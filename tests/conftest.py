import os
import sys
import tempfile

import pytest

# Isolate every test run: headless, never attach to the user's Chrome, throwaway workspace,
# no agent waits, no pacing. Must happen before visor is imported.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.update({
    "VISOR_HEADLESS": "1",
    "VISOR_ATTACH": "0",
    "VISOR_WORKSPACE": tempfile.mkdtemp(prefix="visor-test-"),
    "VISOR_AGENT": "0",
    "VISOR_PACE": "0",
    "VISOR_SAVE_SESSION": "0",
    "VISOR_TIMEOUT": "6",
})

PAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages")


def page_url(name: str) -> str:
    return "file://" + os.path.join(PAGES, name)


@pytest.fixture(scope="session")
def live():
    """A headless Chromium plus a working OCR engine, shared by the browser tests."""
    from visor.core import browser, ocr
    try:
        ocr.get_reader()
    except Exception as e:
        pytest.skip(f"No OCR engine available: {e}")
    try:
        browser.init_browser()
    except Exception as e:
        pytest.skip(f"Chromium unavailable: {e}")
    yield browser
    browser.close(save=False)


@pytest.fixture
def shop(live):
    import visor
    visor.goto(page_url("shop.html"))
    return visor


def log_text():
    import visor
    return visor.page().evaluate("document.getElementById('log').textContent")
