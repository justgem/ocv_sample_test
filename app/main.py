import json
import os
import threading
import time

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import alerts, profile
from app.auth import require_admin, require_viewer
from app.broadcast import iter_events
from app.db import ensure_default_policies, init_db, list_recent_events, record_audit
from app.ingest import get_status_snapshot, start_ingest_loop
from app.rules import delete_rule, save_rule, update_rule
from app.profile import list_labels, save_label

app = FastAPI()
app.mount("/static", StaticFiles(directory="app/static"), name="static")

stop_event = threading.Event()


def _alert_loop():
    while not stop_event.is_set():
        try:
            alerts.evaluate_policies(get_status_snapshot())
        except Exception as exc:
            alerts.record_db_error(exc)
        time.sleep(5)


@app.on_event("startup")
def startup():
    init_db()
    ensure_default_policies()
    threading.Thread(target=start_ingest_loop, args=(stop_event,), daemon=True).start()
    threading.Thread(target=_alert_loop, daemon=True).start()


@app.on_event("shutdown")
def shutdown():
    stop_event.set()


@app.get("/", response_class=HTMLResponse)
def index():
    with open("app/static/index.html", "r", encoding="utf-8") as handle:
        return handle.read()


@app.get("/admin", response_class=HTMLResponse)
def admin(role=Depends(require_admin)):
    record_audit(role, "LOGIN", "/admin")
    with open("app/static/admin.html", "r", encoding="utf-8") as handle:
        return handle.read()


@app.get("/api/events")
def api_events(role=Depends(require_viewer)):
    return JSONResponse(list_recent_events())


@app.get("/api/stream")
def api_stream(role=Depends(require_viewer)):
    return StreamingResponse(iter_events(), media_type="text/event-stream")


@app.get("/admin/api/status")
def admin_status(role=Depends(require_admin)):
    return JSONResponse(get_status_snapshot())


@app.get("/admin/api/rules")
def admin_rules(role=Depends(require_admin)):
    from app.db import db_cursor

    with db_cursor() as cur:
        cur.execute("SELECT * FROM parse_rules ORDER BY priority, id")
        return JSONResponse([dict(row) for row in cur.fetchall()])


@app.post("/admin/api/rules")
def admin_rule_create(payload: dict, role=Depends(require_admin)):
    save_rule(payload, actor=role)
    return JSONResponse({"ok": True})


@app.put("/admin/api/rules/{rule_id}")
def admin_rule_update(rule_id: int, payload: dict, role=Depends(require_admin)):
    update_rule(rule_id, payload, actor=role)
    return JSONResponse({"ok": True})


@app.delete("/admin/api/rules/{rule_id}")
def admin_rule_delete(rule_id: int, role=Depends(require_admin)):
    delete_rule(rule_id, actor=role)
    return JSONResponse({"ok": True})


@app.get("/admin/api/labels")
def admin_labels(role=Depends(require_admin)):
    return JSONResponse(list_labels())


@app.post("/admin/api/labels")
def admin_label_upsert(payload: dict, role=Depends(require_admin)):
    save_label(payload, actor=role)
    return JSONResponse({"ok": True})


@app.get("/admin/api/alerts")
def admin_alerts(role=Depends(require_admin)):
    return JSONResponse(alerts.list_alerts())


@app.post("/admin/api/alerts/{alert_id}/ack")
def admin_alert_ack(alert_id: int, role=Depends(require_admin)):
    alerts.ack_alert(alert_id)
    return JSONResponse({"ok": True})


@app.post("/admin/api/preview")
def admin_preview(payload: dict, role=Depends(require_admin)):
    from app.parse import parse_line
    from app.rules import apply_rules

    line = payload.get("line", "")
    context = {"file_path": payload.get("file_path")}
    line, meta, applied_ids = apply_rules(line, context)
    parsed = parse_line(line, context)
    parsed["rule_applied_ids"] = applied_ids
    parsed["rule_applied_count"] = len(applied_ids)
    return JSONResponse(parsed)


@app.get("/admin/api/export")
def admin_export(role=Depends(require_admin)):
    from app.db import db_cursor

    with db_cursor() as cur:
        cur.execute("SELECT * FROM parse_rules")
        rules = [dict(row) for row in cur.fetchall()]
        cur.execute("SELECT * FROM value_labels")
        labels = [dict(row) for row in cur.fetchall()]
    return JSONResponse({"rules": rules, "labels": labels})


@app.post("/admin/api/import")
def admin_import(payload: dict, role=Depends(require_admin)):
    rules = payload.get("rules", [])
    labels = payload.get("labels", [])
    for rule in rules:
        save_rule(rule, actor=role)
    for label in labels:
        save_label(label, actor=role)
    return JSONResponse({"ok": True})


@app.get("/health")
def health():
    return {"ok": True, "ts": time.time()}
