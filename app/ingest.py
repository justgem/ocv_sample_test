import codecs
import glob
import os
import threading
import time

from app.broadcast import publish_event
from app.db import get_file_state, insert_event, update_file_state
from app.parse import parse_line
from app.profile import update_profile
from app.rules import apply_rules

LOG_DIR = os.getenv("LOG_DIR", "./sample_logs")
INCLUDE_GLOBS = os.getenv("INCLUDE_FILES", "*")

status_lock = threading.Lock()
file_status = {}


def _iter_files():
    patterns = [p.strip() for p in INCLUDE_GLOBS.split(",") if p.strip()]
    for pattern in patterns:
        for path in glob.glob(os.path.join(LOG_DIR, pattern)):
            yield path


def _read_incremental(path, start_offset):
    with open(path, "rb") as handle:
        handle.seek(start_offset)
        data = handle.read()
    try:
        decoder = codecs.getincrementaldecoder("utf-8")()
        text = decoder.decode(data)
        return text, len(data)
    except UnicodeDecodeError:
        decoder = codecs.getincrementaldecoder("cp949")()
        text = decoder.decode(data)
        return text, len(data)


def ingest_once():
    for path in _iter_files():
        inode = str(os.stat(path).st_ino)
        state = get_file_state(path)
        offset = state["offset"] if state else 0
        if state and state.get("inode") != inode:
            offset = 0
        try:
            text, delta = _read_incremental(path, offset)
        except FileNotFoundError:
            _update_status(path, "missing")
            continue
        if not text:
            _update_status(path, "idle")
            continue
        for line in text.splitlines():
            context = {"file_path": path}
            line, meta, applied_ids = apply_rules(line, context)
            if meta.get("record_type") == "IGNORE":
                continue
            parsed = parse_line(line, context)
            payload = {"file_path": path, **parsed}
            payload["rule_applied_ids"] = applied_ids
            payload["rule_applied_count"] = len(applied_ids)
            insert_event(payload)
            if parsed.get("parse_ok") and parsed.get("values"):
                update_profile(parsed.get("device"), parsed.get("grp"), parsed.get("values"))
            publish_event(payload)
        update_file_state(path, offset + delta, inode)
        _update_status(path, "ok")


def _update_status(path, status):
    with status_lock:
        file_status[path] = {
            "status": status,
            "updated_at": time.time(),
        }


def get_status_snapshot():
    with status_lock:
        return {k: dict(v) for k, v in file_status.items()}


def start_ingest_loop(stop_event):
    while not stop_event.is_set():
        ingest_once()
        time.sleep(1)
