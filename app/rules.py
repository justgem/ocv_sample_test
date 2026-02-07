import json
import os
import re
import time
from app.db import db_cursor, record_audit

RULE_RELOAD_SEC = int(os.getenv("RULE_RELOAD_SEC", "10"))

_last_load = 0.0
_cache = []


def _load_rules():
    global _cache, _last_load
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM parse_rules
            WHERE enabled = 1 AND mode = 'ACTIVE'
            ORDER BY priority ASC, id ASC
            """
        )
        _cache = [dict(row) for row in cur.fetchall()]
    _last_load = time.time()


def get_rules():
    if time.time() - _last_load > RULE_RELOAD_SEC:
        _load_rules()
    return _cache


def apply_rules(line, context):
    applied_ids = []
    for rule in get_rules():
        if not _scope_match(rule, context):
            continue
        rule_type = rule["rule_type"]
        pattern = rule.get("pattern")
        action = json.loads(rule.get("action_json") or "{}")
        if rule_type == "IGNORE_LINE_REGEX":
            if pattern and re.search(pattern, line):
                applied_ids.append(rule["id"])
                return line, {"record_type": "IGNORE", "parse_ok": 1}, applied_ids
        elif rule_type == "FORCE_HEADER_REGEX":
            if pattern and re.search(pattern, line):
                applied_ids.append(rule["id"])
                return line, {"record_type": "HEADER", "parse_ok": 1}, applied_ids
        elif rule_type == "DEVICE_REWRITE_REGEX":
            if pattern:
                line, n = re.subn(pattern, action.get("replace", ""), line)
                if n:
                    applied_ids.append(rule["id"])
        elif rule_type == "LINE_REPLACE_REGEX":
            if pattern:
                line, n = re.subn(pattern, action.get("replace", ""), line)
                if n:
                    applied_ids.append(rule["id"])
        elif rule_type == "DELIMITER_OVERRIDE":
            if action.get("delimiter"):
                context["delimiter_override"] = action["delimiter"]
                applied_ids.append(rule["id"])
        elif rule_type == "VALUECOUNT_RANGE_ENFORCE":
            min_v = action.get("min")
            max_v = action.get("max")
            context["valuecount_range"] = (min_v, max_v)
            applied_ids.append(rule["id"])
        elif rule_type == "DROP_VALUE_INDEXES":
            context["drop_indexes"] = action.get("indexes", [])
            applied_ids.append(rule["id"])
        elif rule_type == "COERCE_NUMERIC":
            context["coerce_numeric"] = True
            applied_ids.append(rule["id"])
    return line, {}, applied_ids


def _scope_match(rule, context):
    scope_type = rule.get("scope_type", "GLOBAL")
    scope_value = rule.get("scope_value")
    if scope_type == "GLOBAL":
        return True
    if scope_type == "FILE":
        return scope_value and scope_value == context.get("file_path")
    if scope_type == "DEVICE":
        return scope_value and scope_value == context.get("device")
    return False


def save_rule(rule, actor="system"):
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO parse_rules (enabled, priority, mode, scope_type, scope_value,
                rule_type, pattern, action_json, note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                rule.get("enabled", 1),
                rule.get("priority", 100),
                rule.get("mode", "ACTIVE"),
                rule.get("scope_type", "GLOBAL"),
                rule.get("scope_value"),
                rule.get("rule_type"),
                rule.get("pattern"),
                json.dumps(rule.get("action", {})),
                rule.get("note"),
            ),
        )
    record_audit(actor, "RULE_CREATE", json.dumps(rule, ensure_ascii=False))
    _load_rules()


def update_rule(rule_id, updates, actor="system"):
    columns = []
    values = []
    for key, value in updates.items():
        if key == "action":
            columns.append("action_json = ?")
            values.append(json.dumps(value))
        else:
            columns.append(f"{key} = ?")
            values.append(value)
    columns.append("updated_at = datetime('now')")
    values.append(rule_id)
    with db_cursor() as cur:
        cur.execute(f"UPDATE parse_rules SET {', '.join(columns)} WHERE id = ?", values)
    record_audit(actor, "RULE_UPDATE", json.dumps({"id": rule_id, "updates": updates}, ensure_ascii=False))
    _load_rules()


def delete_rule(rule_id, actor="system"):
    with db_cursor() as cur:
        cur.execute("DELETE FROM parse_rules WHERE id = ?", (rule_id,))
    record_audit(actor, "RULE_DELETE", json.dumps({"id": rule_id}, ensure_ascii=False))
    _load_rules()
