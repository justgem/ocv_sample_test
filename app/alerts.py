import json
import os
import time

from app.db import db_cursor
from app.notify import send_slack

ALERT_COOLDOWN_DEFAULT = int(os.getenv("ALERT_COOLDOWN_DEFAULT", "60"))


def _build_message(policy, context):
    severity = policy["severity"]
    mention = ""
    if severity == "CRITICAL":
        mention = "@channel "
    elif severity == "WARN":
        mention = "@here "
    title = f"[{severity}] {policy['name']}"
    lines = [
        f"*발생 시각*: {context.get('timestamp')}",
        f"*파일*: {context.get('file_path')}",
        f"*device/grp*: {context.get('device')} / {context.get('grp')}",
        f"*요약*: {context.get('summary')}",
        "*최근 에러 샘플*:" ,
    ]
    for sample in context.get("samples", [])[:3]:
        lines.append(f"- {sample}")
    return {
        "text": f"{mention}{title}\n" + "\n".join(lines)
    }


def _dedup_key(policy_name, file_path):
    return f"{policy_name}:{file_path}"


def create_alert(policy, context):
    dedup_key = _dedup_key(policy["name"], context.get("file_path"))
    summary = context.get("summary")
    detail = json.dumps(context, ensure_ascii=False)
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO alerts (policy_name, severity, status, dedup_key, summary, detail)
            VALUES (?, ?, 'PENDING', ?, ?, ?)
            """,
            (policy["name"], policy["severity"], dedup_key, summary, detail),
        )
    return dedup_key


def should_send(dedup_key, cooldown_sec):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT created_at FROM alerts
            WHERE dedup_key = ?
            ORDER BY id DESC LIMIT 1
            """,
            (dedup_key,),
        )
        row = cur.fetchone()
        if not row:
            return True
        last_time = time.mktime(time.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S"))
        return time.time() - last_time > cooldown_sec


def mark_alert_status(dedup_key, status):
    with db_cursor() as cur:
        cur.execute(
            "UPDATE alerts SET status = ? WHERE dedup_key = ? AND status = 'PENDING'",
            (status, dedup_key),
        )


def dispatch_alert(policy, context):
    dedup_key = _dedup_key(policy["name"], context.get("file_path"))
    cooldown = policy.get("cooldown_sec") or ALERT_COOLDOWN_DEFAULT
    if not should_send(dedup_key, cooldown):
        return
    create_alert(policy, context)
    payload = _build_message(policy, context)
    result = send_slack(payload)
    if result.get("status") == 429:
        retry_after = int(result.get("headers", {}).get("Retry-After", "1"))
        time.sleep(retry_after)
        result = send_slack(payload)
    status = "SENT" if result.get("ok") else "FAILED"
    mark_alert_status(dedup_key, status)


def list_alerts(limit=50):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(row) for row in cur.fetchall()]


def ack_alert(alert_id):
    with db_cursor() as cur:
        cur.execute("UPDATE alerts SET status='ACK' WHERE id = ?", (alert_id,))


def get_policies():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM alert_policies WHERE enabled = 1")
    return [dict(row) for row in cur.fetchall()]


def evaluate_policies(status_snapshot):
    policies = get_policies()
    for policy in policies:
        name = policy["name"]
        threshold = json.loads(policy.get("threshold_json") or "{}")
        window_sec = threshold.get("window_sec", 60)
        if name == "PARSE_FAIL_RATE":
            _check_parse_fail_rate(policy, threshold, window_sec)
        elif name == "INGEST_STALL":
            _check_ingest_stall(policy, status_snapshot, window_sec)
        elif name == "FILE_MISSING":
            _check_file_missing(policy, status_snapshot)


def _check_parse_fail_rate(policy, threshold, window_sec):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) as total, SUM(CASE WHEN parse_ok = 0 THEN 1 ELSE 0 END) as fail
            FROM events
            WHERE strftime('%s', created_at) >= strftime('%s', 'now') - ?
            """,
            (window_sec,),
        )
        row = cur.fetchone()
    total = row["total"] or 0
    fail = row["fail"] or 0
    if total == 0:
        return
    rate = fail / total
    if rate >= threshold.get("rate", 0.05):
        dispatch_alert(
            policy,
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "file_path": "all",
                "device": "all",
                "grp": "all",
                "summary": f"parse fail rate {rate:.2%}",
                "samples": [],
            },
        )


def _check_ingest_stall(policy, status_snapshot, window_sec):
    now = time.time()
    for path, status in status_snapshot.items():
        if status["status"] == "ok":
            continue
        if now - status["updated_at"] > window_sec:
            dispatch_alert(
                policy,
                {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "file_path": path,
                    "device": None,
                    "grp": None,
                    "summary": "ingest stalled",
                    "samples": [],
                },
            )


def _check_file_missing(policy, status_snapshot):
    for path, status in status_snapshot.items():
        if status["status"] == "missing":
            dispatch_alert(
                policy,
                {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "file_path": path,
                    "device": None,
                    "grp": None,
                    "summary": "file missing",
                    "samples": [],
                },
            )


def record_db_error(error):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO alerts (policy_name, severity, status, dedup_key, summary, detail) VALUES (?, ?, 'FAILED', ?, ?, ?)",
            ("DB_ERROR", "CRITICAL", "DB_ERROR", "DB error", str(error)),
        )
