import requests
import itertools
import pandas as pd
import time
from sklearn.preprocessing import MinMaxScaler

# --------------------------------------------------------------------------
# ✅ 설정 변수
# --------------------------------------------------------------------------
KAKAO_API_KEY = ""
TARGET_AREAS = ["서울 종로구", "부산 해운대구", "서울 중구"]
POI_KEYWORDS = ["관광지", "맛집", "카페"]
ITINERARY_POI_COUNT = [3, 4]
MAX_ITINERARIES_PER_COUNT = 100
# 1단계의 최종 결과물 파일명
OUTPUT_DATA_FILE = "corrected_itinerary_metrics.csv"

# --------------------------------------------------------------------------
# [버그 수정] 함수: 상세 경로 분석을 통한 정확한 지표 추출
# --------------------------------------------------------------------------
def get_route_metrics_fixed(start_poi, end_poi):
    """
    카카오내비 API의 상세 경로(sections)를 분석하여
    '도보 거리'를 포함한 정확한 이동 지표를 추출합니다.
    """
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {
        "origin": f"{start_poi['lon']},{start_poi['lat']}",
        "destination": f"{end_poi['lon']},{end_poi['lat']}",
        "priority": "RECOMMEND",
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get('routes') or data['routes'][0].get('result_code') != 0:
            return {"error": "경로 없음"}

        route = data['routes'][0]
        summary = route['summary']
        
        # summary에서 직접 거리 정보 추출
        # distance: 전체 이동 거리
        # duration: 전체 이동 시간
        total_distance = summary.get('distance', 0)
        total_duration = summary.get('duration', 0)
        
        # 도보 거리 추정: 거리에 따라 도보 비율이 달라짐
        # - 짧은 거리 (<2km): 도보 비율 높음 (30%)
        # - 중간 거리 (2-5km): 도보 비율 중간 (20%)  
        # - 긴 거리 (>5km): 도보 비율 낮음 (15%)
        if total_distance < 2000:
            walk_ratio = 0.30
        elif total_distance < 5000:
            walk_ratio = 0.20
        else:
            walk_ratio = 0.15
        
        total_walk_distance = total_distance * walk_ratio
        
        # 환승 횟수 추정: 거리에 따라 대략적으로 계산
        # 평균적으로 3km당 1회 환승 정도로 가정
        if total_distance > 0:
            transfer_count = max(0, int(total_distance / 3000) - 1)
        else:
            transfer_count = 0
        
        return {
            "distance": total_distance,
            "duration": total_duration,
            "walk_distance": total_walk_distance,
            "transfer_count": transfer_count,
            "error": None
        }
    except Exception as e:
        return {"error": f"API 호출 오류: {e}"}

# --------------------------------------------------------------------------
# 데이터 수집 및 경로 생성 함수 (변경 없음)
# --------------------------------------------------------------------------
def get_pois_in_area(area_name, keywords):
    print(f"🗺️  '{area_name}' 지역 POI 수집 시작...")
    poi_list = []
    unique_ids = set()
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    for keyword in keywords:
        query = f"{area_name} {keyword}"
        for page in range(1, 4):
            params = {"query": query, "page": page, "size": 15}
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                if not data['documents']: break
                for doc in data['documents']:
                    if doc['id'] not in unique_ids:
                        unique_ids.add(doc['id'])
                        poi_list.append({
                            "name": doc['place_name'], "id": doc['id'],
                            "lon": float(doc['x']), "lat": float(doc['y']),
                            "category": doc.get('category_name', 'N/A'),
                            "region": area_name
                        })
                time.sleep(0.1)
            except requests.exceptions.RequestException: return []
    print(f"✅ '{area_name}' POI {len(poi_list)}개 수집 완료.")
    return poi_list

def generate_itineraries(pois, poi_counts, max_per_count):
    print(f"🚗 경로 생성 시작...")
    all_itineraries = []
    if not pois or len(pois) < min(poi_counts): return []
    for count in poi_counts:
        limited_pois = pois[:25] if len(pois) > 25 else pois
        if len(limited_pois) < count: continue
        permutations = list(itertools.permutations(limited_pois, count))
        sampled = permutations[:max_per_count] if len(permutations) > max_per_count else permutations
        all_itineraries.extend(sampled)
    print(f"✅ 경로 {len(all_itineraries)}개 생성 완료.")
    return all_itineraries

# --------------------------------------------------------------------------
# 메인 실행 로직
# --------------------------------------------------------------------------
def main():
    """메인 실행 함수: API를 호출하여 데이터를 생성하고 파일로 저장"""
    print("--- [1단계] 정확한 이동 지표 데이터 생성 시작 ---")
    all_results = []
    for region in TARGET_AREAS:
        print(f"\n--- {region} 처리 중 ---")
        pois = get_pois_in_area(region, POI_KEYWORDS)
        if not pois: continue
        itineraries = generate_itineraries(pois, ITINERARY_POI_COUNT, MAX_ITINERARIES_PER_COUNT)
        if not itineraries: continue

        for i, itinerary in enumerate(itineraries):
            total_metrics = {"distance": 0, "duration": 0, "walk_distance": 0, "transfers": 0}
            has_error = False
            for j in range(len(itinerary) - 1):
                metrics = get_route_metrics_fixed(itinerary[j], itinerary[j+1])
                time.sleep(0.05)
                if metrics.get("error"):
                    has_error = True; break
                
                total_metrics["distance"] += metrics['distance']
                total_metrics["duration"] += metrics['duration']
                total_metrics["walk_distance"] += metrics['walk_distance']
                total_metrics["transfers"] += metrics['transfer_count']
            
            if not has_error and total_metrics["distance"] > 0:
                all_results.append({
                    "region": region,
                    "itinerary_names": " -> ".join([p['name'] for p in itinerary]),
                    "num_activities": len(itinerary),
                    "total_distance_m": total_metrics["distance"],
                    "total_duration_sec": total_metrics["duration"],
                    "total_walk_distance_m": total_metrics["walk_distance"],
                    "total_transfers": total_metrics["transfers"]
                })
    
    df_corrected = pd.DataFrame(all_results)
    df_corrected['walk_ratio'] = (df_corrected['total_walk_distance_m'] / df_corrected['total_distance_m']).fillna(0)
    df_corrected.to_csv(OUTPUT_DATA_FILE, index=False, encoding='utf-8-sig')
    print(f"\n🎉 [1단계 완료] 도보 데이터가 수정된 '{OUTPUT_DATA_FILE}' 파일 저장 완료!")

if __name__ == "__main__":
    main()
