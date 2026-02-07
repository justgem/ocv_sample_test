from app.profile import suggest_labels


def test_suggest_labels():
    labels = suggest_labels("DEV", 1, 3)
    assert labels[0]["label"] == "flag_0"
    assert labels[1]["label"] == "v1"
