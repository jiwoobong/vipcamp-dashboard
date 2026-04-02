"""네이버 검색에서 캠핑장 방문자리뷰/블로그리뷰 수 수집.

네이버 검색 결과 페이지에서 방문자리뷰, 블로그리뷰 수를 파싱한다.
(네이버 캠핑장 카테고리는 별점을 표시하지 않는 경우가 많음)
"""
import asyncio
import json
import os
import re
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MERGED_FILE = os.path.join(BASE_DIR, "merged_camps.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "naver_reviews.json")


async def search_naver(page, camp_name):
    """네이버 검색 결과에서 방문자리뷰/블로그리뷰/별점 추출."""
    url = f"https://search.naver.com/search.naver?query={camp_name}"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        result = await page.evaluate("""
            () => {
                const text = document.body.innerText;
                const out = {
                    rating: null,
                    visitor_review: 0,
                    blog_review: 0,
                    place_name: null,
                    has_place_card: false
                };

                // 플레이스 카드 존재 여부
                const placeCard = document.querySelector('[class*="place_section"], [class*="sc_new"], [data-pkid], [class*="fst_section"]');
                if (placeCard) out.has_place_card = true;

                // 방문자 리뷰
                const vm = text.match(/방문자\\s*리뷰\\s*([\\d,]+)/);
                if (vm) out.visitor_review = parseInt(vm[1].replace(/,/g, ''));

                // 블로그 리뷰
                const bm = text.match(/블로그\\s*리뷰\\s*([\\d,]+)/);
                if (bm) out.blog_review = parseInt(bm[1].replace(/,/g, ''));

                // 별점 (있는 경우)
                const sm = text.match(/별점\\s*(\\d+\\.\\d+)/);
                if (sm) out.rating = parseFloat(sm[1]);

                // N.N점 패턴 (플레이스 카드 내)
                if (!out.rating) {
                    const pm = text.match(/(\\d+\\.\\d+)점\\s/);
                    if (pm && parseFloat(pm[1]) <= 5.0) out.rating = parseFloat(pm[1]);
                }

                // 플레이스명
                const lines = text.split('\\n');
                for (const line of lines) {
                    if (line.includes('캠핑') || line.includes('글램핑') || line.includes('카라반')) {
                        if (line.length < 50 && !line.includes('http')) {
                            out.place_name = line.trim();
                            break;
                        }
                    }
                }

                return out;
            }
        """)

        return result

    except Exception as e:
        print(f"  에러: {e}")
        return None


async def main():
    with open(MERGED_FILE, encoding="utf-8") as f:
        camps = json.load(f)

    results = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = await context.new_page()

        for idx, camp in enumerate(camps):
            kakao_id = camp["kakao_id"]
            name = camp["name"]
            print(f"[{idx+1}/{len(camps)}] {name}")

            result = await search_naver(page, name)

            if result:
                record = {
                    "kakao_id": kakao_id,
                    "name": name,
                    "naver_rating": result.get("rating"),
                    "naver_visitor_review": result.get("visitor_review", 0),
                    "naver_blog_review": result.get("blog_review", 0),
                    "naver_place_name": result.get("place_name"),
                    "has_naver_place": result.get("has_place_card", False),
                }
                print(f"  -> ★{result.get('rating', '-')} | 방문자 {result.get('visitor_review', 0)} | 블로그 {result.get('blog_review', 0)}")
            else:
                record = {
                    "kakao_id": kakao_id,
                    "name": name,
                    "naver_rating": None,
                    "naver_visitor_review": 0,
                    "naver_blog_review": 0,
                    "naver_place_name": None,
                    "has_naver_place": False,
                }
                print(f"  -> 검색 실패")

            results[kakao_id] = record

            if (idx + 1) % 5 == 0:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(results.values()), f, ensure_ascii=False, indent=2)
                print(f"  저장: {len(results)}개")

            await asyncio.sleep(1.5)

        await browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(results.values()), f, ensure_ascii=False, indent=2)

    has_rating = sum(1 for r in results.values() if r.get("naver_rating"))
    has_visitor = sum(1 for r in results.values() if r.get("naver_visitor_review", 0) > 0)
    has_blog = sum(1 for r in results.values() if r.get("naver_blog_review", 0) > 0)
    print(f"\n완료! 총 {len(results)}개")
    print(f"별점: {has_rating}개 | 방문자리뷰: {has_visitor}개 | 블로그리뷰: {has_blog}개")
    print(f"저장: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
