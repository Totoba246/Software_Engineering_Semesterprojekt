"""Device categories (F07), e.g. "Baustellenampel" or "Verkehrszählgerät".

Who may do what:
  admin, mitarbeiter  read the list (for the category dropdown of a device)
  admin               create, rename and delete categories
Renaming moves all devices along, deleting leaves its devices without a
category (both done by the database, see the v5 block in schema.sql).
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from .. import security
from .deps import get_conn, require_roles
from .models import Category, CategoryWrite

router = APIRouter(prefix="/api/categories", tags=["Kategorien"])

reader = require_roles(*security.MANAGEMENT)
admin_only = require_roles("admin")

LIST = """
    SELECT c.id, c.name, count(d.device_id)::int AS device_count
    FROM categories c LEFT JOIN devices d ON d.category = c.name
    {where}
    GROUP BY c.id ORDER BY lower(c.name)
"""


def _get(conn, category_id: int) -> dict:
    row = conn.execute(LIST.format(where="WHERE c.id = %s"), (category_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden")
    return row


def _duplicate(name: str) -> HTTPException:
    return HTTPException(status_code=409, detail=f"Die Kategorie „{name}“ gibt es schon.")


@router.get("", response_model=list[Category])
def list_categories(conn=Depends(get_conn), user=Depends(reader)):
    return conn.execute(LIST.format(where="")).fetchall()


@router.post("", response_model=Category, status_code=201)
def create_category(body: CategoryWrite, conn=Depends(get_conn), user=Depends(admin_only)):
    try:
        row = conn.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", (body.name,)).fetchone()
    except psycopg.errors.UniqueViolation:
        raise _duplicate(body.name)
    return _get(conn, row["id"])


@router.patch("/{category_id}", response_model=Category)
def rename_category(category_id: int, body: CategoryWrite, conn=Depends(get_conn), user=Depends(admin_only)):
    """Rename; the devices of this category get the new name automatically."""
    _get(conn, category_id)
    try:
        conn.execute("UPDATE categories SET name = %s WHERE id = %s", (body.name, category_id))
    except psycopg.errors.UniqueViolation:
        raise _duplicate(body.name)
    return _get(conn, category_id)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, conn=Depends(get_conn), user=Depends(admin_only)):
    """Delete; its devices keep working, they just have no category any more."""
    _get(conn, category_id)
    conn.execute("DELETE FROM categories WHERE id = %s", (category_id,))
