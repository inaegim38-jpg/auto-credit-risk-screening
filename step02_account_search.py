"""
STEP 2-4 (수정): 계정 탐색
- fs_nm 없음 확인됨 → sj_nm, sj_div 사용
실행: python step02_account_search.py
"""

import os
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

KEYWORDS = ["영업이익", "이자", "금융원가", "금융비용", "차입", "단기차입", "장기차입", "사채", "유동성장기"]
YEARS = ["2021", "2022", "2023"]
CORP_CODE = "00126380"

print("="*70)
print("STEP 2-4: 실제 컬럼 확인 및 계정 탐색")
print("="*70)

for year in YEARS:
    csv_path = Path(f"data/raw/dart/{year}/{CORP_CODE}_{year}.csv")
    if not csv_path.exists():
        print(f"[SKIP] {year}: 파일 없음")
        continue

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    print(f"\n{'─'*60}")
    print(f"[{year}년] 파일: {csv_path}")
    print(f"  행수: {len(df)}, 컬럼: {df.columns.tolist()}")

    # 키워드 탐색
    if "account_nm" not in df.columns:
        print("  account_nm 컬럼 없음")
        continue

    mask = df["account_nm"].str.contains("|".join(KEYWORDS), na=False)
    found = df[mask].copy()

    if found.empty:
        print("  [NOTE] 키워드 매칭 계정 없음")
    else:
        # sj_nm이 있으면 사용, 없으면 sj_div
        sj_col = "sj_nm" if "sj_nm" in found.columns else "sj_div"
        cols_show = ["account_nm", "account_id", sj_col, "thstrm_amount"]
        existing = [c for c in cols_show if c in found.columns]
        result = found[existing].drop_duplicates("account_nm")
        print(result.to_string(index=False))

# ── 전체 연도 합산하여 고유 계정 목록 ────────────────────────────────────────
print(f"\n{'='*70}")
print("전체 연도 통합 계정 탐색 (유니크)")
print("="*70)

all_found = []
for year in YEARS:
    csv_path = Path(f"data/raw/dart/{year}/{CORP_CODE}_{year}.csv")
    if not csv_path.exists():
        continue
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df["year"] = year
    mask = df["account_nm"].str.contains("|".join(KEYWORDS), na=False)
    all_found.append(df[mask])

if all_found:
    combined = pd.concat(all_found, ignore_index=True)
    sj_col = "sj_nm" if "sj_nm" in combined.columns else "sj_div"
    uniq = combined[["account_nm","account_id",sj_col]].drop_duplicates()
    print(uniq.to_string(index=False))
    print(f"\n총 유니크 계정 수: {len(uniq)}")
