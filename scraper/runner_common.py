"""Shared between BaseScraper (scraper/base.py) and CategoryCrawlerBase
(scraper/category_base.py) — both drive a persistent Playwright context and
report to the same scrape_runs alerting shape, previously duplicated
verbatim in both classes.
"""
from __future__ import annotations

from pathlib import Path

from playwright.async_api import BrowserContext

from alerting.base import Notifier, safe_send
from alerting.telegram import escape_markdown
from scraper.antibot import apply_stealth
from scraper.db import SupabaseWriter
from scraper.models import RunResult
from scraper.store_config import StoreConfig

PROFILE_DIR = Path(__file__).resolve().parent.parent / ".pw-profile"

# Was error_reasons[:5] in both BaseScraper.run and CategoryCrawlerBase.run -
# silently dropped every failure past the 5th with no indication anything
# was omitted. Found while investigating four Auchan France Marseille
# listings that looked like they'd stopped being scraped entirely (no
# success, no error) when they were actually failing every day exactly like
# their siblings - Marseille regularly has 9+ failing listings, so 4 of them
# never made it into error_summary at all. Raised the cap and made
# truncation visible instead of silent.
ERROR_SUMMARY_LIMIT = 20


def summarize_error_reasons(error_reasons: list[str]) -> str | None:
    if not error_reasons:
        return None
    summary = "; ".join(error_reasons[:ERROR_SUMMARY_LIMIT])
    omitted = len(error_reasons) - ERROR_SUMMARY_LIMIT
    if omitted > 0:
        summary += f"; and {omitted} more"
    return summary


async def build_context(
    playwright, config: StoreConfig, proxy_url: str | None, profile_suffix: str = ""
) -> BrowserContext:
    launch_kwargs: dict = {
        "user_data_dir": str(PROFILE_DIR / f"{config.slug}{profile_suffix}"),
        "headless": True,
        "locale": config.locale,
        "timezone_id": config.timezone_id,
        "user_agent": config.user_agent,
        "extra_http_headers": {"Accept-Language": "pt-PT,pt;q=0.9"},
    }
    if proxy_url:
        launch_kwargs["proxy"] = {"server": proxy_url}
    context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
    await apply_stealth(context)
    return context


async def send_run_alert(
    notifier: Notifier,
    db: SupabaseWriter,
    config_name: str,
    result: RunResult,
    run_kind: str,
    db_error: Exception | None = None,
) -> None:
    # error_summary/db_error can embed raw scraped page text (e.g. a
    # Drive-bootstrap diagnostic snippet) or an arbitrary exception message
    # - escaped before going into the message so it can't break Telegram's
    # Markdown parser. The literal *bold* markers below are our own
    # controlled formatting, left unescaped on purpose.
    error_summary = escape_markdown(result.error_summary) if result.error_summary else ""
    message = (
        f"*{config_name}* {run_kind} {result.status.upper()}\n"
        f"attempted={result.attempted} ok={result.ok} failed={result.failed} "
        f"coverage={result.coverage:.0%}\n"
        f"{error_summary}"
    )
    if db_error is not None:
        message += f"\n*DB write failed while finishing this run*: {escape_markdown(str(db_error))}"

    delivered = await safe_send(notifier, message)
    if not delivered:
        # Never mark "alerted" for a message that never actually reached
        # Telegram - that would wrongly suppress a real retry next run.
        return
    try:
        db.mark_alerted(result.run_id)
    except Exception:  # noqa: BLE001 - best-effort dedup flag; losing it just risks a
        # duplicate alert next time, which beats losing the alert entirely.
        pass
