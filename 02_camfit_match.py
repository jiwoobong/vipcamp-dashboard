import asyncio
import json
import re
import time
from playwright.async_api import async_playwright

KAKAO_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/kakao_camps.json"
OUTPUT_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/camfit_matched.json"
PROGRESS_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/camfit_progress.json"

def clean_name(name):
    name = re.sub(r'\s*(캠핑장|글램핑|오토캠핑장|카라반|바베큐장|셀프바베큐장)\s*', '', name)
    name = re.sub(r'[&\-·]', ' ', name)
    return name.strip()

def make_search_keywords(place_name):
    keywords = [place_name]
    cleaned = clean_name(place_name)
    if cleaned != place_name:
        keywords.append(cleaned)
    words = place_name.split()
    if len(words) >= 2:
        keywords.append(words[0])
    return keywords

async def main():
    with open(KAKAO_FILE, encoding="utf-8") as f:
        kakao_camps = json.load(f)

    # Load progress
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            results = json.load(f)
        done_ids = {r["kakao_id"] for r in results}
        print(f"Resuming: {len(done_ids)} already done")
    except:
        results = []
        done_ids = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Navigate to camfit first to get cookies/CF clearance
        print("Navigating to camfit.co.kr for CF clearance...")
        await page.goto("https://camfit.co.kr", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        print("CF clearance done")

        for idx, camp in enumerate(kakao_camps):
            kakao_id = camp["id"]
            if kakao_id in done_ids:
                continue

            name = camp["place_name"]
            print(f"\n[{idx+1}/{len(kakao_camps)}] Searching: {name}")

            matched = None
            keywords = make_search_keywords(name)

            for kw in keywords:
                try:
                    search_url = f"https://api.camfit.co.kr/v1/search?search={kw}&skip=0&limit=10"
                    search_result = await page.evaluate(f"""
                        async () => {{
                            const resp = await fetch("{search_url}");
                            return await resp.json();
                        }}
                    """)

                    camps_list = search_result if isinstance(search_result, list) else search_result.get("data", search_result.get("camps", search_result.get("items", [])))

                    if not isinstance(camps_list, list):
                        # Try to find camps in the response
                        if isinstance(search_result, dict):
                            for key in search_result:
                                if isinstance(search_result[key], list) and len(search_result[key]) > 0:
                                    camps_list = search_result[key]
                                    break

                    if camps_list and isinstance(camps_list, list):
                        for c in camps_list:
                            cname = c.get("name", c.get("campName", ""))
                            if not cname:
                                continue
                            # Fuzzy match: check if significant overlap
                            name_lower = name.replace(" ", "").lower()
                            cname_lower = cname.replace(" ", "").lower()
                            if name_lower in cname_lower or cname_lower in name_lower or \
                               clean_name(name).replace(" ","").lower() in cname_lower or \
                               cname_lower in clean_name(name).replace(" ","").lower():
                                matched = c
                                print(f"  MATCHED: {cname}")
                                break

                    if matched:
                        break

                except Exception as e:
                    print(f"  Search error for '{kw}': {e}")

                await asyncio.sleep(1)

            # If matched, get detail
            detail = None
            if matched:
                camp_id = matched.get("id", matched.get("_id", matched.get("campId")))
                if camp_id:
                    try:
                        detail_url = f"https://api.camfit.co.kr/v1/camps/{camp_id}"
                        detail = await page.evaluate(f"""
                            async () => {{
                                const resp = await fetch("{detail_url}");
                                return await resp.json();
                            }}
                        """)
                        print(f"  Got detail for camp_id={camp_id}")
                    except Exception as e:
                        print(f"  Detail error: {e}")

                    await asyncio.sleep(2)

            results.append({
                "kakao_id": kakao_id,
                "kakao_name": name,
                "camfit_matched": matched is not None,
                "camfit_search_result": matched,
                "camfit_detail": detail
            })
            done_ids.add(kakao_id)

            # Save progress every 5
            if len(results) % 5 == 0:
                with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                print(f"  Progress saved: {len(results)} camps processed")

            await asyncio.sleep(2)

        await browser.close()

    # Save final
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    matched_count = sum(1 for r in results if r["camfit_matched"])
    print(f"\n=== DONE ===")
    print(f"Total: {len(results)}, Matched: {matched_count}, Unmatched: {len(results)-matched_count}")

asyncio.run(main())
