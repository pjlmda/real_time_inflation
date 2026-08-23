from alerting.base import Notifier, redact, safe_send


class _OkNotifier(Notifier):
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


class _FailingNotifier(Notifier):
    async def send(self, message: str) -> None:
        raise RuntimeError("simulated delivery failure")


async def test_safe_send_returns_true_and_delivers_on_success():
    notifier = _OkNotifier()

    delivered = await safe_send(notifier, "hello")

    assert delivered is True
    assert notifier.sent == ["hello"]


async def test_safe_send_returns_false_and_does_not_raise_on_failure():
    notifier = _FailingNotifier()

    delivered = await safe_send(notifier, "hello")

    assert delivered is False


async def test_safe_send_prints_original_message_to_stderr_on_failure(capsys):
    # Real bug this guards: a Drive-bootstrap diagnostic message was built
    # successfully but Telegram rejected it, and because nothing caught
    # notifier.send()'s failure, the message content was never visible
    # anywhere - not delivered, not printed, not readable by anyone.
    notifier = _FailingNotifier()

    await safe_send(notifier, "the diagnostic content that must not be lost")

    captured = capsys.readouterr()
    assert "the diagnostic content that must not be lost" in captured.err
    assert "simulated delivery failure" in captured.err


def test_redact_replaces_configured_secret_values(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "SUPERSECRETTOKEN")

    assert redact("error talking to bot SUPERSECRETTOKEN") == "error talking to bot ***"


def test_redact_ignores_unset_secrets(monkeypatch):
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    assert redact("nothing to redact here") == "nothing to redact here"


async def test_safe_send_redacts_secrets_from_stderr_fallback(monkeypatch, capsys):
    # Real risk this guards: escape_markdown() backslash-prefixes special
    # characters, which can make an otherwise-masked secret (GitHub Actions
    # masks by exact string match) no longer match that mask once escaped -
    # this is the defensive backstop, checked at the safe_send() level so
    # it protects every call site uniformly.
    monkeypatch.setenv("EIA_API_KEY", "SUPERSECRETKEY123")
    notifier = _FailingNotifier()

    await safe_send(notifier, "request failed for key SUPERSECRETKEY123")

    captured = capsys.readouterr()
    assert "SUPERSECRETKEY123" not in captured.err
    assert "***" in captured.err
