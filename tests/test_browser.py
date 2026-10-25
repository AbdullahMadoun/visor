"""Browser lifecycle: URLs, sessions, tab recovery, visual settling."""
import json
import os

import pytest

from conftest import page_url
from visor.core import browser


def test_normalize_url(tmp_path):
    assert browser.normalize_url("example.com") == "https://example.com"
    assert browser.normalize_url("localhost:8000/x") == "http://localhost:8000/x"
    assert browser.normalize_url("https://a.b/c") == "https://a.b/c"
    assert browser.normalize_url("about:blank") == "about:blank"
    local = tmp_path / "page.html"
    local.write_text("<p>hi</p>")
    assert browser.normalize_url(str(local)).startswith("file://")
    with pytest.raises(ValueError):
        browser.normalize_url("  ")


@pytest.mark.browser
def test_session_round_trip(live, tmp_path):
    path = str(tmp_path / "session.json")
    page = browser.get_page()
    page.context.add_cookies([{"name": "sid", "value": "abc123", "url": "https://example.com"}])
    browser.save_session(path)
    with open(path) as f:
        cookies = json.load(f)["cookies"]
    assert any(c["name"] == "sid" and c["value"] == "abc123" for c in cookies)


@pytest.mark.browser
def test_recovers_when_the_active_tab_is_closed(live):
    browser._tab_stack.clear()  # no earlier tab to fall back to
    browser.navigate(page_url("help.html"))
    browser.get_page().close()
    page = browser.get_page()  # reopened at the last URL instead of failing forever
    assert not page.is_closed()
    assert page.url.endswith("help.html")


@pytest.mark.browser
def test_settle_detects_a_still_page(live):
    browser.navigate(page_url("help.html"))
    assert browser.wait_until_stable(timeout=3)


@pytest.mark.browser
def test_screenshot_records_its_scale(live):
    from visor.core import ocr
    path = browser.screenshot()
    assert ocr._registered_scale(path) is not None
    assert os.path.getsize(path) > 0
