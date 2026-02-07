import json
import re
from statistics import mean

NUMERIC_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+")


def detect_delimiter(line, override=None):
    if override:
        return override
    if ";" in line:
        return ";"
    if "\t" in line:
        return "\t"
    return None


def clean_device(raw):
    match = TOKEN_RE.search(raw)
    return match.group(0) if match else None


def parse_line(line, context):
    raw_line = line.rstrip("\r\n")
    delimiter = detect_delimiter(raw_line, context.get("delimiter_override"))
    record_type = "DATA"
    if raw_line.strip().startswith("#") or raw_line.strip().lower().startswith("header"):
        return {
            "raw_line": raw_line,
            "record_type": "HEADER",
            "parse_ok": 1,
            "parse_error": None,
        }
    if not raw_line.strip():
        return {
            "raw_line": raw_line,
            "record_type": "IGNORE",
            "parse_ok": 1,
            "parse_error": None,
        }
    tokens = raw_line.split(delimiter) if delimiter else raw_line.split()
    if len(tokens) < 3:
        return {
            "raw_line": raw_line,
            "record_type": "UNKNOWN",
            "parse_ok": 0,
            "parse_error": "not_enough_fields",
        }
    device = clean_device(tokens[0])
    try:
        seq = int(tokens[1].strip())
        grp = int(tokens[2].strip())
    except ValueError:
        return {
            "raw_line": raw_line,
            "record_type": record_type,
            "parse_ok": 0,
            "parse_error": "seq_or_grp_invalid",
        }
    values = []
    parse_ok = 1
    parse_error = None
    for token in tokens[3:]:
        for match in NUMERIC_RE.findall(token):
            try:
                if "." in match:
                    values.append(float(match))
                else:
                    values.append(int(match))
            except ValueError:
                parse_ok = 0
                parse_error = "value_parse_error"
    drop_indexes = context.get("drop_indexes", [])
    if drop_indexes:
        values = [v for idx, v in enumerate(values) if idx not in drop_indexes]
    if context.get("coerce_numeric"):
        values = [float(v) for v in values]
    value_count = len(values)
    value_min = min(values) if values else None
    value_max = max(values) if values else None
    value_avg = mean(values) if values else None
    has_negative = int(any(v < 0 for v in values)) if values else 0
    valuecount_range = context.get("valuecount_range")
    if valuecount_range:
        min_v, max_v = valuecount_range
        if (min_v is not None and value_count < min_v) or (max_v is not None and value_count > max_v):
            parse_ok = 0
            parse_error = "value_count_out_of_range"
    return {
        "raw_line": raw_line,
        "record_type": record_type,
        "parse_ok": parse_ok,
        "parse_error": parse_error,
        "device": device,
        "seq": seq,
        "grp": grp,
        "values": values,
        "value_count": value_count,
        "value_min": value_min,
        "value_max": value_max,
        "value_avg": value_avg,
        "has_negative": has_negative,
    }


def to_values_json(values):
    return json.dumps(values)
