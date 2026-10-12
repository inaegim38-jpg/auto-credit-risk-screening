"""
STEP 7: 5개 기업으로 확대 - 계정명 차이 확인
목적: 기업마다 DART 계정명이 어떻게 다른지 확인
대상: 삼성전자, SK하이닉스, LG전자, 현대차, POSCO홀딩스
실행: python step07_five_companies.py
"""

import os
import io
import json
import zipfile
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")
print(f"[OK] DART_API_KEY: {DART_API_KEY[:4]}****")

BASE_DART = "https://opendart.fss.or.kr/api"
YEARS = ["2021", "2022", "2023"]
REPRT_CODE = "11011"
KEYWORDS = ["영업이익", "이자", "금융원가", "금융비용", "차입", "단기차입", "장기차입", "사채", "유동성장기"]

# 5개 기업 대상 (stock_code)
TARGET_STOCKS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "066570": "LG전자",
    "005380": "현대자동차",
    "005490": "POSCO홀딩스"
}

# ── 1. 기업코드 목록 로드 (캐시 우선) ─────────────────────────────────────────
corp_cache = Path("data/corp_code_list.csv")
if corp_cache.exists():
    print(f"\n[1] 기업코드 캐시 로드: {corp_cache}")
    df_corp = pd.read_csv(corp_cache, encoding="utf-8-sig", dtype=str)
else:
    print(f"\n[1] 기업코드 목록 다운로드 ...")
    resp = requests.get(f"{BASE_DART}/corpCode.xml", params={"crtfc_key": DART_API_KEY}, timeout=30)
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    xml_bytes = zf.read("CORPCODE.xml")
    df_corp = pd.read_xml(io.BytesIO(xml_bytes), parser="lxml", dtype=str)
    df_corp.to_csv(corp_cache, index=False, encoding="utf-8-sig")

df_corp["stock_code_str"] = df_corp["stock_code"].astype(str).str.strip().str.zfill(6)
print(f"  전체 기업수: {len(df_corp):,}")

# ── 2. 5개 기업 corp_code 조회 ─────────────────────────────────────────────────
print(f"\n[2] 5개 기업 corp_code 조회")
corp_list = []
for stock_code, label in TARGET_STOCKS.items():
    row = df_corp[df_corp["stock_code_str"] == stock_code]
    if row.empty:
        print(f"  [WARN] {label}({stock_code}) 기업코드 없음")
        continue
    corp_code = str(row.iloc[0]["corp_code"]).zfill(8)
    corp_name = row.iloc[0]["corp_name"]
    corp_list.append({"stock_code": stock_code, "corp_code": corp_code, "corp_name": corp_name})
    print(f"  {corp_name}: corp_code={corp_code}")

# ── 3. 재무제표 조회 ───────────────────────────────────────────────────────────
FS_URL = f"{BASE_DART}/fnlttSinglAcntAll.json"
all_data = {}  # {corp_code: {year: df}}

for corp in corp_list:
    corp_code = corp["corp_code"]
    corp_name = corp["corp_name"]
    print(f"\n[3] {corp_name} ({corp_code}) 재무제표 조회")
    all_data[corp_code] = {}

    for year in YEARS:
        for fs_div in ["CFS", "OFS"]:
            params = {
                "crtfc_key": DART_API_KEY,
                "corp_code": corp_code,
                "bsns_year": year,
                "reprt_code": REPRT_CODE,
                "fs_div": fs_div
            }
            resp = requests.get(FS_URL, params=params, timeout=20)
            data = resp.json()
            status = data.get("status")
            items = data.get("list", [])
            print(f"  {year}/{fs_div}: status={status} | 행수={len(items)}")

            if status == "000" and items:
                df = pd.DataFrame(items)
                df["corp_code"] = corp_code
                df["corp_name"] = corp_name
                df["bsns_year"] = year
                df["fs_div_used"] = fs_div
                all_data[corp_code][year] = df

                # 저장
                raw_dir = Path(f"data/raw/dart/{year}")
                raw_dir.mkdir(parents=True, exist_ok=True)
                json_path = raw_dir / f"{corp_code}_{year}_{fs_div}_raw.json"
                if not json_path.exists():
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)

                # CSV 저장
                cols = [
                    "corp_code","corp_name","bsns_year","reprt_code",
                    "account_id","account_nm","sj_nm",
                    "thstrm_amount","frmtrm_amount","bfefrmtrm_amount","fs_div_used"
                ]
                existing = [c for c in cols if c in df.columns]
                csv_path = raw_dir / f"{corp_code}_{year}.csv"
                df[existing].to_csv(csv_path, index=False, encoding="utf-8-sig")
                break

# ── 4. 기업별 계정 매핑 비교표 ─────────────────────────────────────────────────
print(f"\n{'='*80}")
print("기업별 계정 탐색 결과 비교")
print("="*80)

# 표준 항목별 매핑 구조
MAPPING_TARGETS = {
    "영업이익": "operating_income",
    "이자비용": "interest_expense",
    "단기차입금": "short_term_debt",
    "장기차입금": "long_term_debt",
    "유동성장기부채": "current_long_term_debt",
    "사채": "bonds_payable",
    "금융비용": "finance_costs",
    "이자의 지급": "interest_paid_cf",
}

rows_mapping = []
for corp in corp_list:
    corp_code = corp["corp_code"]
    corp_name = corp["corp_name"]

    for year, df in all_data.get(corp_code, {}).items():
        if df is None or "account_nm" not in df.columns:
            continue
        mask = df["account_nm"].str.contains("|".join(KEYWORDS), na=False)
        found = df[mask][["account_nm", "account_id", "sj_nm", "thstrm_amount"]].drop_duplicates("account_nm")

        for _, row in found.iterrows():
            rows_mapping.append({
                "corp_name": corp_name,
                "corp_code": corp_code,
                "year": year,
                "account_nm": row["account_nm"],
                "account_id": row["account_id"],
                "sj_nm": row.get("sj_nm", ""),
                "thstrm_amount": row.get("thstrm_amount", "")
            })

df_mapping = pd.DataFrame(rows_mapping)

# 기업 × 계정명 피벗 (연도 무관, 계정명만 확인)
print("\n[계정명 유니크 목록 - 기업별]")
if not df_mapping.empty:
    for corp in corp_list:
        cn = corp["corp_name"]
        sub = df_mapping[df_mapping["corp_name"] == cn][["account_nm","account_id","sj_nm"]].drop_duplicates("account_nm")
        print(f"\n  [{cn}]")
        print(sub.to_string(index=False))

# 전체 매핑표 저장
mapping_path = Path("data/account_mapping_raw.csv")
df_mapping.to_csv(mapping_path, index=False, encoding="utf-8-sig")
print(f"\n[저장] 계정 매핑 원본: {mapping_path}")

# ── 5. 조회 요약 ────────────────────────────────────────────────────────────────
print(f"\n{'='*80}")
print("STEP 7 요약 - 5개 기업 조회 결과")
print("="*80)
print(f"{'기업명':<15} {'corp_code':<12} {'2021':>6} {'2022':>6} {'2023':>6}")
print("-"*50)
for corp in corp_list:
    cc = corp["corp_code"]
    cn = corp["corp_name"]
    counts = {y: len(all_data.get(cc, {}).get(y, [])) for y in YEARS}
    print(f"{cn:<15} {cc:<12} {counts['2021']:>6} {counts['2022']:>6} {counts['2023']:>6}")
print("="*80)
print("다음 단계: step08_db_design.md 확인")
