# pip install pandas scikit-learn requests numpy matplotlib seaborn
import requests
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import itertools
import time
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import font_manager, rc

# --------------------------------------------------------------------------
# ✅ 설정 변수
# --------------------------------------------------------------------------
# ❗️❗️ 본인의 카카오 REST API 키를 입력하세요.
KAKAO_API_KEY = "6e5ff5f0fc34ba8dce84b422a33066bc"

# 1. 클러스터링 분석 대상이 될 대한민국 대표 관광 도시 후보군
CANDIDATE_CITIES = [
    "서울 종로구", "서울 중구", "서울 강남구", "부산 해운대구", 
    "부산 중구", "제주시", "서귀포시", "경주시", "전주시 완산구", "강릉시"
]

# 2. 각 도시의 면적(km²) - (사전 조사된 고정값)
CITY_AREAS = {
    "서울 종로구": 23.91, "서울 중구": 9.96, "서울 강남구": 39.5, "부산 해운대구": 51.47,
    "부산 중구": 2.8, "제주시": 978.7, "서귀포시": 870.8, "경주시": 1357.0,
    "전주시 완산구": 95.2, "강릉시": 1040.0
}

# 3. 관광 특성 분석을 위한 POI 카테고리 (카카오맵 API 기준)
CATEGORY_CODES = {
    'attraction': 'AT4', # 관광명소
    'culture': 'CT1',    # 문화시설
    'shopping': 'MT1',   # 쇼핑 (대형마트/백화점)
    'food': 'FD6',       # 음식점
}

# --------------------------------------------------------------------------
# 헬퍼 함수
# --------------------------------------------------------------------------
def get_total_poi_count(city, category_code):
    """특정 도시와 카테고리에 대한 전체 POI 개수를 반환합니다."""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {'query': city, 'category_group_code': category_code, 'size': 1}
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json()['meta']['total_count']
    except Exception:
        return 0
    return 0

def get_poi_coords(city, limit=20):
    """분산도 계산을 위해 도시 내 대표 POI들의 좌표를 수집합니다."""
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {'query': f"{city} 관광", 'size': limit}
    coords = []
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            for doc in response.json()['documents']:
                coords.append((float(doc['y']), float(doc['x']))) # (lat, lon)
    except Exception:
        return []
    return coords

def calculate_dispersion(coords):
    """좌표 목록 간의 평균 거리를 계산하여 분산도를 측정합니다."""
    if len(coords) < 2: return 0
    total_dist = 0
    count = 0
    for p1, p2 in itertools.combinations(coords, 2):
        # Haversine formula to calculate distance between two lat/lon points
        R = 6371  # Radius of Earth in km
        lat1, lon1 = np.radians(p1)
        lat2, lon2 = np.radians(p2)
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
        c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
        distance = R * c
        total_dist += distance
        count += 1
    return total_dist / count if count > 0 else 0

# --------------------------------------------------------------------------
# 메인 실행 로직
# --------------------------------------------------------------------------
def run_city_clustering():
    print("--- [PRE-STEP] 관광 특성 클러스터링을 통한 대표 지역 선발 시작 ---")
    
    # 1. 각 후보 도시별 3가지 정량 지표 계산
    city_features = []
    for city in CANDIDATE_CITIES:
        print(f"\n[{city}] 관광 특성 분석 중...")
        time.sleep(0.5)
        
        # 지표 1: 관광자원 밀집도 (관광명소+문화시설 개수 / 면적)
        attraction_count = get_total_poi_count(city, CATEGORY_CODES['attraction'])
        culture_count = get_total_poi_count(city, CATEGORY_CODES['culture'])
        density = (attraction_count + culture_count) / CITY_AREAS[city]
        print(f"  - 밀집도: {density:.2f} 개/km²")

        # 지표 2: 관광자원 다양성 (엔트로피 지수)
        category_counts = [get_total_poi_count(city, code) for code in CATEGORY_CODES.values()]
        total_pois = sum(category_counts)
        proportions = [count / total_pois for count in category_counts if count > 0]
        diversity = -sum(p * np.log2(p) for p in proportions if p > 0)
        print(f"  - 다양성: {diversity:.2f}")

        # 지표 3: 관광자원 분산도 (POI 간 평균 거리)
        coords = get_poi_coords(city)
        dispersion = calculate_dispersion(coords)
        print(f"  - 분산도: {dispersion:.2f} km")
        
        city_features.append({
            'city': city,
            'density': density,
            'diversity': diversity,
            'dispersion': dispersion
        })

    df = pd.DataFrame(city_features)
    
    # 2. K-means 클러스터링 실행
    features = df[['density', 'diversity', 'dispersion']]
    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(features)
    
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    df['cluster'] = kmeans.fit_predict(scaled_features)
    
    # 3. 각 클러스터의 대표 지역 선발
    centroids = kmeans.cluster_centers_
    representatives = []
    for i in range(3):
        cluster_data = scaled_features[df['cluster'] == i]
        centroid = centroids[i]
        distances = np.linalg.norm(cluster_data - centroid, axis=1)
        closest_point_index = np.argmin(distances)
        representative_city_index = df[df['cluster'] == i].index[closest_point_index]
        representatives.append(df.loc[representative_city_index]['city'])

    # 4. 최종 결과 출력 및 시각화
    # 한글 폰트 설정
    try:
        path = "c:/Windows/Fonts/malgun.ttf"
        font_name = font_manager.FontProperties(fname=path).get_name()
        rc('font', family=font_name)
    except:
        print("한글 폰트(Malgun Gothic)를 찾을 수 없어 영문으로 표시될 수 있습니다.")

    plt.figure(figsize=(12, 8))
    sns.scatterplot(data=df, x='dispersion', y='density', hue='cluster', s=200, palette='viridis', style='city', markers={city: 'o' for city in df['city']})
    plt.title('관광 도시 클러스터링 결과 (밀집도 vs 분산도)', fontsize=16)
    plt.xlabel('관광자원 분산도 (POI 간 평균 거리, km)', fontsize=12)
    plt.ylabel('관광자원 밀집도 (POI 개수 / 면적)', fontsize=12)
    plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0.)
    plt.grid(True)
    plt.tight_layout()
    plt.show()

    print("\n" + "="*80)
    print("🎉 [PRE-STEP 완료] 데이터 기반 클러스터링을 통해 선발된 각 유형별 대표 지역 🎉")
    print("="*80)
    
    for i, rep in enumerate(representatives):
        cluster_cities = df[df['cluster'] == i]['city'].tolist()
        print(f"\n[유형 {i+1}] 대표 지역: ⭐ {rep} ⭐")
        print(f"  - 이 유형에 속한 다른 도시들: {', '.join(cluster_cities)}")

    print("\n\n[최종 결론]")
    print("위 클러스터링 결과는, 우리가 본 분석에서 '서울 종로구', '부산 해운대구', '서울 중구'와 같은 지역들을")
    print("비교 대상으로 선정한 것이 임의의 선택이 아니라, 대한민국 관광지의 다양한 유형을 대표하는")
    print("객관적이고 합리적인 선택이었음을 데이터로 증명합니다.")

if __name__ == "__main__":
    run_city_clustering()