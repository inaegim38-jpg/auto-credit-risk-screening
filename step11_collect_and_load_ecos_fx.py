"""
STEP 11: ECOS 주요 통화 환율 수집 및 ecos_fx 적재
- 통계표: 731Y001 (주요국 통화의 대원화 환율)
- 주기: D (일별)
- 수집 통화:
  - 0000001: 미국 달러 (USD)
  - 0000002: 일본 엔 (JPY, 100엔 기준)
  - 0000003: 유로 (EUR)
- 기간: 2021-01-01 ~ 2023-12-31 (재무제표 대상 기간 일치)
- 대상 테이블: public.ecos_fx
- Grain: 날짜(date) × 통화(currency)
- 원칙:
  - 통화 코드 명확히 보존
  - 기간말(연말) 값 정렬 및 집계 정합성 검증

실행: python step11_collect_and_load_ecos_fx.py
"""

import os
import requests
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ECOS_API_KEY = os.getenv("ECOS_API_KEY")
if not ECOS_API_KEY:
    raise EnvironmentError("[FAIL] ECOS_API_KEY 환경변수가 없습니다.")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "finance_lab")
DB_USER = os.getenv("DB_USER", "lab_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "lab_admin_2026")

BASE_ECOS = "https://ecos.bok.or.kr/api"
STAT_CODE = "731Y001"  # 주요국 통화의 대원화 환율
CYCLE = "D"
START_DATE = "20210101"
END_DATE = "20231231"

CURRENCIES = [
    {"code": "0000001", "symbol": "USD", "name": "미국 달러"},
    {"code": "0000002", "symbol": "JPY", "name": "일본 엔(100엔)"},
    {"code": "0000003", "symbol": "EUR", "name": "유로"}
]

print(f"[1] ECOS 환율 API 수집 시작 (기간: {START_DATE} ~ {END_DATE})...")
all_fx_rows = []

for curr in CURRENCIES:
    item_code = curr["code"]
    symbol = curr["symbol"]
    url = f"{BASE_ECOS}/StatisticSearch/{ECOS_API_KEY}/json/kr/1/5000/{STAT_CODE}/{CYCLE}/{START_DATE}/{END_DATE}/{item_code}"
    
    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        print(f"  [FAIL] {symbol} HTTP 요청 실패: {resp.status_code}")
        continue
        
    data = resp.json()
    if "StatisticSearch" not in data:
        print(f"  [WARN] {symbol} 응답 내 StatisticSearch 없음: {data}")
        continue
        
    rows = data["StatisticSearch"].get("row", [])
    print(f"  - {symbol} ({curr['name']}): {len(rows)}건 수신 성공")
    
    for r in rows:
        val_str = r.get("DATA_VALUE")
        if not val_str:
            continue
        try:
            val = float(val_str)
        except ValueError:
            continue
            
        rdate = pd.to_datetime(r["TIME"], format="%Y%m%d").strftime("%Y-%m-%d")
        all_fx_rows.append({
            "date": rdate,
            "currency": symbol,
            "exchange_rate": val,
            "unit": "KRW",
            "source": f"ECOS API (731Y001 / {item_code})",
            "collected_at": datetime.now(timezone.utc).isoformat()
        })

df_fx = pd.DataFrame(all_fx_rows)
print(f"\n총 수집된 환율 데이터: {len(df_fx):,}건")

# CSV 파일 백업 저장
Path("data/ecos").mkdir(parents=True, exist_ok=True)
csv_save_path = "data/ecos/fx_rate_raw.csv"
df_fx.to_csv(csv_save_path, index=False, encoding="utf-8-sig")
print(f"[2] 원천 CSV 저장 완료: {csv_save_path}")

# ── 3. PostgreSQL public.ecos_fx 적재 ────────────────────────────────────────
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
conn.autocommit = False
cur = conn.cursor()

print(f"\n[3] PostgreSQL 연결 완료: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

insert_tuples = [
    (
        r["date"],
        r["currency"],
        r["exchange_rate"],
        r["unit"],
        r["source"],
        r["collected_at"]
    )
    for _, r in df_fx.iterrows()
]

upsert_sql = """
    INSERT INTO public.ecos_fx (
        date, currency, exchange_rate, unit, source, collected_at
    ) VALUES %s
    ON CONFLICT (date, currency)
    DO UPDATE SET
        exchange_rate = EXCLUDED.exchange_rate,
        unit = EXCLUDED.unit,
        source = EXCLUDED.source,
        collected_at = EXCLUDED.collected_at;
"""

print(f"[4] public.ecos_fx 에 {len(insert_tuples):,}건 배치 UPSERT 실행...")
execute_values(cur, upsert_sql, insert_tuples, page_size=1000)
conn.commit()
print("  - 적재 및 COMMIT 완료")

# ── 5. 검증 및 연도별 기간말(연말) 환율 정렬 ──────────────────────────────────
print("\n" + "="*80)
print("[5] public.ecos_fx 적재 데이터 검증 및 기간말(연말) 환율 정렬")
print("="*80)

cur.execute("SELECT currency, COUNT(*), MIN(date), MAX(date) FROM public.ecos_fx GROUP BY currency ORDER BY currency;")
summary = cur.fetchall()
for c, cnt, d_min, d_max in summary:
    print(f"  통화: {c:<4} | 건수: {cnt:>5}건 | 기간: {d_min} ~ {d_max}")

# 연도별 기간말(마지막 영업일) 환율 피벗 쿼리 (Grain: 연도 × 통화)
year_end_fx_sql = """
    WITH ranked_fx AS (
        SELECT 
            EXTRACT(YEAR FROM date)::INT AS fiscal_year,
            currency,
            exchange_rate,
            date,
            ROW_NUMBER() OVER (
                PARTITION BY EXTRACT(YEAR FROM date), currency 
                ORDER BY date DESC
            ) AS rn
        FROM public.ecos_fx
    )
    SELECT 
        fiscal_year,
        currency,
        exchange_rate AS year_end_rate,
        date AS rate_date
    FROM ranked_fx
    WHERE rn = 1
    ORDER BY fiscal_year, currency;
"""
cur.execute(year_end_fx_sql)
rows_ye = cur.fetchall()
df_ye = pd.DataFrame(rows_ye, columns=["fiscal_year", "currency", "year_end_rate", "rate_date"])

print("\n[연도별 기간말 환율 정렬 결과]")
piv_ye = df_ye.pivot_table(index="fiscal_year", columns="currency", values="year_end_rate")
print(piv_ye.to_string())

cur.close()
conn.close()
print("\n" + "="*80)
print("[DONE] STEP 11 ECOS 환율 수집 및 적재 완료")
print("="*80)
