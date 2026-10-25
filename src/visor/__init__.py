"""
visor — browser automation that reads the screen.

    import visor

    visor.goto("https://news.ycombinator.com")
    visor.click("login")
    visor.fill("username", "me")
    visor.click("login", expect="logout")

Text is found with OCR, exactly as it looks on screen; the browser is used to
confirm what sits under a pixel, never instead of looking.
"""

__version__ = "0.2.0"

_ACTIONS = (
    "goto", "click", "double_click", "hover", "fill", "type_text", "press_key", "find", "find_all",
    "locate", "press", "see", "wait_for", "wait_gone", "scroll", "scroll_to", "read", "text", "look",
    "dismiss_popups", "current_url", "page", "wait", "check", "select", "upload", "download",
    "human_handshake", "blocker",
)
_BROWSER = ("back", "reload", "settle", "tabs", "switch_tab", "new_tab", "close_tab", "save_session", "close")

_EXPORTS = {name: ("visor.core.actions", name) for name in _ACTIONS}
_EXPORTS.update({name: ("visor.core.browser", name) for name in _BROWSER})
_EXPORTS.update({
    "open": ("visor.core.actions", "goto"),
    "screenshot": ("visor.core.browser", "screenshot"),
    "run_flow": ("visor.core.runner", "run_flow"),
    "configure": ("visor.config", "configure"),
    "settings": ("visor.config", "settings"),
})
for _name in ("VisorError", "TextNotFound", "ElementDisabled", "NavigationError", "Skip", "RestartFlow"):
    _EXPORTS[_name] = ("visor.errors", _name)

__all__ = sorted(_EXPORTS)


def __getattr__(name):
    # Lazy, so `import visor` stays cheap and doesn't start Playwright or OpenCV
    try:
        module_name, attr = _EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module 'visor' has no attribute {name!r}") from None
    import importlib
    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
