"""Shared between BaseScraper (scraper/base.py) and CategoryCrawlerBase
(scraper/category_base.py) — both drive a persistent Playwright context and
report to the same scrape_runs alerting shape, previously duplicated
verbatim in both classes.
"""
from __future__ import annotations

from pathlib import Path

from playwright.async_api import BrowserContext

from alerting.base import Notifier
from scraper.antibot import apply_stealth
from scraper.db import SupabaseWriter
from scraper.models import RunResult
from scraper.store_config import StoreConfig

PROFILE_DIR = Path(__file__).resolve().parent.parent / ".pw-profile"


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
    message = (
        f"*{config_name}* {run_kind} {result.status.upper()}\n"
        f"attempted={result.attempted} ok={result.ok} failed={result.failed} "
        f"coverage={result.coverage:.0%}\n"
        f"{result.error_summary or ''}"
    )
    if db_error is not None:
        message += f"\n*DB write failed while finishing this run*: {db_error}"
    await notifier.send(message)
    try:
        db.mark_alerted(result.run_id)
    except Exception:  # noqa: BLE001 - best-effort dedup flag; losing it just risks a
        # duplicate alert next time, which beats losing the alert entirely.
        pass
