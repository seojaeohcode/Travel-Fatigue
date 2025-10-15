import requests

# --------------------------------------------------------------------------
# ✅ 설정 변수
# --------------------------------------------------------------------------
# 사용자께서 제공해주신 API 키를 사용합니다.
KAKAO_API_KEY = ""
headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}


# --------------------------------------------------------------------------
# 테스트 1: '로컬 API' (키워드로 장소 검색)
# --------------------------------------------------------------------------
def test_local_api():
    """'로컬 API'가 정상적으로 작동하는지 테스트합니다."""
    print("="*50)
    print("[테스트 1] '로컬 API' (키워드로 장소 검색) 연동 확인")
    print("="*50)
    
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    params = {"query": "서울시청"}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            print("✅ [성공] 로컬 API 호출에 성공했습니다. (상태 코드: 200)")
            data = response.json()
            # 검색 결과가 있는지 확인 후 첫 번째 장소 이름 출력
            if data.get('documents'):
                place_name = data['documents'][0]['place_name']
                print(f"   - 확인된 장소: {place_name}")
            else:
                print("   - 호출은 성공했으나, 검색 결과가 없습니다.")
        else:
            # 실패 시 에러 메시지 출력
            print(f"❌ [실패] 로컬 API 호출에 실패했습니다. (상태 코드: {response.status_code})")
            print(f"   - 서버 응답: {response.text}")

    except Exception as e:
        print(f"❌ [에러] 테스트 중 예외가 발생했습니다: {e}")
    print("\n")


# --------------------------------------------------------------------------
# 테스트 2: '카카오내비 API' (길찾기)
# --------------------------------------------------------------------------
def test_navi_api():
    """'카카오내비 API'가 정상적으로 작동하는지 테스트합니다."""
    print("="*50)
    print("[테스트 2] '카카오내비 API' (길찾기) 연동 확인")
    print("="*50)
    
    url = "https://apis-navi.kakaomobility.com/v1/directions"
    # 출발지: 강남역, 도착지: 카카오 판교오피스
    params = {
        "origin": "127.0276,37.4979", 
        "destination": "127.1103,37.3942"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            print("✅ [성공] 카카오내비 API 호출에 성공했습니다. (상태 코드: 200)")
            data = response.json()
            # 경로 결과가 있는지 확인 후 예상 소요 시간 출력
            if data.get('routes'):
                duration_min = data['routes'][0]['summary']['duration'] // 60
                print(f"   - 확인된 경로: 강남역 -> 판교 (예상 소요시간: 약 {duration_min}분)")
            else:
                print("   - 호출은 성공했으나, 경로 정보를 찾을 수 없습니다.")
        else:
            # 실패 시 에러 메시지 출력
            print(f"❌ [실패] 카카오내비 API 호출에 실패했습니다. (상태 코드: {response.status_code})")
            print(f"   - 서버 응답: {response.text}")

    except Exception as e:
        print(f"❌ [에러] 테스트 중 예외가 발생했습니다: {e}")
    print("\n")

# --------------------------------------------------------------------------
# 진단 스크립트 실행
# --------------------------------------------------------------------------
if __name__ == "__main__":
    test_local_api()
    test_navi_api()
    print("진단이 완료되었습니다. 위의 성공/실패 메시지를 확인해주세요.")
