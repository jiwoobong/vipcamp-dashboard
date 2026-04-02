import requests
import json
import time

API_KEY = "3dc525172cc43725d798b0d4acaae2a0"
HEADERS = {"Authorization": f"KakaoAK {API_KEY}"}
CENTER_LAT = 37.74
CENTER_LNG = 126.97
RADIUS = 20000  # 20km in meters

all_camps = []
page = 1
while True:
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    params = {
        "query": "캠핑장",
        "x": str(CENTER_LNG),
        "y": str(CENTER_LAT),
        "radius": RADIUS,
        "page": page,
        "size": 15,
        "sort": "distance"
    }
    resp = requests.get(url, headers=HEADERS, params=params)
    data = resp.json()
    docs = data.get("documents", [])
    if not docs:
        break
    all_camps.extend(docs)
    print(f"Page {page}: {len(docs)} results, total so far: {len(all_camps)}")
    if data.get("meta", {}).get("is_end", True):
        break
    page += 1
    time.sleep(0.3)

# deduplicate by id
seen = set()
unique = []
for c in all_camps:
    if c["id"] not in seen:
        seen.add(c["id"])
        unique.append(c)

print(f"\nTotal unique campgrounds: {len(unique)}")

with open("/Users/jiwoobong/Desktop/campground-ai-phone/market_data/kakao_camps.json", "w", encoding="utf-8") as f:
    json.dump(unique, f, ensure_ascii=False, indent=2)

print("Saved to kakao_camps.json")
