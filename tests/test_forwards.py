from datetime import datetime
from types import SimpleNamespace

from utils.telegram_helpers import is_forwarded
from utils.texts import t


def test_is_forwarded_detects_both_fields():
    # modern field
    assert is_forwarded(SimpleNamespace(forward_origin=object(), forward_date=None))
    # legacy field
    assert is_forwarded(SimpleNamespace(forward_origin=None, forward_date=datetime.now()))
    # not a forward
    assert not is_forwarded(SimpleNamespace(forward_origin=None, forward_date=None))
    # object without the attributes at all
    assert not is_forwarded(SimpleNamespace())


def test_comment_prompt_wraps_content():
    out = t("comment_prompt", text="Учёные открыли новую планету")
    assert "Учёные открыли новую планету" in out
    # it's an instruction to comment, not just the raw text
    assert len(out) > len("Учёные открыли новую планету")
