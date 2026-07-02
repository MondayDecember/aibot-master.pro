from task_queue.worker import _split_message, TELEGRAM_MESSAGE_LIMIT


def test_short_text_single_chunk():
    assert _split_message("hello") == ["hello"]


def test_exact_limit_not_split():
    text = "y" * TELEGRAM_MESSAGE_LIMIT
    assert _split_message(text) == [text]


def test_long_text_without_newlines_loses_nothing():
    text = "x" * 10000
    parts = _split_message(text)
    assert all(len(p) <= TELEGRAM_MESSAGE_LIMIT for p in parts)
    assert "".join(parts) == text


def test_prefers_newline_boundaries():
    text = "\n".join(f"line{i}" for i in range(2000))
    parts = _split_message(text)
    assert all(len(p) <= TELEGRAM_MESSAGE_LIMIT for p in parts)
    # content survives modulo the newlines consumed at cut points
    assert "\n".join(parts).replace("\n", "") == text.replace("\n", "")
