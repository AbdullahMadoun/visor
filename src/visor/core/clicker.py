import time
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
    page = browser.get_page()
    
    # Move mouse naturally first
    page.mouse.move(px, py, steps=5)
    time.sleep(random.uniform(0.1, 0.25))
    
    # Click
    page.mouse.click(px, py)
    print(f"[CLICK] Native CDP at ({px}, {py})")

def type_text(text: str):
    """Types text using Playwright's keyboard CDP."""
    page = browser.get_page()
    page.keyboard.type(text, delay=20)
    print(f"[TYPE] Typed {len(text)} characters")

def press(key: str):
    page = browser.get_page()
    page.keyboard.press(key)
    print(f"[PRESS] {key}")

def human_wait(base: float = 4.0, noise: float = 5.0):
    """Noisy human-like delay between profiles (4–9s)."""
    delay = base + random.random() * noise
    print(f"[WAIT] {delay:.1f}s")
    time.sleep(delay)

def short_wait(base: float = 1.5, noise: float = 2.0):
    """Shorter noisy wait for within-page actions."""
    delay = base + random.random() * noise
    time.sleep(delay)
