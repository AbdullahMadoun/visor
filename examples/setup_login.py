import sys
import os
import time
sys.path.insert(0, os.path.dirname(__file__))

from visor.core import browser

print("="*60)
print("AUTOBOT LOGIN SETUP")
print("="*60)
print("1. Opening Playwright Browser in VISIBLE mode...")
print("2. Please log in to LinkedIn manually.")
print("3. Once you see the LinkedIn feed, press Enter in this terminal.")
print("="*60)

# Init browser with headless=False so user can see it
page = browser.init_browser(headless=False)
page.goto("https://www.linkedin.com/login")

input("\n>>> Press ENTER when you have successfully logged in... <<<")

browser.close()
print("Session saved! Visor can now run in the background (headless).")
