"""
STEP 2: OpenDART API 연결 테스트 - 삼성전자 2021~2023 재무제표 조회
실행: python step02_dart_test.py
"""

import os
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path

# ── 환경변수 로드 ──────────────────────────────────────────────────────────────
load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")

if not DART_API_KEY:
    raise EnvironmentError("[ERROR] DART_API_KEY 환경변수가 없습니다. .env 파일을 확인하세요.")

print(f"[OK] DART_API_KEY 로드 완료 (앞 4자리: {DART_API_KEY[:4]}****)")

# ── 삼성전자 기업코드 조회 ──────────────────────────────────────────────────────
BASE_URL = "https://opendartreader.dart.fss.or.kr/api"

# 삼성전자 stock code = 005930, corp_code는 고유번호 조회 필요
# DART에서는 corp_code(8자리)를 사용 → 기업코드 목록(ZIP) 에서 조회하거나 company API 사용
print("\n[STEP 2-1] 삼성전자 기업코드 조회 ...")

COMPANY_URL = "https://opendart.fss.or.kr/api/company.json"
params = {
    "crtfc_key": DART_API_KEY,
    "stock_code": "005930"  # 삼성전자 주식코드
}
resp = requests.get(COMPANY_URL, params=params, timeout=10)
print(f"  HTTP Status: {resp.status_code}")

company_data = resp.json()
print(f"  API Status: {company_data.get('status')}")
print(f"  API Message: {company_data.get('message')}")

if company_data.get("status") != "000":
    print("[FAIL] 기업 조회 실패. API Key 또는 네트워크를 확인하세요.")
    raise SystemExit(1)

corp_code = company_data.get("corp_code")
corp_name = company_data.get("corp_name")
print(f"  기업코드(corp_code): {corp_code}")
print(f"  기업명(corp_name): {corp_name}")

# ── 연도별 재무제표 조회 ────────────────────────────────────────────────────────
FS_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

YEARS = ["2021", "2022", "2023"]
REPRT_CODE = "11011"  # 사업보고서

all_results = {}

for year in YEARS:
    print(f"\n[STEP 2-2] {year}년 재무제표 조회 ({corp_name}) ...")

    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": year,
        "reprt_code": REPRT_CODE,
        "fs_div": "CFS"  # 연결재무제표 (없으면 OFS 개별 시도)
    }

    resp = requests.get(FS_URL, params=params, timeout=15)
    print(f"  HTTP Status: {resp.status_code}")

    data = resp.json()
    status = data.get("status")
    message = data.get("message")
    print(f"  API Status: {status}")
    print(f"  API Message: {message}")

    if status != "000":
        print(f"  [WARN] {year}년 연결재무제표 조회 실패 → 개별재무제표 시도")
        params["fs_div"] = "OFS"
        resp = requests.get(FS_URL, params=params, timeout=15)
        data = resp.json()
        status = data.get("status")
        print(f"  API Status (OFS): {status}")
        print(f"  API Message (OFS): {data.get('message')}")

    if status != "000":
        print(f"  [FAIL] {year}년 재무제표 조회 실패")
        all_results[year] = None
        continue

    items = data.get("list", [])
    df = pd.DataFrame(items)
    print(f"  조회 행 수: {len(df)}")

    # corp_code, corp_name, bsns_year 컬럼 보강
    df["corp_code"] = corp_code
    df["corp_name"] = corp_name
    df["bsns_year"] = year

    all_results[year] = df

    # 원본 JSON 저장
    raw_dir = Path(f"data/raw/dart/{year}")
    raw_dir.mkdir(parents=True, exist_ok=True)

    json_path = raw_dir / f"{corp_code}_{year}_raw.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  원본 JSON 저장: {json_path}")

    # CSV 저장
    cols_to_save = [
        "corp_code", "corp_name", "bsns_year", "reprt_code",
        "account_id", "account_nm", "sj_nm", "fs_nm",
        "thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"
    ]
    existing_cols = [c for c in cols_to_save if c in df.columns]
    csv_path = raw_dir / f"{corp_code}_{year}.csv"
    df[existing_cols].to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  CSV 저장: {csv_path}")

    # 컬럼 목록 확인
    print(f"\n  [컬럼 목록]")
    for col in df.columns:
        print(f"    - {col}")

    # 주요 계정 키워드 탐색
    KEYWORDS = ["영업이익", "이자", "금융원가", "금융비용", "차입", "단기차입", "장기차입", "사채", "유동성장기"]
    if "account_nm" in df.columns:
        print(f"\n  [계정 탐색 결과] 키워드: {KEYWORDS}")
        mask = df["account_nm"].str.contains("|".join(KEYWORDS), na=False)
        found = df[mask][["account_nm", "account_id", "sj_nm", "fs_nm", "thstrm_amount"]].drop_duplicates()
        if len(found) > 0:
            print(found.to_string(index=False))
        else:
            print("  [NOTE] 해당 키워드 계정 없음")

print("\n" + "="*60)
print("STEP 2 완료 요약")
print("="*60)
for year, df in all_results.items():
    if df is not None:
        print(f"  {year}: {len(df)}행 조회 성공")
    else:
        print(f"  {year}: 조회 실패")
print("="*60)
