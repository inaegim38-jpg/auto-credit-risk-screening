"""
STEP 5: OpenDART 테스트 데이터 수집 및 정밀 검증
- 대상 기업: 5개사 (삼성전자, SK하이닉스, LG전자, 현대자동차, POSCO홀딩스)
- 사업연도: 2021, 2022, 2023 (사업보고서 11011 기준)
- 필수 필드 보존:
  - corp_code, company_name, fiscal_year, report_type
  - account_id_raw, account_name_raw, sj_nm, fs_div
  - amount, unit, source, collected_at
- 결측값(NULL) 원형 보존 (0으로 임의 변환 금지)

실행: python step05_collect_dart_test.py
"""

import os
import glob
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")

TARGET_COMPANIES = [
    {"corp_code": "00126380", "company_name": "삼성전자", "stock_code": "005930"},
    {"corp_code": "00164779", "company_name": "SK하이닉스", "stock_code": "000660"},
    {"corp_code": "00401731", "company_name": "LG전자", "stock_code": "066570"},
    {"corp_code": "00164742", "company_name": "현대자동차", "stock_code": "005380"},
    {"corp_code": "00155319", "company_name": "POSCO홀딩스", "stock_code": "005490"}
]
YEARS = ["2021", "2022", "2023"]
REPORT_TYPE = "11011"  # 사업보고서

print(f"[STEP 5] 5개 기업 × 3개년 OpenDART 수집 데이터 검증 및 표준화 정비...")

all_rows = []
summary_records = []

for comp in TARGET_COMPANIES:
    c_code = comp["corp_code"]
    c_name = comp["company_name"]
    
    for year in YEARS:
        csv_path = Path(f"data/raw/dart/{year}/{c_code}_{year}.csv")
        json_path = Path(f"data/raw/dart/{year}/{c_code}_{year}_CFS_raw.json")
        
        if not csv_path.exists():
            print(f"  [MISSING] {c_name} {year}년 CSV 파일 없음: {csv_path}")
            continue
            
        df = pd.read_csv(csv_path)
        row_count = len(df)
        
        # 필수 필드 매핑 및 검증
        for _, r in df.iterrows():
            raw_amt = r.get("thstrm_amount")
            # NaN인 경우 None(NULL)으로 보존
            amt = None if pd.isna(raw_amt) else float(raw_amt)
            
            all_rows.append({
                "corp_code": str(r.get("corp_code", c_code)).zfill(8),
                "company_name": c_name,
                "fiscal_year": str(year),
                "report_type": REPORT_TYPE,
                "account_id_raw": None if pd.isna(r.get("account_id")) else str(r.get("account_id")),
                "account_name_raw": str(r.get("account_nm", "")).strip(),
                "sj_nm": None if pd.isna(r.get("sj_nm")) else str(r.get("sj_nm")).strip(),
                "fs_div": str(r.get("fs_div_used", "CFS")),
                "amount": amt,
                "unit": "KRW",
                "source": "OpenDART API (fnlttSinglAcntAll)",
                "collected_at": datetime.now(timezone.utc).isoformat()
            })
            
        summary_records.append({
            "기업명": c_name,
            "corp_code": c_code,
            "사업연도": year,
            "보고서": "사업보고서",
            "수집행수": row_count,
            "JSON존재": "O" if json_path.exists() else "X",
            "CSV존재": "O" if csv_path.exists() else "X"
        })

df_all = pd.DataFrame(all_rows)
df_summary = pd.DataFrame(summary_records)

print("\n" + "="*70)
print("수집 데이터 현황 요약 (5개 기업 × 3개년 = 15개 데이터셋)")
print("="*70)
print(df_summary.to_string(index=False))

print("\n" + "="*70)
print("전체 수집 행 검증 결과")
print("="*70)
print(f"총 수집 레코드 수: {len(df_all):,}건")
print(f"corp_code 결측 수: {df_all['corp_code'].isna().sum()}건")
print(f"company_name 결측 수: {df_all['company_name'].isna().sum()}건")
print(f"fiscal_year 결측 수: {df_all['fiscal_year'].isna().sum()}건")
print(f"account_name_raw 결측 수: {df_all['account_name_raw'].isna().sum()}건")
print(f"금액(amount) 실측 결측(NULL) 보존 건수: {df_all['amount'].isna().sum()}건")

# 통합 검증 데이터셋 저장 (finance_raw 적재 준비용)
output_path = Path("data/finance_raw_prepared.csv")
df_all.to_csv(output_path, index=False, encoding="utf-8-sig")
print(f"\n[저장] finance_raw 적재 준비 데이터셋 저장 완료: {output_path}")
print("="*70)
