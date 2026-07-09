import json

import httpx
import pytest

from alerting.telegram import TelegramNotifier

RealAsyncClient = httpx.AsyncClient


def _patch_transport(monkeypatch, handler):
    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return RealAsyncClient(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)


def test_telegram_notifier_requires_token():
    with pytest.raises(ValueError):
        TelegramNotifier(token="", chat_id="123")


def test_telegram_notifier_requires_chat_id():
    with pytest.raises(ValueError):
        TelegramNotifier(token="abc", chat_id="")


async def test_send_posts_expected_url_and_payload(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    _patch_transport(monkeypatch, handler)

    notifier = TelegramNotifier(token="TESTTOKEN", chat_id="42")
    await notifier.send("hello *world*")

    assert captured["url"] == "https://api.telegram.org/botTESTTOKEN/sendMessage"
    assert captured["body"] == {"chat_id": "42", "text": "hello *world*", "parse_mode": "Markdown"}


async def test_send_raises_on_http_error_status(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"ok": False, "description": "Forbidden"})

    _patch_transport(monkeypatch, handler)

    notifier = TelegramNotifier(token="TESTTOKEN", chat_id="42")
    with pytest.raises(httpx.HTTPStatusError):
        await notifier.send("hello")
