import pandas as pd
from sklearn.preprocessing import MinMaxScaler
import numpy as np
import os

# --------------------------------------------------------------------------
# ✅ 설정 변수
# --------------------------------------------------------------------------

# 스크립트의 실제 위치를 기준으로 상대 경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")

# 도보 버그를 수정한, 가장 최신 이동 경로 데이터 파일명
ITINERARY_DATA_FILE = os.path.join(DATASET_DIR, "corrected_itinerary_metrics.csv")

SPENDING_DATA_FILES = {
    "서울 종로구": os.path.join(DATASET_DIR, "spending_jongno.csv"),
    "부산 해운대구": os.path.join(DATASET_DIR, "spending_haeundae.csv"),
    "서울 중구": os.path.join(DATASET_DIR, "spending_junggu.csv")
}

# --------------------------------------------------------------------------
# 분석 함수
# --------------------------------------------------------------------------
def run_data_driven_tpfi_analysis():
    """
    이동 패턴과 소비 데이터의 상관관계를 분석하여
    데이터 기반의 TPFI 가중치를 도출하고, 최종 피로도 점수를 계산합니다.
    """
    print("[1단계] 이동 패턴 데이터 로드 및 요약...")
    try:
        df_itinerary = pd.read_csv(ITINERARY_DATA_FILE)
    except FileNotFoundError:
        print(f"❌ 에러: '{ITINERARY_DATA_FILE}' 파일을 찾을 수 없습니다.")
        print("   - 이전 단계의 'calculate_tpfi.py'를 먼저 실행하여 데이터 파일을 생성해주세요.")
        return

    # 지역별 4대 이동 지표 평균 계산
    travel_metrics = df_itinerary.groupby('region').agg(
        avg_distance_m=('total_distance_m', 'mean'),
        avg_duration_sec=('total_duration_sec', 'mean'),
        avg_transfers=('total_transfers', 'mean'),
        avg_walk_ratio=('walk_ratio', 'mean')
    ).reset_index()
    print("✅ 지역별 평균 이동 지표 계산 완료.")

    # --- 2단계: 소비 패턴 데이터 분석 및 '선택적 활력 소비' 지표 계산 ---
    print("\n[2단계] 소비 패턴 분석 및 '선택적 활력 소비' 지표 생성...")
    consumption_results = []
    for region, filename in SPENDING_DATA_FILES.items():
        try:
            df_spending = pd.read_csv(filename)
            # '쇼핑업'과 '여가서비스업'의 지출액 비율을 합산
            vitality_ratio = df_spending[df_spending['대분류'].isin(['쇼핑업', '여가서비스업'])]['대분류 지출액 비율'].unique().sum()
            consumption_results.append({'region': region, 'vitality_consumption_ratio': vitality_ratio})
        except FileNotFoundError:
            print(f"⚠️  경고: '{filename}' 파일을 찾을 수 없습니다.")
            continue
    
    df_consumption = pd.DataFrame(consumption_results)
    print("✅ 지역별 '선택적 활력 소비' 비율 계산 완료.")

    # --- 3단계: 데이터 병합 및 상관관계 분석 ---
    print("\n[3단계] 상관관계 분석을 통한 가중치 영향력 파악...")
    df_merged = pd.merge(travel_metrics, df_consumption, on='region')
    
    # 상관관계 행렬 계산
    correlation_matrix = df_merged.corr(numeric_only=True)
    # '선택적 활력 소비 비율'과의 상관관계만 추출
    correlations = correlation_matrix['vitality_consumption_ratio'].drop('vitality_consumption_ratio')
    print("✅ 이동 요인과 활력 소비 간의 상관관계 계산 완료:")
    print(correlations)

    # --- 4단계: 상관관계를 이용한 데이터 기반 TPFI 가중치 도출 ---
    print("\n[4단계] 데이터 기반 TPFI 가중치 도출...")
    # 음의 상관관계를 가진 요인만 필터링 (피로 요인이므로 음의 관계가 정상)
    fatigue_factors = correlations[correlations < 0]
    
    if fatigue_factors.empty:
        print("❌ 분석 중단: 피로 요인으로 추정되는 음의 상관관계를 가진 지표가 없습니다.")
        return
        
    # 절댓값의 합으로 정규화하여 가중치 계산
    weights_raw = abs(fatigue_factors)
    data_driven_weights = (weights_raw / weights_raw.sum()).to_dict()
    
    print("✅ 최종 TPFI 가중치 계산 완료:")
    for factor, weight in data_driven_weights.items():
        print(f"   - w_{factor.replace('avg_', '')}: {weight:.4f}")

    # --- 5단계: 최종 TPFI 점수 계산 및 결과 출력 ---
    print("\n[5단계] 최종 TPFI 점수 계산 및 지역별 피로도 분석...")
    features_for_tpfi = {
        'total_distance_m': data_driven_weights.get('avg_distance_m', 0),
        'total_duration_sec': data_driven_weights.get('avg_duration_sec', 0),
        'total_transfers': data_driven_weights.get('avg_transfers', 0),
        'walk_ratio': data_driven_weights.get('avg_walk_ratio', 0)
    }
    
    scaler = MinMaxScaler()
    df_itinerary_scaled = df_itinerary.copy()
    feature_keys = list(features_for_tpfi.keys())
    df_itinerary_scaled[feature_keys] = scaler.fit_transform(df_itinerary[feature_keys])

    df_itinerary['tpfi_score'] = sum(df_itinerary_scaled[key] * weight for key, weight in features_for_tpfi.items())

    print("\n" + "="*60)
    print("🎉 최종 분석 결과: 데이터 기반 TPFI 지역별 평균 점수 🎉")
    print("="*60)
    
    final_report = df_itinerary.groupby('region')['tpfi_score'].mean().sort_values(ascending=False).reset_index()
    final_report.columns = ['지역', '데이터 기반 평균 TPFI']
    print(final_report.to_markdown(index=False))

    print("\n[최종 결론]")
    print("상관관계 분석을 통해 '활력 소비'를 가장 많이 감소시키는 이동 요인을 찾아내고,")
    print("그 영향력을 바탕으로 객관적인 TPFI 가중치를 도출했습니다.")
    print("이 점수는 각 지역의 객관적인 '이동 부하'를 가장 논리적으로 나타내는 지표입니다.")

if __name__ == "__main__":
    run_data_driven_tpfi_analysis()
