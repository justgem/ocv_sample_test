import base64
import os

from fastapi import HTTPException, Request

from app.db import record_audit

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")
VIEWER_USER = os.getenv("VIEWER_USER", "viewer")
VIEWER_PASS = os.getenv("VIEWER_PASS", "viewer")


def _parse_basic(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Basic "):
        return None, None
    raw = base64.b64decode(auth.split(" ", 1)[1]).decode("utf-8")
    username, password = raw.split(":", 1)
    return username, password


def require_admin(request: Request):
    username, password = _parse_basic(request)
    if username == ADMIN_USER and password == ADMIN_PASS:
        record_audit(username, "LOGIN_SUCCESS", "admin")
        return "ADMIN"
    record_audit(username or "unknown", "LOGIN_FAIL", "admin")
    raise HTTPException(status_code=401, detail="Unauthorized")


def require_viewer(request: Request):
    username, password = _parse_basic(request)
    if username == ADMIN_USER and password == ADMIN_PASS:
        record_audit(username, "LOGIN_SUCCESS", "viewer")
        return "ADMIN"
    if username == VIEWER_USER and password == VIEWER_PASS:
        record_audit(username, "LOGIN_SUCCESS", "viewer")
        return "VIEWER"
    record_audit(username or "unknown", "LOGIN_FAIL", "viewer")
    raise HTTPException(status_code=401, detail="Unauthorized")
