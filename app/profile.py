import math
import time
from collections import defaultdict

from app.db import db_cursor, record_audit

_profile_cache = defaultdict(list)


def update_profile(device, grp, values):
    key = (device, grp)
    _profile_cache[key].append(values)
    if len(_profile_cache[key]) >= 50:
        _flush_profile(device, grp)


def _flush_profile(device, grp):
    samples = _profile_cache.pop((device, grp), [])
    if not samples:
        return
    typical_value_count = round(sum(len(v) for v in samples) / len(samples))
    by_index = defaultdict(list)
    for values in samples:
        for idx, value in enumerate(values):
            by_index[idx].append(value)
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO value_profile (device, grp, typical_value_count, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(device, grp) DO UPDATE SET
                typical_value_count=excluded.typical_value_count,
                updated_at=datetime('now')
            """,
            (device, grp, typical_value_count),
        )
        for idx, values in by_index.items():
            min_v = min(values)
            max_v = max(values)
            avg_v = sum(values) / len(values)
            std_v = math.sqrt(sum((v - avg_v) ** 2 for v in values) / len(values))
            unique_count = len(set(values))
            is_binary = int(unique_count <= 2)
            is_constant = int(unique_count == 1)
            negative_rate = sum(1 for v in values if v < 0) / len(values)
            cur.execute(
                """
                INSERT INTO value_profile_index (
                    device, grp, idx, min, max, avg, std, unique_count,
                    is_binary, is_constant, negative_rate, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(device, grp, idx) DO UPDATE SET
                    min=excluded.min,
                    max=excluded.max,
                    avg=excluded.avg,
                    std=excluded.std,
                    unique_count=excluded.unique_count,
                    is_binary=excluded.is_binary,
                    is_constant=excluded.is_constant,
                    negative_rate=excluded.negative_rate,
                    updated_at=datetime('now')
                """,
                (
                    device,
                    grp,
                    idx,
                    min_v,
                    max_v,
                    avg_v,
                    std_v,
                    unique_count,
                    is_binary,
                    is_constant,
                    negative_rate,
                ),
            )


def suggest_labels(device, grp, typical_value_count):
    suggestions = []
    for idx in range(typical_value_count or 0):
        label = f"v{idx}"
        if idx == 0:
            label = "flag_0"
        suggestions.append({"device": device, "grp": grp, "idx": idx, "label": label})
    return suggestions


def save_label(label, actor="system"):
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO value_labels (device, grp, idx, label, unit, note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(device, grp, idx) DO UPDATE SET
                label=excluded.label,
                unit=excluded.unit,
                note=excluded.note,
                updated_at=datetime('now')
            """,
            (
                label["device"],
                label["grp"],
                label["idx"],
                label["label"],
                label.get("unit"),
                label.get("note"),
            ),
        )
    record_audit(actor, "LABEL_UPSERT", str(label))


def list_labels():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM value_labels ORDER BY device, grp, idx")
        return [dict(row) for row in cur.fetchall()]
