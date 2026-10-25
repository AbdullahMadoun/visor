import os
import time
import pathlib
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
from visor.core import WORKSPACE_DIR
from visor.config import settings

_playwright_context = None
_browser_context = None   # the BrowserContext visor launched, or the Browser it attached to over CDP
_page = None
_owns_browser = False
_last_url = None

_popups = []      # tabs opened by visor's pages (target=_blank, window.open)
_tab_stack = []   # tabs we left to follow a popup; we return to them when the popup closes
_watched = set()  # ids of pages with listeners attached
_crashed = set()  # ids of pages whose renderer crashed

SESSION_FILE = os.path.join(WORKSPACE_DIR, "session.json")
SCREENS_DIR = os.path.join(WORKSPACE_DIR, "logs", "screens")


def _cdp_port() -> int:
    try:
        return urlparse(settings.cdp_url).port or 9222
    except ValueError:
        return 9222


def init_browser(headless=None, record_video=False):
    global _playwright_context, _browser_context, _page, _owns_browser
    if _page is not None:
        return get_page()
    if headless is None:
        headless = settings.headless

    try:
        if _playwright_context is None:
            _playwright_context = sync_playwright().start()

        # Attempt to connect to an existing Chromium instance to prevent focus stealing/reopening
        if settings.attach and not record_video:
            try:
                print("[BROWSER] Attempting to connect to existing Chromium instance...")
                _browser_context = _playwright_context.chromium.connect_over_cdp(settings.cdp_url, timeout=2000)
                _owns_browser = False
                print("[BROWSER] Connected successfully. No context switch needed!")
            except Exception:
                pass

        if _browser_context is None:
            print(f"[BROWSER] Launching new Playwright Chromium (headless={headless})...")
            _owns_browser = True

            browser = _playwright_context.chromium.launch(
                headless=headless,
                args=[f"--remote-debugging-port={_cdp_port()}", "--no-sandbox", "--disable-dev-shm-usage"]
            )

            context_kwargs = {"viewport": {"width": settings.viewport[0], "height": settings.viewport[1]}, "locale": "en-US"}
            if record_video:
                video_dir = os.path.join(WORKSPACE_DIR, "videos")
                os.makedirs(video_dir, exist_ok=True)
                context_kwargs["record_video_dir"] = video_dir
                print(f"[BROWSER] Video recording enabled. Saving to {video_dir}")

            if os.path.exists(SESSION_FILE):
                print("[BROWSER] Loading saved session (cookies + storage)...")
                context_kwargs["storage_state"] = SESSION_FILE
            else:
                print("[BROWSER] No session state found, starting clean English context...")
            _browser_context = browser.new_context(**context_kwargs)
    except Exception as e:
        _reset()
        if "Executable doesn't exist" in str(e):
            raise RuntimeError("Chromium is not installed for Playwright. Run: playwright install chromium") from e
        raise

    context = _active_context()

    if _owns_browser:
        if len(context.pages) > 0:
            _page = context.pages[0]
            # Strict Ghost Tabs Cleanup: Close all lingering background tabs
            for p in context.pages[1:]:
                try:
                    p.close()
                except Exception:
                    pass
            try:
                _page.bring_to_front()
            except Exception:
                pass
        else:
            _page = context.new_page()
    else:
        # Connected via CDP -> do NOT hijack existing tabs or clean them up. Spawn an isolated tab.
        print("[BROWSER] Spawning isolated tab for CDP session...")
        _page = context.new_page()

    _watch(_page)
    return _page


def _active_context():
    if _browser_context is None:
        raise RuntimeError("The browser is not running")
    if hasattr(_browser_context, "contexts"):  # attached over CDP: this is a Browser
        return _browser_context.contexts[0] if _browser_context.contexts else _browser_context.new_context()
    return _browser_context


def _on_popup(page):
    _popups.append(page)


def _on_crash(page):
    _crashed.add(id(page))


def _watch(page):
    """Track tabs this page opens and renderer crashes."""
    if page is None or id(page) in _watched:
        return
    _watched.add(id(page))
    page.on("popup", _on_popup)
    page.on("crash", _on_crash)


def _alive(page) -> bool:
    try:
        return page is not None and not page.is_closed() and id(page) not in _crashed
    except Exception:
        return False


def get_page():
    if _page is None:
        return init_browser()
    if not _alive(_page):
        return _recover_page()
    return _page


def _recover_page():
    """The active tab closed or crashed: go back to the tab it came from, or reopen the last URL."""
    global _page
    while _tab_stack:  # e.g. a login popup that closed itself
        previous = _tab_stack.pop()
        if _alive(previous):
            print("[BROWSER] Tab closed; returning to the previous tab.")
            _page = previous
            return _page

    print("[BROWSER] Active tab is gone (closed or crashed). Opening a fresh one...")
    old = _page
    try:
        _page = _active_context().new_page()
    except Exception as e:
        print(f"[BROWSER] Browser connection lost ({e}). Relaunching...")
        _reset()
        return init_browser()
    try:
        old.close()
    except Exception:
        pass
    _watch(_page)
    if _last_url:
        try:
            _page.goto(_last_url, wait_until="domcontentloaded", timeout=int(settings.nav_timeout * 1000))
        except Exception as e:
            print(f"[BROWSER] Could not reopen {_last_url}: {e}")
    return _page


def _reset():
    """Forget every browser handle (the browser died or failed to start)."""
    global _playwright_context, _browser_context, _page, _owns_browser
    if _playwright_context is not None:
        try:
            _playwright_context.stop()
        except Exception:
            pass
    _playwright_context = _browser_context = _page = None
    _owns_browser = False
    _popups.clear()
    _tab_stack.clear()
    _watched.clear()
    _crashed.clear()


def wait(ms: int):
    """
    Pause without launching a browser or failing on a dead tab.
    Uses page.wait_for_timeout when a live page exists so Playwright keeps
    dispatching events; otherwise falls back to time.sleep.
    """
    if _page is not None:
        try:
            if not _page.is_closed():
                _page.wait_for_timeout(ms)
                return
        except Exception:
            pass
    time.sleep(ms / 1000.0)


def normalize_url(url: str) -> str:
    """Add a scheme when it is missing: 'example.com' → 'https://example.com', a local path → file://."""
    url = (url or "").strip()
    if not url:
        raise ValueError("Empty URL")
    if "://" in url or url.startswith(("about:", "data:", "javascript:", "chrome:", "file:")):
        return url
    if os.path.exists(url):
        return pathlib.Path(url).resolve().as_uri()
    if url.startswith(("localhost", "127.0.0.1", "0.0.0.0", "[::1]")):
        return "http://" + url
    return "https://" + url


def navigate(url: str, settle_after: bool = True):
    global _last_url
    page = get_page()
    url = normalize_url(url)
    print(f"[BROWSER] Navigating to {url}")
    timeout_ms = int(settings.nav_timeout * 1000)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except Exception as e:
        # One retry covers transient network errors and tabs that died mid-load
        print(f"[BROWSER] Navigation failed ({e}). Retrying once...")
        wait(1000)
        page = get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    _last_url = url
    if settle_after:
        settle(page)
    return {"ok": True}


def settle(page=None, timeout: float = 6.0) -> bool:
    """Wait (bounded) for the page to finish loading and stop moving."""
    page = page or get_page()
    start = time.monotonic()
    try:
        page.wait_for_load_state("load", timeout=int(timeout * 1000))
    except Exception:
        pass  # slow third-party resources; the visual check below still bounds the wait
    return wait_until_stable(timeout=max(1.0, timeout - (time.monotonic() - start)), page=page)


def wait_until_stable(timeout: float = 4.0, quiet: float = 0.5, interval: float = 0.15, page=None) -> bool:
    """
    Wait until the visible page stops changing (spinners, lazy content, animations).
    Returns False if it was still changing when the timeout ran out.
    """
    import cv2
    import numpy as np
    page = page or get_page()
    deadline = time.monotonic() + timeout
    last, still_since = None, None
    while time.monotonic() < deadline:
        try:
            buf = page.screenshot(type="jpeg", quality=40, scale="css", timeout=5000)
            frame = cv2.imdecode(np.frombuffer(buf, np.uint8), cv2.IMREAD_GRAYSCALE)
            frame = cv2.resize(frame, (160, 100), interpolation=cv2.INTER_AREA)
        except Exception:
            wait(int(interval * 1000))
            continue
        # "Still" = fewer than 8 of 16,000 thumbnail pixels changed noticeably (a blinking caret passes, a spinner doesn't)
        if last is not None and np.count_nonzero(cv2.absdiff(frame, last) > 16) < 8:
            still_since = still_since or time.monotonic()
            if time.monotonic() - still_since >= quiet:
                return True
        else:
            still_since = None
        last = frame
        wait(int(interval * 1000))
    return False


def screenshot(save_path: str = None) -> str:
    page = get_page()
    if not save_path:
        os.makedirs(SCREENS_DIR, exist_ok=True)
        save_path = os.path.join(SCREENS_DIR, "screen.png")

    page.screenshot(path=save_path)
    _record_scale(page, save_path)
    return save_path


def _record_scale(page, path: str):
    """Store the image/CSS scale now, while we still know which page took the screenshot."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return
        vp = page.viewport_size
        css_w = vp["width"] if vp and vp.get("width") else page.evaluate("window.innerWidth")
        from visor.core import ocr
        ocr.register_capture(path, int.from_bytes(head[16:20], "big") / float(css_w))
    except Exception:
        pass


def viewport_size(page=None) -> dict:
    page = page or get_page()
    vp = page.viewport_size
    if vp:
        return vp
    try:
        width, height = page.evaluate("[window.innerWidth, window.innerHeight]")
        return {"width": width, "height": height}
    except Exception:
        return {"width": settings.viewport[0], "height": settings.viewport[1]}


def save_session(path: str = None) -> str:
    """Save cookies + local storage so the next launch starts logged in."""
    path = path or SESSION_FILE
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    _active_context().storage_state(path=tmp)
    os.replace(tmp, path)
    print(f"[BROWSER] Session saved -> {path}")
    return path


# ── Tabs ─────────────────────────────────────────────────────────────────────

def popup_count() -> int:
    return len(_popups)


def follow_popup(since: int, timeout_ms: int = 0):
    """If a tab opened after popup_count() returned `since`, make it the active tab."""
    global _page
    waited = 0
    while len(_popups) <= since and waited < timeout_ms:
        wait(50)
        waited += 50
    fresh = [p for p in _popups[since:] if _alive(p)]
    if not fresh:
        return None
    if _alive(_page):
        _tab_stack.append(_page)
    _page = fresh[-1]
    _watch(_page)
    try:
        _page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    try:
        _page.bring_to_front()
    except Exception:
        pass
    print(f"[BROWSER] Click opened a new tab -> {_page.url}")
    return _page


def tabs() -> list:
    try:
        return [p for p in _active_context().pages if _alive(p)]
    except Exception:
        return []


def switch_tab(which=-1):
    """Make another tab active: an index into tabs(), or text found in its title or URL."""
    global _page
    pages = tabs()
    if isinstance(which, int):
        target = pages[which]
    else:
        needle = str(which).lower()
        matches = [p for p in pages if needle in p.url.lower() or needle in (_title(p) or "").lower()]
        if not matches:
            raise ValueError(f"No open tab matches {which!r}")
        target = matches[-1]
    _page = target
    _watch(_page)
    try:
        _page.bring_to_front()
    except Exception:
        pass
    return _page


def _title(page) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def new_tab(url: str = None):
    global _page
    if _alive(_page):
        _tab_stack.append(_page)
    _page = _active_context().new_page()
    _watch(_page)
    if url:
        navigate(url)
    return _page


def close_tab():
    """Close the active tab and switch to the previous one (or a blank tab if it was the last)."""
    global _page
    old = get_page()
    try:
        old.close()
    except Exception:
        pass
    while _tab_stack:
        previous = _tab_stack.pop()
        if _alive(previous):
            _page = previous
            return _page
    others = tabs()
    _page = others[-1] if others else _active_context().new_page()
    _watch(_page)
    return _page


def back():
    page = get_page()
    page.go_back(wait_until="domcontentloaded", timeout=int(settings.nav_timeout * 1000))
    settle(page)


def reload():
    page = get_page()
    page.reload(wait_until="domcontentloaded", timeout=int(settings.nav_timeout * 1000))
    settle(page)


def close(save=None):
    """Close visor's browser. Saves the session first when visor launched the browser itself."""
    global _playwright_context, _browser_context, _page, _owns_browser
    if save is None:
        save = settings.save_session and _owns_browser
    if save and _browser_context is not None:
        try:
            save_session()
        except Exception as e:
            print(f"[BROWSER] Could not save session: {e}")

    if _page:
        try:
            _page.close()
        except Exception:
            pass
        _page = None

    if _browser_context:
        if _owns_browser:
            try:
                _browser_context.close()
            except Exception:
                pass
        else:
            # Connected via CDP — Browser.close() would tear down the user's browser.
            # Stopping the Playwright driver below detaches without touching it.
            print("[BROWSER] Detaching from CDP session (not closing user's browser).")
        _browser_context = None

    if _playwright_context:
        try:
            _playwright_context.stop()
        except Exception:
            pass
        _playwright_context = None

    _owns_browser = False
    _popups.clear()
    _tab_stack.clear()
    _watched.clear()
    _crashed.clear()

def scroll_down(pixels: int = 800, wait_ms: int = 1500):
    """Native scroller to handle infinite lists and lazy loading."""
    page = get_page()
    print(f"[BROWSER] Scrolling down {pixels}px...")
    page.mouse.wheel(0, pixels)
    page.wait_for_timeout(wait_ms)


def scroll(dy: int = 800, x: int = None, y: int = None, wait_ms: int = 600):
    """Wheel-scroll at (x, y), the viewport centre by default, so an inner pane under the pointer scrolls too."""
    page = get_page()
    vp = viewport_size(page)
    page.mouse.move(vp["width"] / 2 if x is None else x, vp["height"] / 2 if y is None else y)
    page.mouse.wheel(0, dy)
    page.wait_for_timeout(wait_ms)
