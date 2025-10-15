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
    coords = []
    
    # 여러 카테고리의 POI를 수집하여 분산도를 계산
    categories = [CATEGORY_CODES['attraction'], CATEGORY_CODES['culture']]
    
    for category in categories:
        params = {
            'query': city, 
            'category_group_code': category, 
            'size': min(15, limit)  # 각 카테고리당 최대 15개
        }
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                documents = response.json().get('documents', [])
                for doc in documents:
                    coords.append((float(doc['y']), float(doc['x']))) # (lat, lon)
        except Exception:
            continue
        
        time.sleep(0.1)  # API 호출 제한 방지
    
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
    print("\n" + "="*80)
    print("📍 클러스터별 대표 도시 선정 과정")
    print("="*80)
    
    centroids = kmeans.cluster_centers_
    representatives = []
    representative_info = []  # 대표 도시 정보를 저장
    
    for i in range(3):
        cluster_cities_df = df[df['cluster'] == i]
        cluster_data = scaled_features[df['cluster'] == i]
        centroid = centroids[i]
        
        # 클러스터 특성 계산
        avg_density = cluster_cities_df['density'].mean()
        avg_diversity = cluster_cities_df['diversity'].mean()
        avg_dispersion = cluster_cities_df['dispersion'].mean()
        
        print(f"\n[클러스터 {i+1}] 속한 도시: {', '.join(cluster_cities_df['city'].tolist())}")
        print(f"  평균 특성 - 밀집도: {avg_density:.2f}, 다양성: {avg_diversity:.2f}, 분산도: {avg_dispersion:.2f}km")
        
        # 클러스터 중심에서 각 도시까지의 거리 계산
        distances = np.linalg.norm(cluster_data - centroid, axis=1)
        
        # 가장 가까운 도시 찾기
        closest_point_index = np.argmin(distances)
        representative_city_index = df[df['cluster'] == i].index[closest_point_index]
        rep_city = df.loc[representative_city_index]['city']
        
        representatives.append(rep_city)
        representative_info.append({
            'cluster': i,
            'city': rep_city,
            'distance': distances[closest_point_index],
            'avg_density': avg_density,
            'avg_dispersion': avg_dispersion
        })
        
        print(f"  ✅ 대표 도시: {rep_city} (중심점과의 거리: {distances[closest_point_index]:.4f})")

    # 4. 최종 결과 출력 및 시각화
    # 한글 폰트 설정
    try:
        # Windows 기준 '맑은 고딕'
        path = "c:/Windows/Fonts/malgun.ttf"
        font_name = font_manager.FontProperties(fname=path).get_name()
        rc('font', family=font_name)
    except:
        # Mac OS 기준 'AppleGothic'
        try:
            rc('font', family='AppleGothic')
        except:
            print("한글 폰트를 찾을 수 없어 일부 글자가 깨질 수 있습니다.")

    plt.figure(figsize=(14, 9))
    
    # 대표 도시와 일반 도시 분리
    df['is_representative'] = df['city'].isin(representatives)
    
    # 일반 도시 먼저 그리기
    non_rep = df[~df['is_representative']]
    scatter_plot = sns.scatterplot(
        data=non_rep, x='dispersion', y='density', hue='cluster', s=200, 
        palette='viridis', alpha=0.5, legend=False
    )
    
    # 대표 도시는 크고 진하게
    rep_cities = df[df['is_representative']]
    sns.scatterplot(
        data=rep_cities, x='dispersion', y='density', hue='cluster', s=500, 
        palette='viridis', alpha=1.0, edgecolor='red', linewidth=3, legend='full'
    )
    
    plt.title('대한민국 주요 관광 도시 클러스터링 결과 (빨간 테두리 = 대표 도시)', fontsize=18, pad=20)
    plt.xlabel('관광자원 분산도 (POI 간 평균 거리, km)  →  (넓게 퍼져있음)', fontsize=13)
    plt.ylabel('관광자원 밀집도 (POI 개수 / 면적)  →  (빽빽하게 모여있음)', fontsize=13)
    
    # 각 점 옆에 도시 이름 표시 (대표 도시는 굵게)
    for i, point in df.iterrows():
        if point['is_representative']:
            plt.text(point['dispersion'] + 0.5, point['density'], str(point['city']), 
                    fontsize=12, fontweight='bold', color='red')
        else:
            plt.text(point['dispersion'] + 0.5, point['density'], str(point['city']), 
                    fontsize=10, alpha=0.7)
        
    plt.legend(title='클러스터 유형', bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout(rect=[0, 0, 0.85, 1]) # 범례 공간 확보
    
    # 이미지 파일로 저장
    plt.savefig("city_clustering_result.png", dpi=300)
    print("\n\n✅ 클러스터링 결과가 'city_clustering_result.png' 이미지 파일로 저장되었습니다.")
    plt.show()

    print("\n\n" + "="*80)
    print("🎉 [최종 선정] 대한민국 관광지 다양성을 대표하는 3개 지역 🎉")
    print("="*80)
    
    # 클러스터 특성 설명
    cluster_types = {
        'high_density': None,    # 높은 밀집도
        'medium': None,          # 중간 특성
        'low_density_high_dispersion': None  # 낮은 밀집도, 높은 분산도
    }
    
    for info in representative_info:
        if info['avg_density'] > 20:
            cluster_types['high_density'] = info
        elif info['avg_dispersion'] > 10:
            cluster_types['low_density_high_dispersion'] = info
        else:
            cluster_types['medium'] = info
    
    rank = 1
    for type_name, info in cluster_types.items():
        if info is None:
            continue
        city_data = df[df['city'] == info['city']].iloc[0]
        cluster_cities = df[df['cluster'] == info['cluster']]['city'].tolist()
        
        # 유형 설명
        if type_name == 'high_density':
            type_desc = "도심 밀집형 (관광자원이 좁은 지역에 집중)"
        elif type_name == 'low_density_high_dispersion':
            type_desc = "광역 분산형 (관광자원이 넓은 지역에 분포)"
        else:
            type_desc = "중간 균형형 (밀집도와 분산도가 균형)"
        
        print(f"\n[{rank}] ⭐ {info['city']} ⭐")
        print(f"  유형: {type_desc}")
        print(f"  클러스터: {info['cluster']+1}번 (같은 유형: {', '.join(cluster_cities)})")
        print(f"  관광 특성:")
        print(f"    - 밀집도: {city_data['density']:.2f} 개/km²")
        print(f"    - 다양성: {city_data['diversity']:.2f}")
        print(f"    - 분산도: {city_data['dispersion']:.2f} km")
        rank += 1

    print("\n" + "="*80)
    print("📌 최종 선정된 3개 대표 지역: " + " / ".join([f"⭐{city}⭐" for city in representatives]))
    print("="*80)
    
    print("\n[결론]")
    print("위 3개 지역은 K-means 클러스터링을 통해 도출된 서로 다른 관광 특성을 가진")
    print("유형별 대표 도시로, 대한민국 관광지의 다양성을 객관적으로 대표합니다.")
    print("본 분석의 비교 대상 선정이 임의적이지 않음을 데이터로 증명합니다.")

if __name__ == "__main__":
    run_city_clustering()
