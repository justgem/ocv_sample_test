import json
import os
import urllib.request

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_TIMEOUT_SEC = int(os.getenv("WEBHOOK_TIMEOUT_SEC", "5"))
WEBHOOK_DISABLE = os.getenv("WEBHOOK_DISABLE", "0") == "1"


def send_slack(payload):
    if WEBHOOK_DISABLE or not WEBHOOK_URL:
        return {"ok": False, "error": "disabled"}
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SEC) as response:
            return {"ok": response.status < 300, "status": response.status, "headers": dict(response.headers)}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "headers": dict(exc.headers)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
