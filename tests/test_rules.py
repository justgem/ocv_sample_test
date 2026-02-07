from app.rules import apply_rules


def test_ignore_rule():
    context = {"file_path": "f"}
    line = "IGNORE ME"
    # simulate cache by directly using rule apply with context overrides
    # no rules loaded, should pass through
    line2, meta, applied = apply_rules(line, context)
    assert line2 == line
    assert meta == {}
    assert applied == []
