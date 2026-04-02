"""캠핏 예약 현황 주기적 수집 스크립트.

매칭된 5개 캠핑장의 예약 가능일/가격을 수집하여
시간별 추이를 기록한다. cron 등으로 주기 실행.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MATCHED_FILE = os.path.join(BASE_DIR, "camfit_matched.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "reservation_history.jsonl")

CAMFIT_IDS = []


def load_camfit_ids():
    with open(MATCHED_FILE, encoding="utf-8") as f:
        data = json.load(f)
    ids = []
    for item in data:
        if item.get("camfit_matched") and item.get("camfit_detail"):
            detail = item["camfit_detail"]
            camp_id = detail.get("_id") or detail.get("id")
            if camp_id:
                ids.append({
                    "camfit_id": camp_id,
                    "name": item["kakao_name"],
                    "kakao_id": item["kakao_id"],
                })
    return ids


async def fetch_availability(page, camp_id, camp_name):
    today = datetime.now()
    results = []

    for delta in range(0, 30):
        date = today + timedelta(days=delta)
        date_str = date.strftime("%Y-%m-%d")

        try:
            url = f"https://api.camfit.co.kr/v1/camps/{camp_id}/sites?date={date_str}"
            data = await page.evaluate(f"""
                async () => {{
                    const resp = await fetch("{url}");
                    if (!resp.ok) return null;
                    return await resp.json();
                }}
            """)

            if not data:
                continue

            sites = data if isinstance(data, list) else data.get("data", data.get("sites", []))
            if not isinstance(sites, list):
                continue

            total_sites = len(sites)
            available = sum(1 for s in sites if s.get("available") or s.get("isAvailable") or not s.get("isReserved", True))
            reserved = total_sites - available

            prices = [s.get("price", 0) for s in sites if s.get("price")]

            results.append({
                "date": date_str,
                "total_sites": total_sites,
                "available": available,
                "reserved": reserved,
                "occupancy_rate": round(reserved / total_sites * 100, 1) if total_sites > 0 else 0,
                "min_price": min(prices) if prices else None,
                "max_price": max(prices) if prices else None,
                "avg_price": round(sum(prices) / len(prices)) if prices else None,
            })

        except Exception as e:
            print(f"  [{camp_name}] {date_str} 에러: {e}")

        await asyncio.sleep(0.5)

    return results


async def main():
    camps = load_camfit_ids()
    if not camps:
        print("매칭된 캠핏 캠핑장이 없습니다. 02_camfit_match.py를 먼저 실행하세요.")
        return

    print(f"수집 대상: {len(camps)}개 캠핑장")
    timestamp = datetime.now().isoformat()

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

        for camp in camps:
            print(f"\n수집 중: {camp['name']} ({camp['camfit_id']})")
            avail = await fetch_availability(page, camp["camfit_id"], camp["name"])

            record = {
                "timestamp": timestamp,
                "kakao_id": camp["kakao_id"],
                "camfit_id": camp["camfit_id"],
                "name": camp["name"],
                "availability": avail,
            }

            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            print(f"  {len(avail)}일치 데이터 저장")
            await asyncio.sleep(2)

        await browser.close()

    print(f"\n완료! 결과: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
