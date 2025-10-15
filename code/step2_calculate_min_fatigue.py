import pandas as pd
import requests
import itertools
from sklearn.preprocessing import MinMaxScaler
import numpy as np
import os

# --------------------------------------------------------------------------
# 스크립트의 실제 위치를 기준으로 상대 경로 설정
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")

# --------------------------------------------------------------------------
# ✅ 1. 사용자 입력 (이 부분만 수정하여 사용)
# --------------------------------------------------------------------------
USER_START_LOCATION = "홍대입구역"
USER_DESIRED_POIS = ["국립중앙박물관", "N서울타워", "더현대 서울"]

# ❗️❗️ 본인의 카카오 REST API 키를 입력하세요.
KAKAO_API_KEY = "6e5ff5f0fc34ba8dce84b422a33066bc"

# --------------------------------------------------------------------------
# ✅ 2. 사전 연구 및 데이터 파일 설정 (dataset 폴더 사용)
# --------------------------------------------------------------------------
RESEARCH_DATA_FILE = os.path.join(DATASET_DIR, "research_base_data.csv")
SPENDING_DATA_FILES = {
    "서울 종로구": os.path.join(DATASET_DIR, "spending_jongno.csv"),
    "부산 해운대구": os.path.join(DATASET_DIR, "spending_haeundae.csv"),
    "서울 중구": os.path.join(DATASET_DIR, "spending_junggu.csv")
}

# --------------------------------------------------------------------------
# 헬퍼 함수 (1단계 코드와 동일)
# --------------------------------------------------------------------------
def get_coords_for_location(address):
    # ... (1단계와 동일한 좌표 변환 함수)
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
    # ... (1단계와 동일한 대중교통 지표 추출 함수)
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"origin": f"{start_coords['lon']},{start_coords['lat']}", "destination": f"{end_coords['lon']},{end_coords['lat']}"}
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200: return None
        data = response.json()
        if not data.get('routes') or data['routes'][0].get('result_code') != 0: return None
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
        return {"distance": summary.get('distance', 0), "duration": summary.get('duration', 0), "walk_distance": total_walk_distance, "transfers": max(0, transit_count - 1), "fare": summary.get('fare', {}).get('total', 0)}
    except Exception:
        return None

# --------------------------------------------------------------------------
# [핵심] 데이터 기반 가중치 도출 함수
# --------------------------------------------------------------------------
def get_data_driven_weights():
    """사전 연구 데이터와 소비 데이터를 분석하여 TPFI 가중치를 도출합니다."""
    print("--- [사전 분석] 데이터 기반 TPFI 가중치 도출 시작 ---")
    try:
        df_research = pd.read_csv(RESEARCH_DATA_FILE)
    except FileNotFoundError:
        print(f"❌ 에러: 사전 연구 데이터('{RESEARCH_DATA_FILE}')가 필요합니다.")
        return None

    # 1. 지역별 평균 이동 지표 계산
    travel_metrics = df_research.groupby('region').agg(
        avg_distance_m=('distance', 'mean'),
        avg_transfers=('transfers', 'mean'),
        avg_walk_ratio=('walk_ratio', 'mean')
    ).reset_index()

    # 2. '선택적 활력 소비' 지표 계산
    consumption_results = []
    for region, filename in SPENDING_DATA_FILES.items():
        try:
            df_spending = pd.read_csv(filename)
            vitality_ratio = df_spending[df_spending['대분류'].isin(['쇼핑업', '여가서비스업'])]['대분류 지출액 비율'].unique().sum()
            consumption_results.append({'region': region, 'vitality_consumption_ratio': vitality_ratio})
        except FileNotFoundError: return None
    df_consumption = pd.DataFrame(consumption_results)

    # 3. 데이터 병합 및 상관관계 분석
    df_merged = pd.merge(travel_metrics, df_consumption, on='region')
    correlations = df_merged.corr(numeric_only=True)['vitality_consumption_ratio']
    fatigue_factors = correlations[correlations < 0].drop('vitality_consumption_ratio', errors='ignore')

    if fatigue_factors.empty: return None

    # 4. 상관계수를 가중치로 변환
    weights_raw = abs(fatigue_factors)
    data_driven_weights = (weights_raw / weights_raw.sum()).to_dict()
    
    print("✅ 데이터 기반 가중치 도출 완료.")
    return {
        'distance': data_driven_weights.get('avg_distance_m', 0),
        'transfers': data_driven_weights.get('avg_transfers', 0),
        'walk_ratio': data_driven_weights.get('avg_walk_ratio', 0)
    }

# --------------------------------------------------------------------------
# 메인 솔루션 실행 로직
# --------------------------------------------------------------------------
def calculate_user_trip_fatigue(tpfi_weights):
    """사용자 입력을 받아 모든 경로 후보의 피로도를 계산하고 비교 제시합니다."""
    print("\n--- [솔루션 실행] 사용자 지정 경로 최소 피로도 산출 시작 ---")
    
    # 1. 사용자 입력 좌표 변환
    start_coords = get_coords_for_location(USER_START_LOCATION)
    poi_coords = [get_coords_for_location(poi) for poi in USER_DESIRED_POIS]
    if not start_coords or None in poi_coords:
        print("❌ 입력한 장소의 좌표를 찾을 수 없습니다. 장소명을 확인해주세요.")
        return

    # 2. 경로 후보 생성 및 이동 지표 계산
    all_routes = []
    for permutation in itertools.permutations(poi_coords):
        complete_loop = [start_coords] + list(permutation) + [start_coords]
        total_metrics = {"distance": 0, "duration": 0, "walk_distance": 0, "transfers": 0}
        is_valid = True
        for i in range(len(complete_loop) - 1):
            metrics = get_public_transit_metrics(complete_loop[i], complete_loop[i+1])
            if metrics is None: is_valid = False; break
            for key in total_metrics: total_metrics[key] += metrics[key]
        
        if is_valid:
            total_metrics['name'] = " -> ".join([p['name'] for p in complete_loop])
            all_routes.append(total_metrics)
    
    if not all_routes:
        print("❌ 유효한 대중교통 경로를 찾을 수 없습니다.")
        return

    # 3. TPFI 점수 계산
    df = pd.DataFrame(all_routes)
    df['walk_ratio'] = (df['walk_distance'] / df['distance']).fillna(0)
    
    scaler = MinMaxScaler()
    features = ['distance', 'transfers', 'walk_ratio']
    df_scaled = df.copy()
    df_scaled[features] = scaler.fit_transform(df[features])

    df['tpfi_score'] = (df_scaled['distance'] * tpfi_weights['distance'] +
                        df_scaled['transfers'] * tpfi_weights['transfers'] +
                        df_scaled['walk_ratio'] * tpfi_weights['walk_ratio']) * 100
    
    # 4. 최종 결과 출력
    final_report = df[['name', 'tpfi_score', 'duration', 'walk_distance']].sort_values('tpfi_score')
    
    print("\n" + "="*70)
    print(f"🗺️  '{USER_START_LOCATION}'에서 출발하는 당신의 여행 계획 피로도 분석 결과")
    print("="*70)
    
    for i, row in final_report.iterrows():
        print(f"📍 경로 순서: {row['name']}")
        print(f"   - 🔥 최소 피로도(TPFI) 점수: {row['tpfi_score']:.1f} 점 (낮을수록 덜 피곤)")
        print(f"   - 🕒 예상 총 이동시간: 약 {row['duration']/3600:.1f} 시간")
        print(f"   - 🚶 예상 총 도보거리: 약 {row['walk_distance']/1000:.1f} km\n")

if __name__ == "__main__":
    # 1. 먼저 데이터 기반 가중치를 얻고,
    weights = get_data_driven_weights()
    
    # 2. 그 가중치를 이용해 사용자 경로의 피로도를 계산합니다.
    if weights:
        calculate_user_trip_fatigue(weights)
    else:
        print("\n🚨 데이터 기반 가중치를 도출할 수 없어 피로도 계산을 진행할 수 없습니다.")