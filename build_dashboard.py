import json
import math

with open('merged_camps.json') as f:
    camps = json.load(f)
with open('kakao_reviews.json') as f:
    reviews = json.load(f)
with open('naver_reviews.json') as f:
    naver = json.load(f)
with open('all_reviews.json') as f:
    all_reviews = json.load(f)
with open('camfit_reviews.json') as f:
    camfit_reviews = json.load(f)
with open('booking_channels.json') as f:
    booking_channels = json.load(f)

# 네이버 데이터를 camps에 머지
naver_map = {n['kakao_id']: n for n in naver}
review_map = {r['kakao_id']: r for r in all_reviews}

for camp in camps:
    nv = naver_map.get(camp['kakao_id'], {})
    camp['naver_rating'] = nv.get('naver_rating')
    camp['naver_visitor_review'] = nv.get('naver_visitor_review', 0)
    camp['naver_blog_review'] = nv.get('naver_blog_review', 0)

    rv = review_map.get(camp['kakao_id'], {})
    camp['crawled_reviews'] = rv.get('review_summary', {}).get('total', 0)
    camp['review_texts'] = rv.get('reviews', [])

    # 캠핏 리뷰 머지
    cf = camfit_reviews.get(camp['kakao_id'], {})
    camp['camfit_review_count'] = cf.get('camfit_review_count', 0)
    camp['camfit_reviews'] = cf.get('reviews', [])

    # 예약 채널 머지
    bc = booking_channels.get(camp['kakao_id'], {})
    camp['has_own_website'] = bc.get('has_own_website', False)
    camp['own_website_url'] = bc.get('own_website_url')
    camp['booking_platforms'] = bc.get('platforms', [])

# 종합순위 점수 계산 (0~100)
# 7개 항목: 카카오평점(20) + 카카오리뷰수(15) + 네이버방문자(20) + 네이버블로그(15) + 네이버평점(10) + 캠핏리뷰(15) + 예약채널(5)
for camp in camps:
    r = camp.get('rating') or 0
    rc = camp.get('review_count') or 0
    nv = camp.get('naver_visitor_review') or 0
    nb = camp.get('naver_blog_review') or 0
    nr = camp.get('naver_rating') or 0
    cf = camp.get('camfit_review_count') or 0

    s_kakao_rating = r / 5.0 * 20
    s_kakao_review = min(math.log1p(rc) / math.log1p(200) * 15, 15)
    s_naver_visitor = min(math.log1p(nv) / math.log1p(1000) * 20, 20)
    s_naver_blog = min(math.log1p(nb) / math.log1p(500) * 15, 15)
    s_naver_rating = (nr / 5.0 * 10) if nr else 0
    s_camfit_review = min(math.log1p(cf) / math.log1p(100) * 15, 15)
    s_channel = 5 if camp.get('has_own_website') or len(camp.get('booking_platforms', [])) > 0 else 0

    camp['popularity_score'] = round(s_kakao_rating + s_kakao_review + s_naver_visitor + s_naver_blog + s_naver_rating + s_camfit_review + s_channel, 1)
    camp['score_detail'] = {
        'kakao_rating': round(s_kakao_rating, 1),
        'kakao_review': round(s_kakao_review, 1),
        'naver_visitor': round(s_naver_visitor, 1),
        'naver_blog': round(s_naver_blog, 1),
        'naver_rating': round(s_naver_rating, 1),
        'camfit_review': round(s_camfit_review, 1),
        'channel': round(s_channel, 1),
    }

# 종합순위 부여
ranked = sorted(camps, key=lambda c: c['popularity_score'], reverse=True)
for i, c in enumerate(ranked):
    c['comp_rank'] = i + 1

# 리뷰 텍스트는 대시보드에 너무 크니까 요약만
for camp in camps:
    texts = camp.pop('review_texts', [])
    cf_texts = camp.pop('camfit_reviews', [])
    # 캠핏 리뷰 우선 + 기존 리뷰
    all_texts = cf_texts[:10] + texts[:5]
    camp['review_previews'] = [{'s': r.get('source','camfit'), 't': r.get('text','')[:120], 'r': r.get('rating'), 'z': r.get('zone','')} for r in all_texts[:12]]

with open('dashboard.html') as f:
    html = f.read()

html = html.replace('CAMPS_PLACEHOLDER', json.dumps(camps, ensure_ascii=False))
html = html.replace('REVIEWS_PLACEHOLDER', json.dumps(reviews, ensure_ascii=False))

with open('dashboard_live.html', 'w') as f:
    f.write(html)

has_naver = sum(1 for c in camps if c.get('naver_visitor_review', 0) > 0 or c.get('naver_blog_review', 0) > 0)
print(f"dashboard_live.html 생성 완료 (캠핑장 {len(camps)}개, 리뷰 {len(reviews)}개, 네이버 {has_naver}개)")
