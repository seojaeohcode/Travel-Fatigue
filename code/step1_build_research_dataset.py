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

# ❗️❗️ 본인의 TMAP API 키를 입력하세요.
# TMAP API 키 발급: https://openapi.sk.com/ (회원가입 후 앱 등록)
TMAP_API_KEY = "rHUR1txUpc99XTr7lNrej3ahSlDcABiEavyP5xHL"  # 여기에 TMAP API 키를 입력하세요

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
    """두 지점 간 대중교통 기준 이동 지표를 TMAP API로 추출합니다."""
    url = "https://apis.openapi.sk.com/transit/routes"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "appKey": TMAP_API_KEY
    }
    
    # TMAP API는 POST 방식, JSON body 사용
    payload = {
        "startX": str(start_coords['lon']),
        "startY": str(start_coords['lat']),
        "endX": str(end_coords['lon']),
        "endY": str(end_coords['lat']),
        "lang": 0,  # 0: 한국어
        "format": "json",
        "count": 1  # 최적 경로 1개만
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        # TMAP 응답 구조 확인
        if 'metaData' not in data or 'data' not in data:
            return None
        
        meta = data['metaData']
        
        # 경로 정보가 없으면 None 반환
        if meta.get('plan', {}).get('itineraries') is None:
            return None
        
        itineraries = meta['plan']['itineraries']
        if len(itineraries) == 0:
            return None
        
        # 첫 번째 경로(최적 경로) 선택
        route = itineraries[0]
        
        # 지표 추출
        total_time = route.get('totalTime', 0)  # 총 소요 시간 (분)
        total_distance = route.get('totalDistance', 0)  # 총 이동 거리 (m)
        total_walk_time = route.get('totalWalkTime', 0)  # 도보 시간 (분)
        total_walk_distance = route.get('totalWalkDistance', 0)  # 도보 거리 (m)
        transfer_count = route.get('transferCount', 0)  # 환승 횟수
        fare = route.get('fare', {}).get('regular', {}).get('totalFare', 0)  # 일반 요금
        
        # legs에서 상세 정보 추출
        legs = route.get('legs', [])
        bus_count = 0
        subway_count = 0
        
        for leg in legs:
            mode = leg.get('mode', '')
            if mode == 'BUS':
                bus_count += 1
            elif mode == 'SUBWAY':
                subway_count += 1
        
        return {
            "distance": total_distance,  # 총 이동 거리 (m)
            "duration": total_time * 60,  # 총 소요 시간 (초로 변환)
            "walk_distance": total_walk_distance,  # 도보 거리 (m)
            "walk_time": total_walk_time * 60,  # 도보 시간 (초로 변환)
            "transfers": transfer_count,  # 환승 횟수
            "fare": fare,  # 대중교통 요금 (원)
            "bus_count": bus_count,  # 버스 이용 횟수
            "subway_count": subway_count  # 지하철 이용 횟수
        }
    except Exception as e:
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
    print("(대중교통 이동 기준으로 여행 경로 데이터를 수집합니다 - TMAP API 사용)\n")
    all_results = []

    for region in TARGET_AREAS:
        print(f"[{region}] 데이터 수집 중...")
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
        print(f"  - 총 {len(sampled_itineraries)}개 경로 조합 생성, 데이터 수집 시작...")
        
        collected_count = 0
        for idx, itinerary in enumerate(sampled_itineraries, 1):
            if idx % 30 == 0:
                print(f"    진행률: {idx}/{len(sampled_itineraries)} (수집 성공: {collected_count}개)")
            complete_loop = [start_point_coords] + list(itinerary) + [start_point_coords]
            total_metrics = {
                "distance": 0, 
                "duration": 0, 
                "walk_distance": 0, 
                "walk_time": 0,
                "transfers": 0, 
                "fare": 0,
                "bus_count": 0,
                "subway_count": 0
            }
            is_valid_route = True
            
            for i in range(len(complete_loop) - 1):
                metrics = get_public_transit_metrics(complete_loop[i], complete_loop[i+1])
                time.sleep(0.1)  # API 호출 제한 방지 (TMAP은 좀 더 여유있게)
                if metrics is None:
                    is_valid_route = False; break
                for key in total_metrics:
                    total_metrics[key] += metrics[key]
            
            if is_valid_route and total_metrics["distance"] > 0:
                total_metrics['region'] = region
                all_results.append(total_metrics)
                collected_count += 1
        
        print(f"  ✅ {region} 완료: {collected_count}개 경로 수집")

    if not all_results:
        print("\n🚨 유효한 경로 데이터를 생성하지 못했습니다. API 키나 네트워크 상태를 확인해주세요.")
        return

    df = pd.DataFrame(all_results)
    
    # 파생 지표 계산
    # 1. 도보 비율 (전체 거리 중 도보 거리 비율)
    df['walk_ratio'] = (df['walk_distance'] / df['distance']).fillna(0)
    
    # 2. 평균 이동 속도 (km/h)
    df['avg_speed'] = (df['distance'] / 1000) / (df['duration'] / 3600)
    df['avg_speed'] = df['avg_speed'].fillna(0)
    
    # 3. 환승 밀도 (거리 대비 환승 횟수)
    df['transfer_density'] = (df['transfers'] / (df['distance'] / 1000)).fillna(0)
    
    # 4. 대중교통 이용 비율
    df['transit_ratio'] = 1 - df['walk_ratio']
    
    df.to_csv(OUTPUT_RESEARCH_FILE, index=False, encoding='utf-8-sig')
    print(f"\n🎉 [1단계 완료] 사전 연구용 데이터셋 '{OUTPUT_RESEARCH_FILE}' 파일 저장 완료!")
    print(f"  - 총 {len(df)}개의 여행 경로 데이터 수집")
    print(f"  - 수집 지표: 거리, 소요시간, 도보거리, 환승횟수, 요금, 버스/지하철 이용")
    print(f"  - 파생 지표: 도보비율, 평균속도, 환승밀도, 대중교통비율")

if __name__ == "__main__":
    build_research_dataset()