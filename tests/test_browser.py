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


@pytest.mark.browser
def test_attached_scripts_share_one_tab(tmp_path, monkeypatch):
    """Two scripts attached to the same Chrome: the second picks up the first one's tab."""
    import subprocess
    import time
    import urllib.request
    from playwright.sync_api import sync_playwright
    from visor.config import settings

    if browser._playwright_context is not None:  # only one sync Playwright may run per thread
        exe = browser._playwright_context.chromium.executable_path
    else:
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
    chrome = subprocess.Popen([exe, "--headless=new", "--remote-debugging-port=9377",
                               f"--user-data-dir={tmp_path / 'profile'}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen("http://127.0.0.1:9377/json/version", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        saved_state = (browser._playwright_context, browser._browser_context, browser._page, browser._owns_browser)
        browser._browser_context = browser._page = None   # keep the one sync Playwright this thread may run
        monkeypatch.setattr(browser, "_remembered", None)
        monkeypatch.setattr(settings, "attach", True)
        monkeypatch.setattr(settings, "cdp_url", "http://127.0.0.1:9377")
        monkeypatch.setattr(browser, "ATTACHED_TAB_FILE", str(tmp_path / "attached_tab.json"))

        def script_exits():
            browser._browser_context.close()  # attached: only disconnects, the tab stays open
            browser._browser_context = browser._page = None
            browser._remembered = None

        browser.navigate(page_url("help.html"))           # script 1
        script_exits()

        assert any("help.html" in p.url for p in browser.tabs())  # first call in script 2 sees every tab
        assert browser.get_page().url.endswith("help.html")     # and works in the same tab
        script_exits()
    finally:
        chrome.terminate()
        browser._playwright_context, browser._browser_context, browser._page, browser._owns_browser = saved_state


@pytest.mark.browser
def test_new_tab_after_close_starts_the_browser_again(live):
    from visor.core import browser
    browser.close(save=False)
    page = browser.new_tab()
    assert page is browser.get_page() and not page.is_closed()
