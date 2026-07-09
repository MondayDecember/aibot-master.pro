from tools.configure import get_value, set_value, comment_out


def sample():
    return [
        "BOT_TOKEN=abc",
        "BOT_LANGUAGE=ru",
        "# ALLOWED_USER_IDS=123456789,987654321",
        "AUTO_WEB_SEARCH=true",
        "# COMPOSE_FILE=docker-compose.yml:docker-compose.autoupdate.yml",
    ]


def test_get_value_skips_comments():
    lines = sample()
    assert get_value(lines, "BOT_LANGUAGE") == "ru"
    assert get_value(lines, "ALLOWED_USER_IDS") is None
    assert get_value(lines, "COMPOSE_FILE") is None


def test_set_value_replaces_active_line():
    lines = set_value(sample(), "BOT_LANGUAGE", "en")
    assert "BOT_LANGUAGE=en" in lines
    assert lines.count("BOT_LANGUAGE=en") == 1


def test_set_value_uncomments_example_line():
    lines = set_value(sample(), "ALLOWED_USER_IDS", "42")
    assert "ALLOWED_USER_IDS=42" in lines
    # the commented example was replaced, not duplicated
    assert not any(line.startswith("# ALLOWED_USER_IDS") for line in lines)


def test_set_value_appends_when_missing():
    lines = set_value(sample(), "NEW_KEY", "1")
    assert lines[-1] == "NEW_KEY=1"


def test_comment_out_disables_key():
    lines = set_value(sample(), "COMPOSE_FILE", "a.yml:b.yml")
    assert get_value(lines, "COMPOSE_FILE") == "a.yml:b.yml"
    lines = comment_out(lines, "COMPOSE_FILE")
    assert get_value(lines, "COMPOSE_FILE") is None


def test_roundtrip_enable_disable_enable():
    lines = sample()
    lines = set_value(lines, "COMPOSE_FILE", "x")
    lines = comment_out(lines, "COMPOSE_FILE")
    lines = set_value(lines, "COMPOSE_FILE", "y")
    assert get_value(lines, "COMPOSE_FILE") == "y"
    assert sum("COMPOSE_FILE" in line for line in lines) == 1
