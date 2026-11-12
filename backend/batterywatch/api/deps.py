"""Building blocks every endpoint uses: database connection, logged-in user, role check.

FastAPI "dependencies": an endpoint declares e.g.
    user: CurrentUser = Depends(require_roles("chef", "mitarbeiter"))
and FastAPI runs the check BEFORE the endpoint. Not logged in -> 401,
wrong role -> 403. So the rights are enforced on the server (ADR-09),
not only by hiding buttons in the web page.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from .. import security
from ..config import Settings
from . import queries

SESSION_COOKIE = "bw_session"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(request: Request):
    """Borrow a database connection for one request. Changes are committed
    when the request finished without error, otherwise rolled back."""
    with request.app.state.pool.connection() as conn:
        yield conn


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    email: str | None
    role: str
    must_change_password: bool

    @property
    def is_management(self) -> bool:
        return self.role in security.MANAGEMENT


def _user_from_cookie(request: Request, conn) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    row = None
    if token:
        row = conn.execute(queries.SESSION_USER, {"token_hash": security.token_hash(token)}).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Bitte anmelden.")
    return CurrentUser(**row)


def logged_in_user(request: Request, conn=Depends(get_conn)) -> CurrentUser:
    """Any logged-in user, also one who still has to change the start password
    (only used by the login/password endpoints)."""
    return _user_from_cookie(request, conn)


def current_user(user: CurrentUser = Depends(logged_in_user)) -> CurrentUser:
    """A logged-in user who may use the system (start password already changed)."""
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Bitte zuerst das Start-Passwort ändern.")
    return user


def require_roles(*roles: str):
    """Dependency factory: only the given roles may call the endpoint."""

    def check(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Kein Zugriff für diese Rolle.")
        return user

    return check
