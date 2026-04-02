import asyncio
import json
import re
from playwright.async_api import async_playwright

KAKAO_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/kakao_camps.json"
OUTPUT_FILE = "/Users/jiwoobong/Desktop/campground-ai-phone/market_data/kakao_reviews.json"

async def main():
    with open(KAKAO_FILE, encoding="utf-8") as f:
        kakao_camps = json.load(f)

    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for idx, camp in enumerate(kakao_camps):
            place_url = camp.get("place_url", "")
            name = camp["place_name"]
            kakao_id = camp["id"]
            print(f"[{idx+1}/{len(kakao_camps)}] {name} -> {place_url}")

            review_count = None
            rating = None

            if place_url:
                try:
                    await page.goto(place_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)

                    # Extract review count and rating from the page
                    page_text = await page.evaluate("document.body.innerText")

                    # Look for rating patterns like "4.3" near review indicators
                    rating_match = re.search(r'(\d+\.\d+)\s*점', page_text)
                    if not rating_match:
                        rating_match = re.search(r'별점\s*(\d+\.\d+)', page_text)
                    if rating_match:
                        rating = float(rating_match.group(1))

                    # Look for review count
                    review_match = re.search(r'리뷰\s*(\d+)', page_text)
                    if not review_match:
                        review_match = re.search(r'후기\s*(\d+)', page_text)
                    if review_match:
                        review_count = int(review_match.group(1))

                    # Also try to get from structured data
                    try:
                        structured = await page.evaluate("""
                            () => {
                                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                                const data = [];
                                scripts.forEach(s => { try { data.push(JSON.parse(s.textContent)); } catch(e) {} });
                                return data;
                            }
                        """)
                        for item in structured:
                            if isinstance(item, dict):
                                if "aggregateRating" in item:
                                    ar = item["aggregateRating"]
                                    if rating is None:
                                        rating = float(ar.get("ratingValue", 0)) or None
                                    if review_count is None:
                                        review_count = int(ar.get("reviewCount", 0)) or None
                    except:
                        pass

                    # Try getting star info from specific selectors
                    try:
                        star_text = await page.evaluate("""
                            () => {
                                const el = document.querySelector('.grade_star, .star_score, .rating, [class*=star], [class*=rating], [class*=score]');
                                return el ? el.textContent : '';
                            }
                        """)
                        if star_text and rating is None:
                            m = re.search(r'(\d+\.?\d*)', star_text)
                            if m:
                                rating = float(m.group(1))
                    except:
                        pass

                    print(f"  rating={rating}, reviews={review_count}")

                except Exception as e:
                    print(f"  Error: {e}")

            results.append({
                "kakao_id": kakao_id,
                "name": name,
                "place_url": place_url,
                "review_count": review_count,
                "rating": rating
            })

            await asyncio.sleep(1)

        await browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    has_rating = sum(1 for r in results if r["rating"] is not None)
    has_reviews = sum(1 for r in results if r["review_count"] is not None)
    print(f"\n=== DONE ===")
    print(f"Total: {len(results)}, With rating: {has_rating}, With reviews: {has_reviews}")

asyncio.run(main())
