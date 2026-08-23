import json

import httpx
import pytest

from alerting.telegram import TelegramNotifier, TelegramSendFailed

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
    with pytest.raises(TelegramSendFailed):
        await notifier.send("hello")


async def test_send_does_not_leak_token_on_http_error(monkeypatch):
    # Real bug this guards: httpx.HTTPStatusError's default str() embeds
    # the full request URL, which is https://api.telegram.org/bot<TOKEN>/
    # sendMessage - a revoked/invalid token (401) or any other error must
    # not surface that URL verbatim, since callers propagate this
    # exception's message uncaught (no caller currently wraps notifier.send()).
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})

    _patch_transport(monkeypatch, handler)

    notifier = TelegramNotifier(token="SUPERSECRETTOKEN", chat_id="42")
    with pytest.raises(TelegramSendFailed) as exc_info:
        await notifier.send("hello")

    assert "SUPERSECRETTOKEN" not in str(exc_info.value)
