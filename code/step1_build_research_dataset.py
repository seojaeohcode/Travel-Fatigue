import requests
import itertools
import pandas as pd
import time
import os

# --------------------------------------------------------------------------
# ✅ 설정 변수
# --------------------------------------------------------------------------
# 스크립트의 실제 위치를 기준으로 상대 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")

# ❗️❗️ 본인의 카카오 REST API 키를 입력하세요.
KAKAO_API_KEY = "6e5ff5f0fc34ba8dce84b422a33066bc"

# 1. 사전 연구를 위한 3가지 대표 지역 (논리적 대조군)
TARGET_AREAS = ["강릉시", "부산 해운대구", "서울 중구"]

# 2. 각 지역의 대표적인 시작점 (가상 숙소 역할을 할 교통/관광 거점)
#    - 모든 여행은 이 거점에서 시작하여 거점으로 돌아오는 '완결된 여정'으로 가정
AREA_START_POINTS = {
    "강릉시": "강릉역",
    "부산 해운대구": "해운대해수욕장",
    "서울 중구": "명동역"
}

# 3. 데이터 수집 설정
POI_KEYWORDS = ["관광지", "맛집"]
ITINERARY_POI_COUNT = [3] # 분석의 일관성을 위해 POI 개수는 3개로 고정
MAX_ITINERARIES_PER_COUNT = 150 # 지역별로 생성할 최대 경로 수

# 4. 최종 결과물 파일명 (dataset 폴더에 저장)
OUTPUT_RESEARCH_FILE = os.path.join(DATASET_DIR, "research_base_data.csv")

# --------------------------------------------------------------------------
# 헬퍼 함수
# --------------------------------------------------------------------------
def get_coords_for_location(address):
    """장소명을 위도, 경도 좌표로 변환합니다."""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {'query': address, 'size': 1}
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200 and response.json()['documents']:
            doc = response.json()['documents'][0]
            return {"name": doc['place_name'], "lon": float(doc['x']), "lat": float(doc['y'])}
    except Exception:
        return None
    return None

def get_public_transit_metrics(start_coords, end_coords):
    """두 지점 간 '대중교통' 기준 이동 지표를 상세히 추출합니다."""
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"origin": f"{start_coords['lon']},{start_coords['lat']}", "destination": f"{end_coords['lon']},{end_coords['lat']}"}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200: return None
        
        data = response.json()
        if not data.get('routes') or data['routes'][0].get('result_code') != 0:
            return None

        route = data['routes'][0]
        summary = route['summary']
        
        total_walk_distance = 0
        transit_count = 0
        for section in route['sections']:
            if section.get('guides'):
                for guide in section['guides']:
                    if guide.get('name') == '도보':
                        total_walk_distance += guide.get('distance', 0)
            transit_count += sum(1 for guide in section.get('guides', []) if guide.get('type') in [1, 2])
        
        return {
            "distance": summary.get('distance', 0),
            "duration": summary.get('duration', 0),
            "walk_distance": total_walk_distance,
            "transfers": max(0, transit_count - 1),
            "fare": summary.get('fare', {}).get('total', 0)
        }
    except Exception:
        return None

def get_pois_in_area(area_name, keywords):
    """지역 내 POI 목록을 수집합니다."""
    poi_list = []
    unique_ids = set()
    for keyword in keywords:
        # ... (이전과 동일한 POI 수집 로직)
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
        params = {'query': f"{area_name} {keyword}", 'size': 15, 'page': 1}
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200 and response.json()['documents']:
            for doc in response.json()['documents']:
                if doc['id'] not in unique_ids:
                    unique_ids.add(doc['id'])
                    poi_list.append({"name": doc['place_name'], "lon": float(doc['x']), "lat": float(doc['y'])})
    return poi_list

# --------------------------------------------------------------------------
# 메인 실행 로직
# --------------------------------------------------------------------------
def build_research_dataset():
    print("--- [1단계] 데이터 기반 가중치 도출을 위한 사전 연구 데이터셋 구축 시작 ---")
    all_results = []

    for region in TARGET_AREAS:
        print(f"\n[{region}] 데이터 수집 중...")
        start_point_name = AREA_START_POINTS[region]
        start_point_coords = get_coords_for_location(start_point_name)
        
        if not start_point_coords:
            print(f"  - ❌ 시작점 '{start_point_name}'의 좌표를 찾을 수 없어 건너<binary data, 2 bytes, 1 bytes>니다.")
            continue
            
        pois = get_pois_in_area(region, POI_KEYWORDS)
        if len(pois) < max(ITINERARY_POI_COUNT):
             print(f"  - ❌ POI가 충분하지 않아 건너<binary data, 2 bytes, 1 bytes>니다.")
             continue

        itineraries = list(itertools.permutations(pois, max(ITINERARY_POI_COUNT)))
        sampled_itineraries = itineraries[:MAX_ITINERARIES_PER_COUNT]

        for itinerary in sampled_itineraries:
            complete_loop = [start_point_coords] + list(itinerary) + [start_point_coords]
            total_metrics = {"distance": 0, "duration": 0, "walk_distance": 0, "transfers": 0, "fare": 0}
            is_valid_route = True
            
            for i in range(len(complete_loop) - 1):
                metrics = get_public_transit_metrics(complete_loop[i], complete_loop[i+1])
                time.sleep(0.05)
                if metrics is None:
                    is_valid_route = False; break
                for key in total_metrics:
                    total_metrics[key] += metrics[key]
            
            if is_valid_route and total_metrics["distance"] > 0:
                total_metrics['region'] = region
                all_results.append(total_metrics)

    if not all_results:
        print("\n🚨 유효한 경로 데이터를 생성하지 못했습니다. API 키나 네트워크 상태를 확인해주세요.")
        return

    df = pd.DataFrame(all_results)
    df['walk_ratio'] = (df['walk_distance'] / df['distance']).fillna(0)
    df.to_csv(OUTPUT_RESEARCH_FILE, index=False, encoding='utf-8-sig')
    print(f"\n🎉 [1단계 완료] 사전 연구용 데이터셋 '{OUTPUT_RESEARCH_FILE}' 파일 저장 완료!")

if __name__ == "__main__":
    build_research_dataset()