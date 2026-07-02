import config


def test_parse_allowed_ids_keeps_order_and_drops_junk():
    assert config._parse_allowed_ids("111, 222,abc, -5, 111") == [111, 222]
    assert config._parse_allowed_ids("") == []


def test_parse_model_choices():
    parsed = config._parse_model_choices("default=llama3, coder=qwen3-coder:30b,, bad")
    assert parsed == {"default": "llama3", "coder": "qwen3-coder:30b"}
    assert config._parse_model_choices("") == {}
