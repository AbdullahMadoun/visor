import sys
import random
from visor.core import browser

def click(px: int, py: int):
    """
    CDP mouse click via Playwright.
    Coordinates exactly match the screenshot pixels.
    CDP events bypass Playwright's actionability checks and go through
    Blink's full hit-testing pipeline, making them harder for basic
    bot-detection to distinguish from real user interaction.
    """
    move(px, py)
    press_at(px, py)

def move(px: int, py: int):
    """Move the mouse naturally onto (px, py), then pause like a person would."""
    page = browser.get_page()
    page.mouse.move(px, py, steps=5)
    browser.wait(int(random.uniform(100, 250)))

def press_at(px: int, py: int, clicks: int = 1, button: str = "left"):
    """Mouse down/up at (px, py) without the approach move."""
    page = browser.get_page()
    page.mouse.click(px, py, click_count=clicks, button=button)
    print(f"[CLICK] Native CDP at ({px}, {py})" + (f" x{clicks}" if clicks > 1 else ""))

def double_click(px: int, py: int):
    move(px, py)
    press_at(px, py, clicks=2)

def hover(px: int, py: int):
    move(px, py)
    print(f"[HOVER] ({px}, {py})")

def type_text(text: str, delay: int = 20):
    """Types text using Playwright's keyboard CDP."""
    page = browser.get_page()
    page.keyboard.type(text, delay=delay)
    print(f"[TYPE] Typed {len(text)} characters")

def press(key: str):
    page = browser.get_page()
    page.keyboard.press(key)
    print(f"[PRESS] {key}")

def select_all():
    """Select everything in the focused field (Cmd+A on macOS, Ctrl+A elsewhere)."""
    browser.get_page().keyboard.press("Meta+A" if sys.platform == "darwin" else "Control+A")

def human_wait(base: float = 4.0, noise: float = 5.0):
    """Noisy human-like delay between profiles (4–9s)."""
    delay = base + random.random() * noise
    print(f"[WAIT] {delay:.1f}s")
    browser.wait(int(delay * 1000))

def short_wait(base: float = 1.5, noise: float = 2.0):
    """Shorter noisy wait for within-page actions."""
    delay = base + random.random() * noise
    browser.wait(int(delay * 1000))
