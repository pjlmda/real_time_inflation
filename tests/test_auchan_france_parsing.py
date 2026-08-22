import pytest

from scraper.auchan_france import AuchanFranceScraper, parse_price_per_unit
from scraper.models import FetchFailed


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1,63€ / l", (1.63, "EUR/L")),
        ("1,63€ / L", (1.63, "EUR/L")),
        ("4,20€ / kg", (4.20, "EUR/kg")),
        ("0,97€ / u", (0.97, "EUR/un")),
        ("0,29€ / pce", (0.29, "EUR/un")),  # "pce" (pièce) is what auchan.fr actually renders
        ("1€ / l", (1.0, "EUR/L")),  # whole numbers render with no decimal point
    ],
)
def test_parse_price_per_unit_matches_real_auchan_france_formats(text, expected):
    assert parse_price_per_unit(text) == expected


def test_parse_price_per_unit_raises_on_unparseable_text():
    with pytest.raises(FetchFailed):
        parse_price_per_unit("indisponible")


class _FakeLocator:
    def __init__(self, text, raises=None):
        self._text = text
        self._raises = raises

    def locator(self, *_args, **_kwargs):
        return self

    async def inner_text(self, timeout=None):
        if self._raises:
            raise self._raises
        return self._text


class _FakePage:
    def __init__(
        self,
        html="<html></html>",
        body_text="Some page text",
        url="https://www.auchan.fr/x",
        title="X",
        raises=None,
    ):
        self._html = html
        self._body = _FakeLocator(body_text, raises=raises)
        self.url = url
        self._title = title

    async def content(self):
        return self._html

    def locator(self, *_args, **_kwargs):
        return self._body

    async def title(self):
        return self._title


async def test_diagnostic_snapshot_captures_page_state_on_bootstrap_failure():
    # Regression test: the Drive-location bootstrap flow started timing out
    # in CI only (2026-08-18 onward), identically at both tracked locations,
    # while reproducing cleanly from a non-CI network - the bare
    # TimeoutError alone gave no way to tell what was actually on the page.
    page = _FakePage(
        html="<html><body>Bienvenue</body></html>",
        body_text="Bienvenue sur Auchan.fr  Livraison indisponible dans votre zone",
        url="https://www.auchan.fr/auchan-lait-demi-ecreme-sterilise-uht/pr-C1171534",
        title="Auchan.fr",
    )

    snapshot = await AuchanFranceScraper._diagnostic_snapshot(page)

    assert "url=https://www.auchan.fr/auchan-lait-demi-ecreme-sterilise-uht/pr-C1171534" in snapshot
    assert "title='Auchan.fr'" in snapshot
    assert "block_markers_detected=False" in snapshot
    assert "Livraison indisponible dans votre zone" in snapshot


async def test_diagnostic_snapshot_never_raises_even_if_page_access_fails():
    # Diagnostics are best-effort - a failure gathering them must never mask
    # the original bootstrap exception that triggered the capture.
    page = _FakePage(raises=RuntimeError("page already closed"))

    snapshot = await AuchanFranceScraper._diagnostic_snapshot(page)

    assert "diagnostic snapshot itself failed" in snapshot
    assert "page already closed" in snapshot
