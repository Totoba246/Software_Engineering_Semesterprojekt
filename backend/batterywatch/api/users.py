"""User management for the admin (F06, "Nutzerkonten verwalten").

There is no e-mail sending, so a new account (or a password reset) gets a
START PASSWORD that is shown to the admin once; the admin passes it on, and
the user must choose an own password at the first login.

Safety rules: an admin can't lock, demote or delete their own account, and
the last active admin can't be removed - otherwise nobody could manage users.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from .. import security
from . import queries
from .deps import CurrentUser, get_conn, require_roles
from .models import User, UserCreate, UserUpdate, UserWithPassword

router = APIRouter(prefix="/api/users", tags=["Nutzerverwaltung"])
admin_only = require_roles("admin")


def _get(conn, user_id: int) -> dict:
    row = conn.execute(queries.USERS.format(where="WHERE u.id = %(id)s"), {"id": user_id}).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Nutzer nicht gefunden")
    return row


def _other_active_admins(conn, user_id: int) -> int:
    return conn.execute("SELECT count(*) AS n FROM users WHERE role = 'admin' AND active AND id <> %s",
                        (user_id,)).fetchone()["n"]


@router.get("", response_model=list[User])
def list_users(conn=Depends(get_conn), admin: CurrentUser = Depends(admin_only)):
    return conn.execute(queries.USERS.format(where="")).fetchall()


@router.post("", response_model=UserWithPassword, status_code=201)
def create_user(body: UserCreate, conn=Depends(get_conn), admin: CurrentUser = Depends(admin_only)):
    username = security.normalize_username(body.username)
    problem = security.check_username(username)
    password = body.password or security.generate_password()
    problem = problem or security.check_password(password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    try:
        row = conn.execute(
            "INSERT INTO users (username, display_name, email, role, password_hash, must_change_password) "
            "VALUES (%s, %s, %s, %s, %s, true) RETURNING id",
            (username, body.display_name.strip(), body.email, body.role, security.hash_password(password)),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"Den Benutzernamen {username} gibt es schon.")
    return UserWithPassword(**_get(conn, row["id"]), start_password=password)


@router.patch("/{user_id}", response_model=UserWithPassword)
def update_user(user_id: int, body: UserUpdate, conn=Depends(get_conn), admin: CurrentUser = Depends(admin_only)):
    current = _get(conn, user_id)
    fields = body.model_fields_set - {"reset_password"}

    # --- safety rules ---------------------------------------------------------
    demoted = "role" in fields and body.role != "admin"
    locked = "active" in fields and body.active is False
    if user_id == admin.id and (demoted or locked):
        raise HTTPException(status_code=400, detail="Das eigene Konto kann nicht gesperrt oder herabgestuft werden.")
    if current["role"] == "admin" and (demoted or locked) and _other_active_admins(conn, user_id) == 0:
        raise HTTPException(status_code=400, detail="Es muss mindestens ein aktiver Admin bleiben.")

    # --- apply ----------------------------------------------------------------
    values = body.model_dump()
    for f in ("display_name", "role", "active"):
        if f in fields and values[f] is None:
            raise HTTPException(status_code=400, detail=f"{f} darf nicht leer sein.")
    if fields:
        sets = ", ".join(f"{f} = %({f})s" for f in fields)  # field names = column names
        conn.execute(f"UPDATE users SET {sets} WHERE id = %(id)s", {**values, "id": user_id})
    if "role" in fields and body.role != "techniker":
        # no longer a technician -> their devices are unassigned
        conn.execute("UPDATE devices SET technician_id = NULL WHERE technician_id = %s", (user_id,))

    start_password = None
    if body.reset_password:
        start_password = security.generate_password()
        conn.execute("UPDATE users SET password_hash = %s, must_change_password = true WHERE id = %s",
                     (security.hash_password(start_password), user_id))
    if locked or body.reset_password:
        conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))  # log out everywhere now
    return UserWithPassword(**_get(conn, user_id), start_password=start_password)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, conn=Depends(get_conn), admin: CurrentUser = Depends(admin_only)):
    current = _get(conn, user_id)
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Das eigene Konto kann nicht gelöscht werden.")
    if current["role"] == "admin" and _other_active_admins(conn, user_id) == 0:
        raise HTTPException(status_code=400, detail="Es muss mindestens ein aktiver Admin bleiben.")
    # sessions are deleted with the user (CASCADE), devices become unassigned (SET NULL)
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
