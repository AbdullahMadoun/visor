import sys
import time
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core import browser

page = browser.get_page()
browser.navigate("https://www.linkedin.com/company/humane/people/")
time.sleep(5)

# Scroll down to load more people
for _ in range(3):
    page.mouse.wheel(0, 1500)
    time.sleep(1.5)

links = page.query_selector_all("a.app-aware-link[href*='/in/']")
urls = []
for link in links:
    url = link.get_attribute("href")
    if url and "/in/" in url:
        # Avoid things like /in/name/overlay/
        if "miniProfile" in url: continue
        
        if url.startswith("http"):
            full_url = url
        else:
            full_url = "https://www.linkedin.com" + url
        
        clean_url = full_url.split("?")[0]
        if clean_url not in urls and clean_url != "https://www.linkedin.com/in/":
            urls.append(clean_url)

print(f"Found {len(urls)} profiles")
targets_path = os.path.join(PROJECT_ROOT, "humane_targets.csv")
with open(targets_path, "w") as f:
    f.write("url,status\n")
    for u in urls[:5]:
        f.write(f"{u},pending\n")
        print(f"Added: {u}")

browser.close()
