import sys
import time
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
from visor.core.browser import get_page, navigate, close

def get_jobs():
    page = get_page()
    # Worldwide Remote Easy Apply for Computer Vision
    navigate("https://www.linkedin.com/jobs/search/?keywords=Computer%20Vision%20Engineer&location=Worldwide&f_WRA=true&f_AL=true")
    time.sleep(5)
    
    urls = []
    # Scroll the jobs list to load more
    for _ in range(3):
        page.mouse.wheel(0, 1000)
        time.sleep(2)
        
    job_cards = page.locator(".job-card-container").all()
    print(f"Found {len(job_cards)} job cards on page.")
    
    for card in job_cards:
        if "Easy Apply" in card.inner_text():
            job_id = card.get_attribute("data-job-id")
            if job_id:
                url = f"https://www.linkedin.com/jobs/view/{job_id}"
                if url not in urls:
                    urls.append(url)
            if len(urls) >= 10:
                break
            
    # Write to targets
    targets_path = os.path.join(PROJECT_ROOT, "jobs_targets.csv")
    with open(targets_path, "w") as f:
        f.write("url,status\n")
        for url in urls:
            f.write(f"{url},pending\n")
            
    print(f"Successfully extracted {len(urls)} URLs.")
    close()

if __name__ == "__main__":
    get_jobs()
