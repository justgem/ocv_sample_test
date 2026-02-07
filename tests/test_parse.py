from app.parse import parse_line


def test_parse_semicolon():
    context = {}
    line = "DEV_A;1;2;3;4;-1; 419"
    parsed = parse_line(line, context)
    assert parsed["device"] == "DEV_A"
    assert parsed["seq"] == 1
    assert parsed["grp"] == 2
    assert parsed["value_count"] == 4
    assert parsed["has_negative"] == 1


def test_parse_tab():
    context = {}
    line = "DEV_B\t2\t3\t9\t8"
    parsed = parse_line(line, context)
    assert parsed["value_count"] == 2


def test_parse_space():
    context = {}
    line = "noiseDEV_C 3 4 1 2"
    parsed = parse_line(line, context)
    assert parsed["device"] == "noiseDEV_C"
