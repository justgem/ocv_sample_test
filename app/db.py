import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "./data.db")
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "30"))

_db_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_conn = _connect()


@contextmanager
def db_cursor():
    with _db_lock:
        global _conn
        try:
            _conn.execute("SELECT 1")
        except sqlite3.Error:
            _conn = _connect()
        cur = _conn.cursor()
        try:
            yield cur
            _conn.commit()
        except Exception:
            _conn.rollback()
            raise
        finally:
            cur.close()


def init_db():
    with db_cursor() as cur:
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT (datetime('now')),
                file_path TEXT,
                raw_line TEXT,
                record_type TEXT,
                parse_ok INTEGER,
                parse_error TEXT,
                device TEXT,
                seq INTEGER,
                grp INTEGER,
                values_json TEXT,
                value_count INTEGER,
                value_min REAL,
                value_max REAL,
                value_avg REAL,
                has_negative INTEGER,
                rule_applied_ids_json TEXT,
                rule_applied_count INTEGER
            );
            CREATE TABLE IF NOT EXISTS file_state (
                file_path TEXT PRIMARY KEY,
                offset INTEGER,
                inode TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS parse_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enabled INTEGER,
                priority INTEGER,
                mode TEXT,
                scope_type TEXT,
                scope_value TEXT,
                rule_type TEXT,
                pattern TEXT,
                action_json TEXT,
                note TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS value_labels (
                device TEXT,
                grp INTEGER,
                idx INTEGER,
                label TEXT,
                unit TEXT,
                note TEXT,
                updated_at TEXT,
                PRIMARY KEY(device, grp, idx)
            );
            CREATE TABLE IF NOT EXISTS value_profile (
                device TEXT,
                grp INTEGER,
                typical_value_count INTEGER,
                updated_at TEXT,
                PRIMARY KEY(device, grp)
            );
            CREATE TABLE IF NOT EXISTS value_profile_index (
                device TEXT,
                grp INTEGER,
                idx INTEGER,
                min REAL,
                max REAL,
                avg REAL,
                std REAL,
                unique_count INTEGER,
                is_binary INTEGER,
                is_constant INTEGER,
                negative_rate REAL,
                updated_at TEXT,
                PRIMARY KEY(device, grp, idx)
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT (datetime('now')),
                actor TEXT,
                action TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT (datetime('now')),
                policy_name TEXT,
                severity TEXT,
                status TEXT,
                dedup_key TEXT,
                summary TEXT,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS alert_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                enabled INTEGER,
                threshold_json TEXT,
                cooldown_sec INTEGER,
                severity TEXT,
                updated_at TEXT
            );
            """
        )


def insert_event(payload):
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO events (
                file_path, raw_line, record_type, parse_ok, parse_error,
                device, seq, grp, values_json, value_count, value_min, value_max,
                value_avg, has_negative, rule_applied_ids_json, rule_applied_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("file_path"),
                payload.get("raw_line"),
                payload.get("record_type"),
                payload.get("parse_ok"),
                payload.get("parse_error"),
                payload.get("device"),
                payload.get("seq"),
                payload.get("grp"),
                json.dumps(payload.get("values", [])),
                payload.get("value_count"),
                payload.get("value_min"),
                payload.get("value_max"),
                payload.get("value_avg"),
                payload.get("has_negative"),
                json.dumps(payload.get("rule_applied_ids", [])),
                payload.get("rule_applied_count"),
            ),
        )


def update_file_state(file_path, offset, inode):
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO file_state (file_path, offset, inode, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(file_path) DO UPDATE SET
                offset=excluded.offset,
                inode=excluded.inode,
                updated_at=datetime('now')
            """,
            (file_path, offset, inode),
        )


def get_file_state(file_path):
    with db_cursor() as cur:
        cur.execute("SELECT file_path, offset, inode FROM file_state WHERE file_path = ?", (file_path,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_recent_events(limit=200):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(row) for row in cur.fetchall()]


def prune_old_records():
    cutoff = int(time.time()) - RETENTION_DAYS * 86400
    with db_cursor() as cur:
        cur.execute("DELETE FROM events WHERE strftime('%s', created_at) < ?", (cutoff,))
        cur.execute("DELETE FROM alerts WHERE strftime('%s', created_at) < ?", (cutoff,))
        cur.execute("DELETE FROM audit_log WHERE strftime('%s', created_at) < ?", (cutoff,))


def record_audit(actor, action, detail):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log (actor, action, detail) VALUES (?, ?, ?)",
            (actor, action, detail),
        )


def ensure_default_policies():
    defaults = [
        ("PARSE_FAIL_RATE", {"rate": 0.05, "window_sec": 60}, 60, "WARN"),
        ("INGEST_STALL", {"window_sec": 60}, 120, "WARN"),
        ("FILE_MISSING", {"window_sec": 60}, 300, "CRITICAL"),
        ("DB_ERROR", {"window_sec": 60}, 300, "CRITICAL"),
    ]
    with db_cursor() as cur:
        for name, threshold, cooldown, severity in defaults:
            cur.execute(
                """
                INSERT INTO alert_policies (name, enabled, threshold_json, cooldown_sec, severity, updated_at)
                VALUES (?, 1, ?, ?, ?, datetime('now'))
                ON CONFLICT(name) DO NOTHING
                """,
                (name, json.dumps(threshold), cooldown, severity),
            )
