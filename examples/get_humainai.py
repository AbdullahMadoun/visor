import sys
import time
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core import browser

page = browser.get_page()
browser.navigate("https://www.linkedin.com/company/humainai/people/")
time.sleep(5)

# Scroll down to load more people
for _ in range(5):
    page.mouse.wheel(0, 1500)
    time.sleep(1.5)

# Playwright evaluate to grab all hrefs that have /in/
urls = page.evaluate("""() => {
    let links = Array.from(document.querySelectorAll("a"));
    return links.map(a => a.href).filter(href => href.includes('/in/') && !href.includes('/overlay/'));
}""")

unique_urls = []
for url in urls:
    clean_url = url.split("?")[0].strip("/")
    if clean_url not in unique_urls and "linkedin.com/in" in clean_url:
        unique_urls.append(clean_url)

# Print out some unique profiles found
print(f"Found {len(unique_urls)} profiles")
targets = []
for u in unique_urls:
    if u != "https://www.linkedin.com/in" and u not in targets:
        targets.append(u)

targets_path = os.path.join(PROJECT_ROOT, "humainai_targets.csv")
with open(targets_path, "w") as f:
    f.write("url,status\n")
    for u in targets[:5]:
        f.write(f"{u},pending\n")
        print(f"Added: {u}")

browser.close()
