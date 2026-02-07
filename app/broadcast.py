import json
import queue
import threading

MAX_QUEUE = 2000

_event_queue = queue.Queue(maxsize=MAX_QUEUE)
_lock = threading.Lock()


def publish_event(payload):
    try:
        _event_queue.put_nowait(payload)
    except queue.Full:
        try:
            _event_queue.get_nowait()
        except queue.Empty:
            pass
        _event_queue.put_nowait(payload)


def iter_events():
    while True:
        payload = _event_queue.get()
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def get_snapshot():
    items = []
    with _lock:
        while not _event_queue.empty():
            try:
                items.append(_event_queue.get_nowait())
            except queue.Empty:
                break
    for item in items:
        publish_event(item)
    return items
