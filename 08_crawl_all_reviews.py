"""캠핏/카카오/네이버 리뷰 텍스트 통합 크롤링.

3개 소스에서 실제 리뷰 텍스트를 수집하여 all_reviews.json에 저장.
"""
import asyncio
import json
import os
import re
import urllib.parse
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MERGED_FILE = os.path.join(BASE_DIR, "merged_camps.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "all_reviews.json")


# ============ CAMFIT REVIEWS ============
async def crawl_camfit_reviews(page, camfit_id, camp_name):
    """캠핏 API에서 리뷰 수집."""
    if not camfit_id:
        return []
    try:
        url = f"https://api.camfit.co.kr/v1/reviews?campId={camfit_id}&skip=0&limit=50"
        resp = await page.evaluate(f"""
            async () => {{
                try {{
                    const r = await fetch("{url}");
                    if (!r.ok) return [];
                    return await r.json();
                }} catch(e) {{ return []; }}
            }}
        """)
        if not isinstance(resp, list):
            resp = resp.get("data", resp.get("reviews", []))

        reviews = []
        for r in resp:
            text = r.get("content") or r.get("text") or r.get("comment") or ""
            rating = r.get("rating") or r.get("score") or r.get("star")
            user = r.get("user", {})
            nickname = user.get("nickname", "") if isinstance(user, dict) else ""
            date = r.get("createdAt") or r.get("date") or ""
            reviews.append({
                "source": "camfit",
                "text": text.strip(),
                "rating": rating,
                "author": nickname,
                "date": date[:10] if date else "",
            })
        return reviews
    except Exception as e:
        print(f"    캠핏 리뷰 에러 ({camp_name}): {e}")
        return []


# ============ KAKAO REVIEWS ============
async def crawl_kakao_reviews(page_kakao, kakao_id, camp_name):
    """카카오맵 place 페이지에서 리뷰 텍스트 수집."""
    try:
        url = f"http://place.map.kakao.com/{kakao_id}"
        await page_kakao.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        text = await page_kakao.evaluate("() => document.body.innerText")
        lines = text.split("\n")

        reviews = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # 리뷰 패턴: "후기 N별점평균 N.N팔로워 N" 다음에 날짜, 그 다음에 리뷰 텍스트
            if re.match(r"후기\s*\d+별점평균", line):
                # 날짜 찾기
                date_str = ""
                review_text = ""
                for j in range(i+1, min(i+5, len(lines))):
                    dl = lines[j].strip()
                    if re.match(r"\d{4}\.\d{2}\.\d{2}", dl):
                        date_str = dl.replace(".", "-").rstrip("-")
                    elif len(dl) > 15 and not re.match(r"(좋아요|후기|별점|팔로워|더보기)", dl):
                        review_text = dl
                        break

                if review_text:
                    # 별점 추출
                    rm = re.search(r"별점평균\s*([\d.]+)", line)
                    rating = float(rm.group(1)) if rm else None
                    reviews.append({
                        "source": "kakao",
                        "text": review_text[:500],
                        "rating": rating,
                        "author": "",
                        "date": date_str,
                    })
            i += 1

        # 블로그 리뷰도 수집 (카카오맵에 임베딩된 블로그 글)
        for i, line in enumerate(lines):
            line = line.strip()
            if len(line) > 50 and len(line) < 500:
                # 블로그 리뷰 패턴: 긴 텍스트 + 날짜
                prev_lines = [lines[j].strip() for j in range(max(0,i-3), i)]
                next_lines = [lines[j].strip() for j in range(i+1, min(len(lines), i+4))]
                has_date = any(re.match(r"\d{4}\.\d{2}\.\d{2}", l) for l in prev_lines + next_lines)
                has_camp = camp_name.replace(" ", "") in "".join(prev_lines + [line]).replace(" ", "")

                if has_date and ("캠핑" in line or "카라반" in line or camp_name[:4] in line):
                    if not any(r["text"][:30] == line[:30] for r in reviews):
                        date_found = ""
                        for l in next_lines:
                            dm = re.match(r"(\d{4}\.\d{2}\.\d{2})", l)
                            if dm:
                                date_found = dm.group(1).replace(".", "-")
                                break
                        reviews.append({
                            "source": "kakao_blog",
                            "text": line[:500],
                            "rating": None,
                            "author": "",
                            "date": date_found,
                        })

        return reviews
    except Exception as e:
        print(f"    카카오 리뷰 에러 ({camp_name}): {e}")
        return []


# ============ NAVER REVIEWS ============
async def crawl_naver_reviews(page_naver, camp_name):
    """네이버 검색에서 방문자 리뷰 텍스트 수집."""
    try:
        query = urllib.parse.quote(camp_name)
        url = f"https://search.naver.com/search.naver?query={query}"
        await page_naver.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(2)

        # 방문자 리뷰 탭이 있으면 클릭
        try:
            review_tab = await page_naver.query_selector('a[href*="ugc"], a:has-text("방문자리뷰"), [class*="tab"]:has-text("리뷰")')
            if review_tab:
                await review_tab.click()
                await asyncio.sleep(2)
        except:
            pass

        text = await page_naver.evaluate("() => document.body.innerText")
        lines = text.split("\n")

        reviews = []

        # 방문자 리뷰 텍스트 패턴 수집
        for i, line in enumerate(lines):
            line = line.strip()
            # 방문자 리뷰는 보통 긴 텍스트(30자+)로 나옴
            if len(line) > 30 and len(line) < 600:
                # 리뷰가 아닌 것 필터링
                skip_patterns = ["http", "검색결과", "네이버", "더보기", "공유하기", "신고",
                                 "www.", "블로그", "카페", "뉴스", "지도", "이미지",
                                 "관광사업자", "제공 한국", "예약은...아래", "클릭클릭"]
                if any(p in line for p in skip_patterns):
                    continue

                # 캠핑 관련 키워드 확인
                camp_keywords = ["캠핑", "카라반", "텐트", "사이트", "체크인", "글램핑",
                                 "불멍", "바베큐", "계곡", "숙박", "캠프", camp_name[:3]]
                if any(k in line for k in camp_keywords):
                    # 날짜 찾기
                    date_found = ""
                    for j in range(max(0, i-2), min(len(lines), i+3)):
                        dm = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", lines[j])
                        if dm:
                            date_found = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
                            break

                    if not any(r["text"][:30] == line[:30] for r in reviews):
                        reviews.append({
                            "source": "naver",
                            "text": line[:500],
                            "rating": None,
                            "author": "",
                            "date": date_found,
                        })

        return reviews[:15]  # 최대 15개
    except Exception as e:
        print(f"    네이버 리뷰 에러 ({camp_name}): {e}")
        return []


# ============ MAIN ============
async def main():
    with open(MERGED_FILE, encoding="utf-8") as f:
        camps = json.load(f)

    # 기존 결과 로드
    results = {}
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        for item in existing:
            if item.get("reviews"):
                results[item["kakao_id"]] = item
        print(f"기존 {len(results)}개 로드됨")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # 3개 페이지 준비
        ctx_camfit = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        ctx_kakao = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", locale="ko-KR")
        ctx_naver = await browser.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", locale="ko-KR")

        page_camfit = await ctx_camfit.new_page()
        page_kakao = await ctx_kakao.new_page()
        page_naver = await ctx_naver.new_page()

        # CF clearance for camfit
        print("캠핏 CF 우회 중...")
        await page_camfit.goto("https://camfit.co.kr", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)
        print("준비 완료!\n")

        for idx, camp in enumerate(camps):
            kakao_id = camp["kakao_id"]
            if kakao_id in results:
                continue

            name = camp["name"]
            camfit_id = camp.get("camfit_id")
            print(f"[{idx+1}/{len(camps)}] {name}")

            # 3개 소스 병렬 수집
            camfit_reviews, kakao_reviews, naver_reviews = await asyncio.gather(
                crawl_camfit_reviews(page_camfit, camfit_id, name),
                crawl_kakao_reviews(page_kakao, kakao_id, name),
                crawl_naver_reviews(page_naver, name),
            )

            all_reviews = camfit_reviews + kakao_reviews + naver_reviews

            record = {
                "kakao_id": kakao_id,
                "name": name,
                "review_summary": {
                    "camfit": len(camfit_reviews),
                    "kakao": len(kakao_reviews),
                    "naver": len(naver_reviews),
                    "total": len(all_reviews),
                },
                "reviews": all_reviews,
            }
            results[kakao_id] = record

            cf = len(camfit_reviews)
            kk = len(kakao_reviews)
            nv = len(naver_reviews)
            print(f"  캠핏:{cf} | 카카오:{kk} | 네이버:{nv} | 합계:{cf+kk+nv}")

            # 5개마다 저장
            if (idx + 1) % 5 == 0:
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(results.values()), f, ensure_ascii=False, indent=2)
                print(f"  저장: {len(results)}개")

            await asyncio.sleep(1)

        await browser.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(list(results.values()), f, ensure_ascii=False, indent=2)

    total_reviews = sum(len(r["reviews"]) for r in results.values())
    print(f"\n완료! {len(results)}개 캠핑장 / 리뷰 총 {total_reviews}개")
    print(f"저장: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
