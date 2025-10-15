import requests
import itertools
import pandas as pd
import time
import os

# --------------------------------------------------------------------------
# ✅ 설정 변수
# --------------------------------------------------------------------------
# 진단 테스트를 통과한 API 키를 사용합니다.
KAKAO_API_KEY = ""

# 1. 분석할 지역 목록: 데이터 기반 '관광 거점 유형' 프레임워크에 따라 선정.
TARGET_AREAS = ["서울 종로구", "부산 해운대구", "서울 중구"]

# 2. 각 지역별로 수집할 POI 키워드
POI_KEYWORDS = ["관광지", "맛집", "카페"]

# 3. 생성할 경로(Itinerary)의 POI 개수
ITINERARY_POI_COUNT = [3, 4]

# 4. POI 개수별, 지역별로 생성할 최대 경로 수
MAX_ITINERARIES_PER_COUNT = 100

# 5. 최종 결과물을 저장할 파일명
OUTPUT_CSV_FILE = "final_multi_region_itinerary_metrics.csv"


# --------------------------------------------------------------------------
# 함수 1: POI 데이터 수집 (수정된 부분)
# --------------------------------------------------------------------------
def get_pois_in_area(area_name, keywords):
    """
    주어진 지역명과 키워드로 카카오맵 API를 호출하여 고유한 POI 목록을 수집합니다.
    """
    print(f"🗺️  '{area_name}' 지역 POI 수집 시작 (키워드: {keywords})...")
    poi_list = []
    unique_ids = set()
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}

    for keyword in keywords:
        query = f"{area_name} {keyword}"
        print(f"   🔍 검색 중: '{query}'")
        
        for page in range(1, 4):
            # 간단한 파라미터 구성: query만 사용
            params = {
                "query": query,
                "page": page,
                "size": 15
            }
            
            try:
                response = requests.get(url, headers=headers, params=params, timeout=10)
                
                # 상세한 에러 정보 출력
                if response.status_code != 200:
                    print(f"   ⚠️  API 응답 코드: {response.status_code}")
                    print(f"   ⚠️  응답 내용: {response.text}")
                    if response.status_code == 400:
                        print(f"   💡 잘못된 요청입니다. API 키나 파라미터를 확인하세요.")
                    elif response.status_code == 401:
                        print(f"   💡 인증 실패. API 키를 확인하세요.")
                    elif response.status_code == 429:
                        print(f"   💡 API 호출 한도 초과. 잠시 후 다시 시도하세요.")
                        time.sleep(1)
                    continue
                
                data = response.json()
                
                # 메타 정보 출력
                if page == 1 and 'meta' in data:
                    print(f"   📍 검색 결과: 총 {data['meta'].get('total_count', 0)}건")
                
                if not data.get('documents'):
                    break

                for doc in data['documents']:
                    if doc['id'] not in unique_ids:
                        unique_ids.add(doc['id'])
                        poi_list.append({
                            "name": doc['place_name'], 
                            "id": doc['id'],
                            "lon": float(doc['x']), 
                            "lat": float(doc['y']),
                            "category": doc.get('category_name', 'N/A'),
                            "region": area_name
                        })
                
                time.sleep(0.2)  # API 호출 간격 증가
                
            except requests.exceptions.Timeout:
                print(f"   ⏱️  요청 시간 초과. 다음 페이지로 넘어갑니다.")
                continue
            except requests.exceptions.RequestException as e:
                print(f"   ❌ API 요청 오류: {e}")
                continue
            except Exception as e:
                print(f"   ❌ 예상치 못한 오류: {e}")
                continue

    print(f"✅ '{area_name}' 지역에서 총 {len(poi_list)}개의 고유 POI 수집 완료.")
    return poi_list

# --------------------------------------------------------------------------
# 함수 2: 가상 경로 생성 (변경 없음)
# --------------------------------------------------------------------------
def generate_itineraries(pois, poi_counts, max_per_count):
    """
    수집된 POI 목록으로 방문 순서를 고려한 경로(순열)를 생성합니다.
    """
    print(f"🚗 경로(Itinerary) 생성 시작 (POI 개수: {poi_counts})...")
    all_itineraries = []
    if not pois or len(pois) < min(poi_counts): return []

    for count in poi_counts:
        limited_pois = pois[:25] if len(pois) > 25 else pois
        if len(limited_pois) < count: continue

        permutations = list(itertools.permutations(limited_pois, count))
        sampled = permutations[:max_per_count] if len(permutations) > max_per_count else permutations
        all_itineraries.extend(sampled)
        print(f"   - POI {count}개 경로: {len(sampled)}개 생성")

    print(f"✅ 총 {len(all_itineraries)}개 경로 생성 완료.")
    return all_itineraries

# --------------------------------------------------------------------------
# 함수 3: 객관적 이동 지표 추출 (변경 없음)
# --------------------------------------------------------------------------
def get_route_metrics(start_poi, end_poi):
    """
    두 POI 간의 대중교통 경로 정보를 카카오내비 API로 조회하여 객관적 지표를 추출합니다.
    """
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {
        "origin": f"{start_poi['lon']},{start_poi['lat']}",
        "destination": f"{end_poi['lon']},{end_poi['lat']}",
        "priority": "RECOMMEND",
        "car_type": 1,
    }
    
    try:
        response = requests.get(url, headers=headers, params={**params, "waypoints": ""})
        response.raise_for_status()
        data = response.json()

        if not data.get('routes') or data['routes'][0].get('result_code') != 0:
            return {"error": "경로 없음"}

        summary = data['routes'][0]['summary']
        if 'fare' not in summary:
             return {"error": "대중교통 경로 없음"}

        transit_count = sum(1 for section in data['routes'][0]['sections'] for guide in section.get('guides', []) if guide.get('type') in [1, 2])
        transfer_count = max(0, transit_count - 1)
        
        return {
            "distance": summary.get('distance', 0),
            "duration": summary.get('duration', 0),
            "walk_distance": summary.get('walking_distance', 0),
            "transfer_count": transfer_count,
            "error": None
        }
    except Exception as e:
        return {"error": f"API 호출 또는 파싱 오류: {e}"}

# --------------------------------------------------------------------------
# 메인 실행 로직 (변경 없음)
# --------------------------------------------------------------------------
def main():
    """메인 실행 함수"""
    all_results = []
    for region in TARGET_AREAS:
        print(f"\n{'='*60}\n PROCESSING REGION: {region} \n{'='*60}")
        
        pois = get_pois_in_area(region, POI_KEYWORDS)
        if not pois: continue

        itineraries = generate_itineraries(pois, ITINERARY_POI_COUNT, MAX_ITINERARIES_PER_COUNT)
        if not itineraries: continue

        print(f"\n📊 총 {len(itineraries)}개 경로의 이동 지표 추출 시작...")
        for i, itinerary in enumerate(itineraries):
            total_metrics = {"distance": 0, "duration": 0, "walk_distance": 0, "transfers": 0}
            has_error = False
            for j in range(len(itinerary) - 1):
                metrics = get_route_metrics(itinerary[j], itinerary[j+1])
                time.sleep(0.05)
                if metrics.get("error"):
                    has_error = True; break
                
                total_metrics["distance"] += metrics['distance']
                total_metrics["duration"] += metrics['duration']
                total_metrics["walk_distance"] += metrics['walk_distance']
                total_metrics["transfers"] += metrics['transfer_count']
            
            if not has_error:
                all_results.append({
                    "region": region,
                    "itinerary_names": " -> ".join([p['name'] for p in itinerary]),
                    "num_activities": len(itinerary),
                    "total_distance_m": total_metrics["distance"],
                    "total_duration_sec": total_metrics["duration"],
                    "total_walk_distance_m": total_metrics["walk_distance"],
                    "total_transfers": total_metrics["transfers"]
                })
            
            if (i + 1) % 20 == 0: print(f"   ... {i + 1}/{len(itineraries)}개 처리 완료")

    if not all_results:
        print("\n🚨 처리된 유효 경로가 없습니다. 프로그램을 종료합니다.")
        return

    df = pd.DataFrame(all_results)
    df['walk_ratio'] = (df['total_walk_distance_m'] / df['total_distance_m']).fillna(0)
    df.insert(0, 'route_id', range(1, 1 + len(df)))

    df.to_csv(OUTPUT_CSV_FILE, index=False, encoding='utf-8-sig')
    print(f"\n🎉 모든 작업 완료! '{OUTPUT_CSV_FILE}' 파일에 {len(df)}개의 경로 데이터 저장 완료.")

if __name__ == "__main__":
    main()
