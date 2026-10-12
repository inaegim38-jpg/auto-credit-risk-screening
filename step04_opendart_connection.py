"""
STEP 4: OpenDART API 연결 테스트
- .env 환경변수 로드 및 API Key 유효성 검증
- OpenDART API 엔드포인트 실제 통신 검증
  1) corpCode.xml (기업 고유번호 다운로드 엔드포인트)
  2) fnlttSinglAcntAll.json (단일회사 전체 재무제표 조회 엔드포인트)
- HTTP Status, API 응답 코드(status), 메시지(message) 검증

실행: python step04_opendart_connection.py
"""

import os
import requests
from dotenv import load_dotenv

# ── 1. 환경변수 확인 ────────────────────────────────────────────────────────────
load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")

if not DART_API_KEY:
    raise EnvironmentError("[FAIL] DART_API_KEY 환경변수가 존재하지 않습니다. .env 파일을 확인하세요.")

masked_key = f"{DART_API_KEY[:4]}****{DART_API_KEY[-4:]}" if len(DART_API_KEY) > 8 else "****"
print(f"[1] DART_API_KEY 로드 성공: {masked_key} (길이: {len(DART_API_KEY)})")

BASE_URL = "https://opendart.fss.or.kr/api"

# ── 2. corpCode.xml 연결 테스트 ───────────────────────────────────────────────
print("\n[2] OpenDART corpCode.xml 엔드포인트 연결 테스트...")
url_corp = f"{BASE_URL}/corpCode.xml"
params_corp = {"crtfc_key": DART_API_KEY}

try:
    resp_corp = requests.get(url_corp, params=params_corp, timeout=15)
    print(f"  - HTTP Status Code: {resp_corp.status_code}")
    print(f"  - Content-Type: {resp_corp.headers.get('Content-Type')}")
    print(f"  - Content-Length: {len(resp_corp.content):,} bytes")
    
    if resp_corp.status_code == 200 and resp_corp.headers.get('Content-Type') == 'application/x-zip-compressed':
        print("  - [PASS] corpCode.xml 정상 수신 (ZIP 파일 반환 확인)")
    else:
        print(f"  - [WARN] 응답 상태 또는 Content-Type 비정상: {resp_corp.text[:200]}")
except Exception as e:
    print(f"  - [FAIL] corpCode.xml 통신 오류: {e}")

# ── 3. fnlttSinglAcntAll.json 연결 테스트 (삼성전자 2023년 사업보고서 기준) ─────
print("\n[3] OpenDART fnlttSinglAcntAll.json (전체 재무제표) 연결 테스트...")
url_fs = f"{BASE_URL}/fnlttSinglAcntAll.json"
test_params = {
    "crtfc_key": DART_API_KEY,
    "corp_code": "00126380",  # 삼성전자 고유번호
    "bsns_year": "2023",
    "reprt_code": "11011",    # 사업보고서
    "fs_div": "CFS"           # 연결재무제표
}

try:
    resp_fs = requests.get(url_fs, params=test_params, timeout=15)
    print(f"  - HTTP Status Code: {resp_fs.status_code}")
    
    if resp_fs.status_code == 200:
        data = resp_fs.json()
        api_status = data.get("status")
        api_message = data.get("message")
        item_count = len(data.get("list", []))
        
        print(f"  - API Status Code: {api_status}")
        print(f"  - API Response Message: {api_message}")
        print(f"  - 조회된 재무 계정 행 수: {item_count}건")
        
        if api_status == "000":
            print("  - [PASS] fnlttSinglAcntAll.json API 통신 및 데이터 반환 정상 (status=000 정상)")
        else:
            print(f"  - [WARN] OpenDART API 오류 코드 반환: {api_status} ({api_message})")
    else:
        print(f"  - [FAIL] HTTP 비정상 응답: {resp_fs.status_code}")
except Exception as e:
    print(f"  - [FAIL] fnlttSinglAcntAll.json 통신 오류: {e}")

print("\n" + "="*60)
print("[DONE] OpenDART API 연결 테스트 완료")
print("="*60)
