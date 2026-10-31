"""
Runtime settings for visor.

Every setting can come from an environment variable (read once, at import)
or be changed while running with visor.configure(...).
"""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_list(name: str) -> list:
    return [part.strip() for part in _env(name, "").split(",") if part.strip()]


def _env_pace() -> tuple:
    # "4-9" → (4.0, 9.0); "0" → no pause between targets
    raw = _env("VISOR_PACE", "4-9")
    try:
        low, _, high = raw.partition("-")
        return (float(low), float(high or low))
    except ValueError:
        return (4.0, 9.0)


@dataclass
class Settings:
    # Browser
    headless: bool = field(default_factory=lambda: _env_bool("VISOR_HEADLESS", False))
    attach: bool = field(default_factory=lambda: _env_bool("VISOR_ATTACH", True))  # reuse a Chrome already running with a debug port
    cdp_url: str = field(default_factory=lambda: _env("VISOR_CDP_URL", "http://localhost:9222"))
    viewport: tuple = (1440, 900)
    nav_timeout: float = field(default_factory=lambda: _env_float("VISOR_NAV_TIMEOUT", 30.0))
    save_session: bool = field(default_factory=lambda: _env_bool("VISOR_SAVE_SESSION", True))  # write session.json when visor closes its own browser
    follow_tabs: bool = True  # switch to a tab that a click opens

    # Perception
    ocr_engine: str = field(default_factory=lambda: _env("VISOR_OCR_ENGINE", "auto"))  # auto | livetext | vision | easyocr
    ocr_langs: list = field(default_factory=lambda: _env_list("VISOR_OCR_LANGS"))  # e.g. ["en", "ar"]
    min_conf: float = 0.5

    # Actions
    timeout: float = field(default_factory=lambda: _env_float("VISOR_TIMEOUT", 8.0))  # how long click/wait_for keep looking
    scroll_search: bool = True  # scroll to find text that is off screen
    scale: float = field(default_factory=lambda: _env_float("VISOR_SCALE", 2.0))  # pixel density of browsers visor launches
    max_scrolls: int = 8
    dom_fallback: bool = True  # last resort: find icon-only buttons by accessible name
    auto_dismiss: bool = True  # close cookie banners / overlays that block a click
    verify_clicks: bool = True  # check that a click changed something, retry once if not

    # Runner / self-healing
    agent: bool = field(default_factory=lambda: _env_bool("VISOR_AGENT", True))  # wait for fix.json on unknown failures
    agent_timeout: float = field(default_factory=lambda: _env_float("VISOR_AGENT_TIMEOUT", 600.0))
    ocr_only: bool = field(default_factory=lambda: _env_bool("VISOR_OCR_ONLY", False))  # no visor.page(): your code sees only OCR text
    controls: bool = field(default_factory=lambda: _env_bool("VISOR_CONTROLS", True))  # list on-screen controls in failure.json
    review: bool = field(default_factory=lambda: _env_bool("VISOR_REVIEW", False))  # proven fixes wait for `visor tree --review`
    heal: bool = False  # high-level actions escalate to the strategy tree / agent (on while run_flow runs)
    human: bool = field(default_factory=lambda: _env_bool("VISOR_HUMAN", True))  # pause for you on captchas / 2FA
    human_timeout: float = field(default_factory=lambda: _env_float("VISOR_HUMAN_TIMEOUT", 900.0))
    flow: str = ""  # strategy-tree key of the running flow
    pace: tuple = field(default_factory=_env_pace)  # seconds to pause between targets (min, max)


settings = Settings()


def configure(**changes) -> Settings:
    """Change settings at runtime, e.g. configure(headless=True, timeout=15)."""
    for key, value in changes.items():
        if not hasattr(settings, key):
            raise TypeError(f"Unknown visor setting: {key!r}")
        setattr(settings, key, value)
    return settings
