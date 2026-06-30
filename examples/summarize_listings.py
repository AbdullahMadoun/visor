import json

with open("haraj_40_listings.json", "r", encoding="utf-8") as f:
    listings = json.load(f)

# Let's filter out duplicates based on title and print them out clearly
seen_titles = set()
unique_listings = []

for item in listings:
    if item['title'] not in seen_titles:
        seen_titles.add(item['title'])
        unique_listings.append(item)

print(f"Total Unique Listings: {len(unique_listings)}\n")
for i, item in enumerate(unique_listings):
    title = item['title']
    url = item['url']
    desc = item['description'][:150].replace('\n', ' ')
    print(f"{i+1}. {title}\n   URL: {url}\n   Desc: {desc}...\n")
