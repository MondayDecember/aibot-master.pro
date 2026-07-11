from task_queue.worker import (
    _split_message, _extract_long_code_blocks,
    TELEGRAM_MESSAGE_LIMIT,
)


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


# --- _extract_long_code_blocks: pull code out of the explanation so the
# caller can rebuild it as its own message(s) when the whole reply would
# otherwise be split mid-code across several message bubbles ---

def _long_prose(n_chars):
    return ("Пояснение к коду. " * (n_chars // 19 + 1))[:n_chars]


def test_short_reply_with_code_is_left_alone():
    text = "Вот функция:\n```python\nprint('hi')\n```\nГотово."
    new_text, blocks = _extract_long_code_blocks(text)
    assert new_text == text
    assert blocks == []


def test_long_reply_without_code_is_left_alone():
    text = _long_prose(TELEGRAM_MESSAGE_LIMIT + 500)
    new_text, blocks = _extract_long_code_blocks(text)
    assert new_text == text
    assert blocks == []


def test_long_reply_with_code_extracts_it():
    code = "int main() {\n    return 0;\n}\n" * 100  # long enough to push past the limit
    text = _long_prose(4000) + f"\n```cpp\n{code}\n```\n" + _long_prose(200)
    assert len(text) > TELEGRAM_MESSAGE_LIMIT

    new_text, blocks = _extract_long_code_blocks(text)

    assert len(blocks) == 1
    assert blocks[0][0] == "cpp"
    assert blocks[0][1].strip() == code.strip()
    assert "```" not in new_text  # fence replaced by the placeholder
    assert len(new_text) < len(text)


def test_multiple_code_blocks_extracted_in_order():
    text = (
        _long_prose(4000)
        + "\n```python\nprint(1)\n```\n"
        + _long_prose(500)
        + "\n```javascript\nconsole.log(2)\n```\n"
    )
    assert len(text) > TELEGRAM_MESSAGE_LIMIT

    _, blocks = _extract_long_code_blocks(text)

    assert [lang for lang, _ in blocks] == ["python", "javascript"]


def test_empty_code_fence_is_not_extracted():
    text = _long_prose(TELEGRAM_MESSAGE_LIMIT + 500) + "\n```\n```\n"
    new_text, blocks = _extract_long_code_blocks(text)
    assert blocks == []
    assert "```" in new_text
