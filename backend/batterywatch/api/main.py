"""The API: answers the web page's questions with data from the database (ADR-06).

WHAT IS A "REST API"?
    A small web server that returns DATA (JSON) instead of web pages.
    The web page asks e.g.   GET /api/devices
    and gets back            [{"device_id": "101", "soc_percent": 35.2, "status": "niedrig", ...}, ...]

WHERE DOES IT RUN?
    Container "api", port 8000 inside Docker (= port 20801 on your computer /
    the server, only reachable locally). The browser doesn't call it directly:
    nginx in the frontend container forwards http://<host>:20800/api/... here.
    Clickable documentation of all endpoints: http://localhost:20801/docs

THE PARTS (one file each)
    auth.py      login, logout, own password            /api/auth/...
    devices.py   devices, history, messages, master data /api/devices/..., /api/technicians
    users.py     user management (admin only)            /api/users/...
    appointments.py  private calendar of technicians     /api/appointments/...
    deps.py      "who is logged in?" and role checks used by all of them
    models.py    shapes of the JSON in and out
    queries.py   the SQL

Everything except /api/health and /api/auth/login needs a login (cookie).
Writing measurements is done by the collector, not here.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..config import Settings, get_settings
from ..db import ensure_schema
from . import appointments, auth, devices, users
from .deps import get_conn


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the web application. (A function, so tests can pass their own settings.)"""
    settings = settings or get_settings()

    # Runs once at start-up (before "yield") and once at shutdown (after it).
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with psycopg.connect(settings.database_url, autocommit=True) as conn:
            ensure_schema(conn)  # create/upgrade the tables
        # A "pool" keeps up to 10 database connections open and lends them to requests.
        pool = ConnectionPool(settings.database_url, min_size=1, max_size=10,
                              kwargs={"row_factory": dict_row}, open=True)
        app.state.pool = pool
        app.state.settings = settings
        app.state.login_throttle = auth.LoginThrottle(settings.login_max_failures, settings.login_lock_minutes)
        try:
            yield
        finally:
            pool.close()

    app = FastAPI(title="BatteryWatch API", version="0.2.0", lifespan=lifespan)
    if settings.cors_origins and settings.cors_origins != ["*"]:
        # Only needed if the web page is served from another address than the API.
        # Normally both come through nginx / the Vite dev server, so this stays off.
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])

    app.include_router(auth.router)
    app.include_router(devices.router)
    app.include_router(users.router)
    app.include_router(appointments.router)

    @app.get("/api/health", tags=["System"])
    def health(conn=Depends(get_conn)):
        """Is the API alive and the database reachable? (no login needed)"""
        conn.execute("SELECT 1")
        return {"status": "ok", "database": "ok"}

    return app


# The object the web server "uvicorn" runs (see the CMD in backend/Dockerfile:
# "uvicorn batterywatch.api.main:app" = file batterywatch/api/main.py, variable app).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
