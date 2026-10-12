"""
STEP 5: ECOS API 연결 테스트 - 한국은행 기준금리 조회
STEP 6: 연도별 기준금리로 변환 (연말 기준)
실행: python step05_ecos_test.py
"""

import os
import json
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ECOS_API_KEY = os.getenv("ECOS_API_KEY")
if not ECOS_API_KEY:
    raise EnvironmentError("[ERROR] ECOS_API_KEY 환경변수 없음")
print(f"[OK] ECOS_API_KEY 로드: {ECOS_API_KEY[:4]}****")

# ── STEP 5-1: ECOS API 기준금리 조회 ──────────────────────────────────────────
# 통계표: 722Y001 = 한국은행 기준금리 (일별)
# 주기: D (일별)
# 항목: 0101000 = 한국은행 기준금리

BASE_ECOS = "https://ecos.bok.or.kr/api"
STAT_CODE = "722Y001"
CYCLE = "D"
ITEM_CODE1 = "0101000"
START_DATE = "20170101"
END_DATE = "20231231"
FMT = "json"
LANG = "kr"
START_IDX = 1
END_IDX = 10000  # 충분히 크게

url = f"{BASE_ECOS}/StatisticSearch/{ECOS_API_KEY}/{FMT}/{LANG}/{START_IDX}/{END_IDX}/{STAT_CODE}/{CYCLE}/{START_DATE}/{END_DATE}/{ITEM_CODE1}"

print(f"\n[STEP 5-1] ECOS API 호출 ...")
print(f"  URL (key 마스킹): .../{ECOS_API_KEY[:4]}****/...")
resp = requests.get(url, timeout=20)
print(f"  HTTP Status: {resp.status_code}")

data = resp.json()

# 응답 구조 확인
top_keys = list(data.keys())
print(f"  응답 최상위 키: {top_keys}")

if "StatisticSearch" not in data:
    print(f"  [FAIL] StatisticSearch 없음. 응답 내용:")
    print(json.dumps(data, ensure_ascii=False, indent=2)[:500])
    raise SystemExit(1)

ss = data["StatisticSearch"]
print(f"  list_total_count: {ss.get('list_total_count')}")
print(f"  결과 코드: {ss.get('err_msg', '없음')}")

rows = ss.get("row", [])
print(f"  조회 행 수: {len(rows)}")

if not rows:
    print("[FAIL] 데이터 없음")
    raise SystemExit(1)

# ── STEP 5-2: DataFrame 변환 ──────────────────────────────────────────────────
print(f"\n[STEP 5-2] DataFrame 변환 ...")
df = pd.DataFrame(rows)
print(f"  컬럼: {df.columns.tolist()}")
print(f"\n  샘플 (상위 5행):")
print(df.head(5).to_string(index=False))
print(f"\n  샘플 (하위 5행):")
print(df.tail(5).to_string(index=False))

# 표준 컬럼으로 정리
# ECOS 응답: STAT_CODE, STAT_NAME, ITEM_CODE1, ITEM_NAME1, TIME, DATA_VALUE 등
rename_map = {
    "TIME": "rate_date_raw",
    "DATA_VALUE": "rate_value_raw",
    "ITEM_NAME1": "rate_name"
}
df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

# 날짜 파싱 (ECOS 일별: YYYYMMDD)
df["rate_date"] = pd.to_datetime(df["rate_date_raw"], format="%Y%m%d", errors="coerce")
df["rate_value"] = pd.to_numeric(df["rate_value_raw"], errors="coerce")
df["rate_name"] = df.get("rate_name", "한국은행 기준금리")

# 최종 정리
df_rate = df[["rate_date", "rate_name", "rate_value"]].dropna(subset=["rate_date", "rate_value"])
df_rate = df_rate.sort_values("rate_date").reset_index(drop=True)

print(f"\n  정리 후 DataFrame:")
print(f"  컬럼: {df_rate.columns.tolist()}")
print(f"  행수: {len(df_rate)}")
print(f"  기간: {df_rate['rate_date'].min()} ~ {df_rate['rate_date'].max()}")
print(f"\n  샘플:")
print(df_rate.head(3).to_string(index=False))
print("  ...")
print(df_rate.tail(3).to_string(index=False))

# 원본 JSON 저장
ecos_dir = Path("data/ecos")
ecos_dir.mkdir(parents=True, exist_ok=True)
json_path = ecos_dir / "base_rate_raw.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"\n  [저장] JSON: {json_path}")

csv_path = ecos_dir / "base_rate.csv"
df_rate.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"  [저장] CSV: {csv_path}")

# ── STEP 6: 연도별 기준금리 변환 ────────────────────────────────────────────────
print(f"\n{'='*60}")
print("STEP 6: 연도별 기준금리 변환 (연말 기준)")
print("="*60)

df_rate["fiscal_year"] = df_rate["rate_date"].dt.year

# 연말 기준: 각 연도의 마지막 날짜 레코드 선택
df_annual = (
    df_rate
    .sort_values("rate_date")
    .groupby("fiscal_year")
    .last()
    .reset_index()
    [["fiscal_year", "rate_value", "rate_date"]]
    .rename(columns={"rate_value": "base_rate"})
)

print(f"\n  연도별 기준금리 (core_annual_interest_rate):")
print(df_annual.to_string(index=False))

# 저장
annual_path = ecos_dir / "annual_base_rate.csv"
df_annual.to_csv(annual_path, index=False, encoding="utf-8-sig")
print(f"\n  [저장] CSV: {annual_path}")

# ── 요약 ───────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("STEP 5~6 요약")
print("="*60)
print(f"  API 호출 성공: {'O' if resp.status_code == 200 else 'X'}")
print(f"  조회 기간: {df_rate['rate_date'].min().date()} ~ {df_rate['rate_date'].max().date()}")
print(f"  조회 행수: {len(df_rate)}")
print(f"  기준금리 컬럼: rate_date, rate_name, rate_value")
print(f"\n  연말 기준금리:")
for _, row in df_annual[df_annual["fiscal_year"].between(2021, 2023)].iterrows():
    print(f"    {int(row['fiscal_year'])}년말: {row['base_rate']}% ({row['rate_date'].date()})")
print("="*60)
print("다음 단계: python step07_five_companies.py")
