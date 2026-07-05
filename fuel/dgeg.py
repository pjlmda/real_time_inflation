"""DGEG national daily average fuel price scraper (Part C — first prototype).

Scrapes Portugal's official public "Preço Médio Diário" statistics page
(precoscombustiveis.dgeg.gov.pt), not the per-station bulk dataset — that
requires a formal data-sharing agreement with the Director-General of
Energy and Geology that we haven't pursued. This page's footer explicitly
states the information is free for non-commercial use ("gratuita, podendo
ser utilizada livremente... proibida a sua utilização para fins
comerciais"), matching this project's scope exactly.

`robots.txt` doesn't exist on this subdomain (confirmed: both a plain HTTP
request and a real browser navigation to it simply time out — no route
configured for that path), so the usual `scraper.antibot.RobotsChecker` is
skipped here rather than risk hanging on a robots.txt fetch that will never
resolve; the site's own explicit non-commercial-use terms above are the
operative permission instead.

Reports a national average with an inherent reporting lag (a given day's
figure isn't finalized until stations report in) — `scrape_date` here is
always DGEG's own most-recently-available date for that fuel type, which
may be a day or two behind the day this scraper actually ran, not the
Lisbon "today" convention scraper/db.py uses for groceries.

Scoped to vehicle fuels only this round (gasoline 95, diesel, LPG auto) —
domestic bottled/piped gas is deliberately out of scope (see the project's
build spec notes on this). Data collection only, no compute/index yet.
"""
from __future__ import annotations

import asyncio
import random
import re

from playwright.async_api import async_playwright

from scraper.antibot import apply_stealth

BASE_URL = "https://precoscombustiveis.dgeg.gov.pt/estatistica/preco-medio-diario/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Our internal fuel_type slug -> DGEG's <select> option value.
FUEL_TYPES = {
    "gasoline_95": "3201",  # Gasolina simples 95
    "diesel": "2101",  # Gasóleo simples
    "lpg_auto": "1120",  # GPL Auto
}

# Each date's data row, e.g.:
# <tr id="rowTipo2026-07-04"><td></td><td>Gasolina simples 95 </td>
#   <td>1,873 €</td><td>litro</td><td>1650</td></tr>
ROW_RE = re.compile(
    r'id="rowTipo(\d{4}-\d{2}-\d{2})">'
    r"<td[^>]*></td><td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td>"
    r"<td[^>]*>([^<]+)</td><td[^>]*>([^<]+)</td>"
)


def parse_price_table(html: str) -> list[dict]:
    """Pure function: page HTML -> list of {date, fuel_name, price, unit,
    n_stations} rows. The page already orders rows most-recent-date-first."""
    rows = []
    for date, fuel_name, price_text, unit, n_stations in ROW_RE.findall(html):
        price_match = re.search(r"([\d,]+)", price_text)
        if not price_match:
            continue
        price = float(price_match.group(1).replace(",", "."))
        rows.append(
            {
                "date": date,
                "fuel_name": fuel_name.strip(),
                "price": price,
                "unit": unit.strip(),
                "n_stations": int(n_stations) if n_stations.strip().isdigit() else None,
            }
        )
    return rows


async def _dismiss_cookie_banner(page) -> None:
    try:
        await page.click("text=ACEITAR", timeout=5000)
    except Exception:  # noqa: BLE001 - banner may not appear on every load
        pass


async def fetch_all_latest_prices() -> dict[str, dict]:
    """Returns {fuel_type: {date, fuel_name, price, unit, n_stations}} for
    each configured fuel type's most recently available date."""
    results: dict[str, dict] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="pt-PT", timezone_id="Europe/Lisbon", user_agent=USER_AGENT
        )
        await apply_stealth(context)
        page = await context.new_page()
        await page.goto(BASE_URL, wait_until="networkidle", timeout=45_000)
        await _dismiss_cookie_banner(page)

        for fuel_type, option_value in FUEL_TYPES.items():
            await page.select_option("#cboTipoCombustivelPMD", option_value)
            await page.click("button:has-text('Procurar')")
            await page.wait_for_timeout(2000)
            html = await page.content()
            rows = parse_price_table(html)
            if rows:
                results[fuel_type] = rows[0]
            await asyncio.sleep(random.uniform(2, 4))

        await browser.close()
    return results
