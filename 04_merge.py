import json

KAKAO_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/kakao_camps.json"
CAMFIT_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/camfit_matched.json"
REVIEWS_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/kakao_reviews.json"
OUTPUT_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/merged_camps.json"

with open(KAKAO_FILE, encoding="utf-8") as f:
    kakao = json.load(f)
with open(CAMFIT_FILE, encoding="utf-8") as f:
    camfit = json.load(f)
with open(REVIEWS_FILE, encoding="utf-8") as f:
    reviews = json.load(f)

camfit_by_id = {c["kakao_id"]: c for c in camfit}
reviews_by_id = {r["kakao_id"]: r for r in reviews}

merged = []
for camp in kakao:
    kid = camp["id"]
    dist_m = int(camp.get("distance", 0))

    entry = {
        "name": camp["place_name"],
        "address": camp.get("road_address_name") or camp.get("address_name", ""),
        "phone": camp.get("phone", ""),
        "distance_km": round(dist_m / 1000, 1),
        "kakao_id": kid,
        "place_url": camp.get("place_url", ""),
        "category": camp.get("category_name", ""),
        "lat": float(camp.get("y", 0)),
        "lng": float(camp.get("x", 0)),
    }

    # Reviews from kakao
    rev = reviews_by_id.get(kid, {})
    entry["review_count"] = rev.get("review_count")
    entry["rating"] = rev.get("rating")

    # Camfit data
    cf = camfit_by_id.get(kid, {})
    entry["camfit_matched"] = cf.get("camfit_matched", False)

    if cf.get("camfit_matched"):
        detail = cf.get("camfit_detail", {})
        if detail and isinstance(detail, dict):
            # Extract key info from camfit detail
            entry["camfit_id"] = detail.get("_id", detail.get("id", ""))
            entry["camfit_name"] = detail.get("name", "")

            # Pricing
            zones = detail.get("zones", [])
            prices = []
            site_count = 0
            for z in zones:
                sites = z.get("sites", [])
                site_count += len(sites)
                for s in sites:
                    price = s.get("price", s.get("defaultPrice", 0))
                    if price:
                        prices.append({
                            "zone": z.get("name", ""),
                            "site": s.get("name", ""),
                            "price": price
                        })

            entry["site_count"] = site_count
            entry["prices"] = prices
            entry["min_price"] = min((p["price"] for p in prices), default=None)
            entry["max_price"] = max((p["price"] for p in prices), default=None)

            # Policy
            policy = detail.get("policy", {})
            if isinstance(policy, dict):
                entry["policy"] = {
                    "checkIn": policy.get("checkIn", ""),
                    "checkOut": policy.get("checkOut", ""),
                    "cancelPolicy": policy.get("cancelPolicy", policy.get("cancel", "")),
                }
            else:
                entry["policy"] = str(policy) if policy else None

            # Facilities
            entry["facilities"] = detail.get("facilities", detail.get("facility", []))

            # Basic info
            entry["camfit_address"] = detail.get("address", "")
            entry["camfit_description"] = (detail.get("description", "") or "")[:200]
        else:
            search = cf.get("camfit_search_result", {})
            if search:
                entry["camfit_id"] = search.get("id", search.get("_id", ""))
                entry["camfit_name"] = search.get("name", "")
    else:
        entry["camfit_id"] = None
        entry["site_count"] = None
        entry["prices"] = None
        entry["min_price"] = None
        entry["max_price"] = None
        entry["policy"] = None
        entry["facilities"] = None

    merged.append(entry)

# Sort by distance
merged.sort(key=lambda x: x["distance_km"])

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)

print(f"Merged {len(merged)} camps -> {OUTPUT_FILE}")
print(f"\nCamfit matched: {sum(1 for m in merged if m['camfit_matched'])}")
print(f"With rating: {sum(1 for m in merged if m.get('rating'))}")
print(f"With reviews: {sum(1 for m in merged if m.get('review_count'))}")

# Summary table
print(f"\n{'='*80}")
print(f"{'Name':<30} {'Dist':>5} {'Rating':>6} {'Reviews':>7} {'Camfit':>6} {'Price':>10}")
print(f"{'='*80}")
for m in merged:
    price_str = ""
    if m.get("min_price"):
        price_str = f"{m['min_price']:,}"
    print(f"{m['name'][:30]:<30} {m['distance_km']:>5.1f} {str(m.get('rating','-')):>6} {str(m.get('review_count','-')):>7} {'✓' if m['camfit_matched'] else '-':>6} {price_str:>10}")
