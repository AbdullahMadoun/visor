import os
from playwright.sync_api import sync_playwright
from visor.core import PROJECT_ROOT

_playwright_context = None
_browser_context = None
_page = None
_owns_browser = False

def init_browser(headless=False, record_video=False):
    global _playwright_context, _browser_context, _page, _owns_browser
    if _page is not None:
        return _page

    _playwright_context = sync_playwright().start()
    
    # Attempt to connect to an existing Chromium instance to prevent focus stealing/reopening
    if not record_video:
        try:
            print("[BROWSER] Attempting to connect to existing Chromium instance...")
            _browser_context = _playwright_context.chromium.connect_over_cdp("http://localhost:9222", timeout=2000)
            _owns_browser = False
            print("[BROWSER] Connected successfully. No context switch needed!")
        except Exception:
            pass

    if _browser_context is None:
        print(f"[BROWSER] Launching new Playwright Chromium (headless={headless})...")
        _owns_browser = True
        
        browser = _playwright_context.chromium.launch(
            headless=headless,
            args=["--remote-debugging-port=9222", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        
        session_file = os.path.join(PROJECT_ROOT, "visor_workspace", "session.json")
        context_kwargs = {"viewport": {"width": 1440, "height": 900}, "locale": "en-US"}
        if record_video:
            video_dir = os.path.join(PROJECT_ROOT, "visor_workspace", "videos")
            os.makedirs(video_dir, exist_ok=True)
            context_kwargs["record_video_dir"] = video_dir
            print(f"[BROWSER] Video recording enabled. Saving to {video_dir}")
            
        if os.path.exists(session_file):
            print("[BROWSER] Loading persistent session state for video recording...")
            context_kwargs["storage_state"] = session_file
            _browser_context = browser.new_context(**context_kwargs)
        else:
            print("[BROWSER] No session state found, starting clean English context...")
            _browser_context = browser.new_context(**context_kwargs)

    if hasattr(_browser_context, 'contexts') and len(_browser_context.contexts) > 0:
        context = _browser_context.contexts[0]
    elif hasattr(_browser_context, 'pages'):
        context = _browser_context
    else:
        context = _browser_context

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
        
    return _page

def get_page():
    if _page is None:
        return init_browser(headless=False)
    return _page

def navigate(url: str):
    page = get_page()
    print(f"[BROWSER] Navigating to {url}")
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000) # Give DOM time to settle
    return {"ok": True}

def screenshot(save_path: str = None) -> str:
    page = get_page()
    if not save_path:
        temp_dir = os.path.join(PROJECT_ROOT, "visor_workspace", "logs", "failures")
        os.makedirs(temp_dir, exist_ok=True)
        save_path = os.path.join(temp_dir, "temp_screenshot.png")
    
    page.screenshot(path=save_path)
    return save_path

def close():
    global _playwright_context, _browser_context, _page, _owns_browser
    if _owns_browser:
        if _browser_context:
            _browser_context.close()
        if _playwright_context:
            _playwright_context.stop()
    else:
        # Connected via CDP — don't close the user's browser, just detach
        print("[BROWSER] Detaching from CDP session (not closing user's browser).")
        if _page:
            try:
                print("[BROWSER] Closing isolated Visor tab...")
                _page.close()
            except Exception:
                pass
    _page = None
    _browser_context = None
    _playwright_context = None
    _owns_browser = False

def scroll_down(pixels: int = 800, wait_ms: int = 1500):
    """Native scroller to handle infinite lists and lazy loading."""
    page = get_page()
    print(f"[BROWSER] Scrolling down {pixels}px...")
    page.mouse.wheel(0, pixels)
    page.wait_for_timeout(wait_ms)

