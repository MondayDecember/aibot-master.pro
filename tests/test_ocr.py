import asyncio

import utils.ocr_helper as ocr


def test_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_ENABLED", False)
    assert asyncio.run(ocr.extract_text_from_image(b"whatever")) == ""


def test_empty_bytes_returns_empty(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_ENABLED", True)
    assert asyncio.run(ocr.extract_text_from_image(b"")) == ""


def test_missing_tesseract_is_swallowed(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_ENABLED", True)

    def boom(_):
        raise RuntimeError("tesseract is not installed")
    monkeypatch.setattr(ocr, "_run_ocr", boom)
    # must degrade to "" rather than break photo handling
    assert asyncio.run(ocr.extract_text_from_image(b"img")) == ""


def test_short_output_is_dropped_as_noise(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_ENABLED", True)
    monkeypatch.setattr(ocr, "_run_ocr", lambda _: "ok")  # < _MIN_OCR_CHARS
    assert asyncio.run(ocr.extract_text_from_image(b"img")) == ""


def test_real_text_is_returned_and_capped(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_ENABLED", True)
    monkeypatch.setattr(ocr, "_run_ocr", lambda _: "Ошибка 0x80070005: доступ запрещён")
    out = asyncio.run(ocr.extract_text_from_image(b"img"))
    assert "Ошибка 0x80070005" in out

    monkeypatch.setattr(ocr, "_run_ocr", lambda _: "x" * 10000)
    assert len(asyncio.run(ocr.extract_text_from_image(b"img"))) == ocr._MAX_OCR_CHARS
