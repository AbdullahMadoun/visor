"""
apply_loop.py — Strategic Easy Apply Job Loop

Architecture:
  1. Search LinkedIn Easy Apply jobs via URL filter (f_AL=true = Easy Apply only)
  2. Extract job card URLs using DOM (job cards only, not full DOM scraping)
  3. Deduplicate across runs using results.csv
  4. Run linkedin_apply flow via run.py subprocess
  5. Loop until 10 real successes

Query rotation: CV → AI Eng → ML Eng → NLP Eng → Data Scientist (remote/worldwide)
"""

import sys
import time
import os
import csv
import json
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core.browser import get_page, navigate

RESULTS_CSV = os.path.join(PROJECT_ROOT, "logs", "results.csv")
JOBS_TARGETS = os.path.join(PROJECT_ROOT, "jobs_targets.csv")
GOAL = 10

QUERIES = [
    "https://www.linkedin.com/jobs/search/?keywords=Computer%20Vision%20Engineer&f_WT=2&f_AL=true&sortBy=R",
    "https://www.linkedin.com/jobs/search/?keywords=AI%20Engineer&f_WT=2&f_AL=true&sortBy=R",
    "https://www.linkedin.com/jobs/search/?keywords=Machine%20Learning%20Engineer&f_WT=2&f_AL=true&sortBy=R",
    "https://www.linkedin.com/jobs/search/?keywords=NLP%20Engineer&f_WT=2&f_AL=true&sortBy=R",
    "https://www.linkedin.com/jobs/search/?keywords=Data%20Scientist&f_WT=2&f_AL=true&sortBy=R",
    "https://www.linkedin.com/jobs/search/?keywords=Deep%20Learning%20Engineer&f_WT=2&f_AL=true&sortBy=R",
]


def count_successes():
    if not os.path.exists(RESULTS_CSV):
        return 0
    with open(RESULTS_CSV) as f:
        reader = csv.DictReader(f)
        return sum(
            1 for row in reader
            if row.get("status") == "success"
            and "example.com" not in row.get("url", "")
        )


def load_seen_urls():
    seen = set()
    for path in [RESULTS_CSV, JOBS_TARGETS]:
        if not os.path.exists(path):
            continue
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("url", "").strip()
                if url:
                    seen.add(url)
    return seen


def harvest_job_urls(page, seen_urls, needed=5):
    """
    Harvest Easy Apply job card URLs from search results.

    Proven selectors (from live DOM probe 2026-06-24):
    - .job-card-container  → 7 cards found ✅
    - a[href*='/jobs/view/'] → 9 links found ✅
    - li.jobs-search-results__list-item → 0 (wrong, don't use) ❌

    Capped at `needed` per call (default 5). Rotate queries externally to accumulate more.
    Stall detection: if count doesn't grow after a scroll, stop early.
    """
    collected = []
    scroll_attempts = 0
    max_scrolls = 6
    last_count = -1  # stall detection

    while len(collected) < needed and scroll_attempts < max_scrolls:
        # Stall detection: if last scroll added nothing, stop
        if scroll_attempts > 0 and len(collected) == last_count:
            print(f"  [HARVEST] No new cards found after scroll — stopping early")
            break
        last_count = len(collected)
        # Strategy 1: job-card-container with Easy Apply inner text
        try:
            cards = page.query_selector_all(".job-card-container")
            for card in cards:
                try:
                    card_text = card.inner_text()
                    if "Easy Apply" not in card_text:
                        continue
                    # Find the job link inside this card
                    link = card.query_selector("a[href*='/jobs/view/']")
                    if not link:
                        continue
                    href = link.get_attribute("href") or ""
                    if "/jobs/view/" in href:
                        job_id = href.split("/jobs/view/")[1].split("/")[0].split("?")[0]
                        url = f"https://www.linkedin.com/jobs/view/{job_id}"
                        if url not in seen_urls and url not in collected:
                            collected.append(url)
                            print(f"  [HARVEST] Found: {url}")
                            if len(collected) >= needed:
                                break
                except Exception:
                    continue
        except Exception as e:
            print(f"  [HARVEST] card selector failed: {e}")

        # Strategy 2: fallback — all /jobs/view/ links on page (already filtered by f_AL=true)
        if not collected:
            try:
                links = page.query_selector_all("a[href*='/jobs/view/']")
                for link in links:
                    href = link.get_attribute("href") or ""
                    if "/jobs/view/" in href:
                        job_id = href.split("/jobs/view/")[1].split("/")[0].split("?")[0]
                        url = f"https://www.linkedin.com/jobs/view/{job_id}"
                        if url not in seen_urls and url not in collected:
                            collected.append(url)
                            print(f"  [HARVEST-fallback] Found: {url}")
                            if len(collected) >= needed:
                                break
            except Exception as e:
                print(f"  [HARVEST] link fallback failed: {e}")

        if len(collected) >= needed:
            break

        # Scroll to load more cards
        page.mouse.wheel(0, 2000)
        time.sleep(3)
        scroll_attempts += 1
        print(f"  [HARVEST] Scroll {scroll_attempts}/{max_scrolls}, collected {len(collected)} so far")

        # Click "Show more results" if present
        try:
            show_more = page.query_selector(
                "button.infinite-scroller__show-more-button, "
                "button[aria-label*='more results'], "
                "button[aria-label*='Show more']"
            )
            if show_more:
                show_more.click()
                time.sleep(3)
                print("  [HARVEST] Clicked 'Show more results'")
        except Exception:
            pass

    print(f"[HARVEST] Done — collected {len(collected)} new job URLs")
    return collected


def write_targets(urls):
    """Write or append new URLs to jobs_targets.csv."""
    existing = load_seen_urls()
    new_urls = [u for u in urls if u not in existing]
    if not new_urls:
        return 0
    
    mode = "a" if os.path.exists(JOBS_TARGETS) else "w"
    with open(JOBS_TARGETS, mode) as f:
        if mode == "w":
            f.write("url,status\n")
        for u in new_urls:
            f.write(f"{u},pending\n")
    return len(new_urls)


def run_apply_batch(target_file=JOBS_TARGETS):
    """Fire the visor linkedin_apply flow and wait for completion."""
    print(f"\n[LOOP] Launching linkedin_apply on {target_file}...")
    result = subprocess.run(
        [
            "python3", "-u", "run.py",
            "--flow", "linkedin_apply",
            "--targets", target_file,
            "--retries", "2"
        ],
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": PROJECT_ROOT}
    )
    return result.returncode


def main():
    os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)

    query_idx = 0
    page = get_page()

    while True:
        successes = count_successes()
        print(f"\n[LOOP] Progress: {successes}/{GOAL} successful applications")

        if successes >= GOAL:
            print(f"[LOOP] 🎉 GOAL REACHED — {GOAL} jobs applied to!")
            break

        # Harvest 5 per query batch, rotate queries to reach goal
        seen_urls = load_seen_urls()
        query = QUERIES[query_idx % len(QUERIES)]
        print(f"[LOOP] Searching query {query_idx % len(QUERIES) + 1}/{len(QUERIES)}: {query}")

        navigate(query)
        time.sleep(5)

        new_urls = harvest_job_urls(page, seen_urls, needed=5)

        if not new_urls:
            print(f"[LOOP] No new Easy Apply jobs on query {query_idx % len(QUERIES) + 1}. Proceeding to apply to existing pending targets...")
            query_idx += 1
            if query_idx % len(QUERIES) == 0:
                print("[LOOP] All queries exhausted. Will retry after apply batch.")
        else:
            written = write_targets(new_urls)
            print(f"[LOOP] Harvested {len(new_urls)} new URLs, wrote {written} to targets CSV")

        run_apply_batch()

        # Short break between batches to avoid rate-limiting
        time.sleep(10)
        query_idx += 1


if __name__ == "__main__":
    main()
