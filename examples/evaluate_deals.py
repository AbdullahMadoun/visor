import json
import re

with open("haraj_40_listings.json", "r", encoding="utf-8") as f:
    listings = json.load(f)

seen_titles = set()
unique_listings = []

for item in listings:
    if item['title'] not in seen_titles:
        seen_titles.add(item['title'])
        unique_listings.append(item)

# Sort them based on length of description as a proxy for detail, or look for keywords
scored = []
for item in unique_listings:
    score = 0
    desc = item['description']
    
    if "ايكيا" in desc or "IKEA" in desc.upper():
        score += 10
    if "هيرمان ميلر" in desc or "Aeron" in desc:
        score += 50 # Herman Miller is super high end
    if "نظيف" in desc:
        score += 5
    if "جديد" in desc:
        score += 5
    if "فاخر" in desc:
        score += 10
    if "ريال" in desc:
        score += 5
        
    scored.append((score, item))

scored.sort(key=lambda x: x[0], reverse=True)

with open("best_deals.md", "w", encoding="utf-8") as f:
    f.write("# Top Recommendations\n\n")
    for score, item in scored[:5]:
        f.write(f"## {item['title']}\n")
        f.write(f"**URL**: {item['url']}\n")
        f.write(f"**Score**: {score}\n")
        f.write(f"**Description**:\n{item['description'][:300]}...\n\n")
