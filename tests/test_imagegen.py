import asyncio

import utils.imagegen_client as imagegen_client


class _FakeResponse:
    def __init__(self, status=200, body=b"PNGDATA"):
        self.status = status
        self._body = body

    async def read(self):
        return self._body

    async def text(self):
        return self._body.decode(errors="replace")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, response):
        self._response = response

    def post(self, url, json=None):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _patch_session(monkeypatch, response):
    monkeypatch.setattr(imagegen_client.aiohttp, "ClientSession", lambda *a, **k: _FakeSession(response))


def test_returns_bytes_on_success(monkeypatch):
    _patch_session(monkeypatch, _FakeResponse(status=200, body=b"pngbytes"))
    result = asyncio.run(imagegen_client.generate_image("a cat"))
    assert result == b"pngbytes"


def test_returns_none_on_error_status(monkeypatch):
    _patch_session(monkeypatch, _FakeResponse(status=500, body=b"boom"))
    result = asyncio.run(imagegen_client.generate_image("a cat"))
    assert result is None


def test_returns_none_when_service_unreachable(monkeypatch):
    class _FailingSession:
        async def __aenter__(self):
            raise ConnectionError("no service running")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(imagegen_client.aiohttp, "ClientSession", lambda *a, **k: _FailingSession())
    result = asyncio.run(imagegen_client.generate_image("a cat"))
    assert result is None
