"""캠핏 캠핑장 운영지침 크롤링.

캠핏에서 인기 캠핑장 30개의 운영 정보(입퇴실 시간, 금지사항,
부대시설, 특징, 가격 정책 등)를 수집한다.
"""
import asyncio
import json
import os
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "camfit_guidelines.json")

SEARCH_KEYWORDS = [
    "양주", "파주", "포천", "의정부", "동두천",
    "가평", "연천", "남양주", "글램핑", "캠핑장",
]


async def search_camps(page, keyword, limit=10):
    try:
        url = f"https://api.camfit.co.kr/v1/search?search={keyword}&skip=0&limit={limit}"
        result = await page.evaluate(f"""
            async () => {{
                const resp = await fetch("{url}");
                if (!resp.ok) return [];
                return await resp.json();
            }}
        """)

        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ["data", "camps", "items"]:
                if key in result and isinstance(result[key], list):
                    return result[key]
            for key in result:
                if isinstance(result[key], list) and len(result[key]) > 0:
                    return result[key]
        return []
    except Exception as e:
        print(f"  검색 에러 '{keyword}': {e}")
        return []


async def get_camp_detail(page, camp_id):
    try:
        url = f"https://api.camfit.co.kr/v1/camps/{camp_id}"
        detail = await page.evaluate(f"""
            async () => {{
                const resp = await fetch("{url}");
                if (!resp.ok) return null;
                return await resp.json();
            }}
        """)
        return detail
    except Exception as e:
        print(f"  상세 에러 {camp_id}: {e}")
        return None


def extract_guidelines(detail):
    if not detail:
        return None

    d = detail.get("data", detail) if isinstance(detail, dict) else detail

    return {
        "id": d.get("_id") or d.get("id"),
        "name": d.get("name") or d.get("campName", ""),
        "address": d.get("address") or d.get("addr", ""),
        "phone": d.get("phone") or d.get("tel", ""),
        "check_in": d.get("checkIn") or d.get("checkinTime", ""),
        "check_out": d.get("checkOut") or d.get("checkoutTime", ""),
        "site_count": d.get("siteCount") or d.get("totalSite", 0),
        "site_types": d.get("siteTypes") or d.get("types", []),
        "facilities": d.get("facilities") or d.get("facility", []),
        "amenities": d.get("amenities") or [],
        "restrictions": d.get("restrictions") or d.get("notice") or d.get("rule", ""),
        "pet_allowed": d.get("petAllowed") or d.get("isPetAllowed", None),
        "description": d.get("description") or d.get("intro", ""),
        "environment": d.get("environment") or d.get("surroundings", ""),
        "homepage": d.get("homepage") or d.get("website", ""),
        "prices": d.get("prices") or [],
        "seasons": d.get("seasons") or d.get("operatingPeriod", ""),
        "images": [img.get("url", img) if isinstance(img, dict) else img for img in (d.get("images") or d.get("photos") or [])[:5]],
        "tags": d.get("tags") or d.get("keywords") or [],
        "rating": d.get("rating") or d.get("score", 0),
        "review_count": d.get("reviewCount") or d.get("reviews", 0),
    }


async def main():
    # Load existing progress
    collected = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        for item in existing:
            if item and item.get("id"):
                collected[item["id"]] = item
        print(f"기존 {len(collected)}개 로드됨")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        print("CF 우회 중...")
        await page.goto("https://camfit.co.kr", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        print("CF 완료")

        # Collect camp IDs from search
        all_camp_ids = {}
        for kw in SEARCH_KEYWORDS:
            print(f"검색: '{kw}'")
            camps = await search_camps(page, kw, limit=15)
            for c in camps:
                cid = c.get("_id") or c.get("id") or c.get("campId")
                cname = c.get("name") or c.get("campName", "")
                if cid and cid not in collected:
                    all_camp_ids[cid] = cname
            await asyncio.sleep(1)

        print(f"\n신규 수집 대상: {len(all_camp_ids)}개")
        target = dict(list(all_camp_ids.items())[:max(0, 30 - len(collected))])

        for i, (camp_id, camp_name) in enumerate(target.items()):
            print(f"[{i+1}/{len(target)}] {camp_name} ({camp_id})")
            detail = await get_camp_detail(page, camp_id)
            guideline = extract_guidelines(detail)

            if guideline:
                collected[camp_id] = guideline
                print(f"  -> {guideline['name']} | 사이트 {guideline['site_count']} | 체크인 {guideline['check_in']}")

            # Save progress every 5
            if (i + 1) % 5 == 0:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(collected.values()), f, ensure_ascii=False, indent=2)
                print(f"  진행 저장: {len(collected)}개")

            await asyncio.sleep(2)

        await browser.close()

    # Final save
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(collected.values()), f, ensure_ascii=False, indent=2)

    print(f"\n완료! 총 {len(collected)}개 운영지침 저장: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
