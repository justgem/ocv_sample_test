from app.alerts import _dedup_key


def test_dedup_key():
    key = _dedup_key("POL", "file")
    assert key == "POL:file"
