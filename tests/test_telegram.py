import json

import httpx
import pytest

from alerting.telegram import MAX_MESSAGE_LENGTH, TelegramNotifier, TelegramSendFailed, escape_markdown

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


@pytest.mark.parametrize("char", ["_", "*", "`", "["])
def test_escape_markdown_escapes_each_special_char(char):
    assert escape_markdown(f"a{char}b") == f"a\\{char}b"


def test_escape_markdown_escapes_mixed_string():
    # Real-shape guard: raw scraped page text (e.g. a Drive-bootstrap
    # diagnostic snippet) can contain any mix of these - all four must
    # survive together, not just individually.
    assert escape_markdown("price_per_kg *promo* `code` [link]") == (
        "price\\_per\\_kg \\*promo\\* \\`code\\` \\[link]"
    )


def test_escape_markdown_leaves_plain_text_unchanged():
    assert escape_markdown("nothing special here, just words and numbers 123") == (
        "nothing special here, just words and numbers 123"
    )


def test_escape_markdown_escapes_backslash_before_the_character_it_precedes():
    # Real bug this guards: escaping "_" before "\\" would leave a raw
    # backslash-underscore pair (e.g. any Windows path) re-paired into a
    # still-unescaped underscore. Backslash must go first so every
    # original backslash is already doubled before the later passes run.
    assert escape_markdown("C:\\Users\\_cache") == "C:\\\\Users\\\\\\_cache"


async def test_send_truncates_messages_over_the_telegram_limit(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["text"] = json.loads(request.content)["text"]
        return httpx.Response(200, json={"ok": True})

    _patch_transport(monkeypatch, handler)

    notifier = TelegramNotifier(token="TESTTOKEN", chat_id="42")
    await notifier.send("x" * (MAX_MESSAGE_LENGTH + 500))

    assert len(captured["text"]) == MAX_MESSAGE_LENGTH
    assert captured["text"].endswith("…")


async def test_send_truncation_does_not_leave_a_dangling_escape_backslash(monkeypatch):
    # Real bug this guards: a naive slice can land exactly between a
    # backslash escape_markdown() inserted and the character it was
    # escaping, leaving an incomplete escape sequence that Telegram
    # rejects with its own 400 - the same failure this truncation exists
    # to prevent in the first place.
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["text"] = json.loads(request.content)["text"]
        return httpx.Response(200, json={"ok": True})

    _patch_transport(monkeypatch, handler)

    notifier = TelegramNotifier(token="TESTTOKEN", chat_id="42")
    # Engineered so the slice boundary (index MAX_MESSAGE_LENGTH - 1) lands
    # exactly on a lone backslash.
    forced = ("x" * (MAX_MESSAGE_LENGTH - 1)) + "\\_rest of a very long message" * 20
    await notifier.send(forced)

    assert not captured["text"].removesuffix("…").endswith("\\")
