"""
STEP 10: ECOS 기준금리 시계열 수집 및 ecos_rate 적재
- 원천: ECOS API (통계코드 722Y001, 항목 0101000 한국은행 기준금리)
- 대상: public.ecos_rate
- 기간: 2017-01-01 ~ 2023-12-31 (2,556행)
- 원칙:
  - 날짜와 금리를 반드시 함께 저장
  - 기간말(연말) 값 정렬 및 집계 정합성 검증 (Grain 맞추기)
  - 시나리오 충격 가공은 일절 배제 (순수 원천 시계열 저장)

실행: python step10_load_ecos_rate.py
"""

import os
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "finance_lab")
DB_USER = os.getenv("DB_USER", "lab_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "lab_admin_2026")

csv_path = "data/ecos/base_rate.csv"
if not os.path.exists(csv_path):
    raise FileNotFoundError(f"[FAIL] 기준금리 원천 CSV 없음: {csv_path}")

df = pd.read_csv(csv_path)
print(f"[1] ECOS 기준금리 원천 데이터 로드 완료: {len(df):,}건 ({csv_path})")

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
conn.autocommit = False
cur = conn.cursor()

print(f"[2] PostgreSQL 연결 완료: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# 배치 INSERT 튜플 준비
now_iso = datetime.now(timezone.utc).isoformat()
tuples = [
    (
        pd.to_datetime(r["rate_date"]).strftime("%Y-%m-%d"),
        str(r.get("rate_name", "한국은행 기준금리")),
        float(r["rate_value"]),
        "연%",
        "ECOS API (722Y001/0101000)",
        now_iso
    )
    for _, r in df.iterrows()
]

upsert_sql = """
    INSERT INTO public.ecos_rate (
        date, indicator, rate, unit, source, collected_at
    ) VALUES %s
    ON CONFLICT (date, indicator)
    DO UPDATE SET
        rate = EXCLUDED.rate,
        unit = EXCLUDED.unit,
        source = EXCLUDED.source,
        collected_at = EXCLUDED.collected_at;
"""

print(f"[3] public.ecos_rate 에 {len(tuples):,}건 배치 UPSERT 실행...")
execute_values(cur, upsert_sql, tuples, page_size=1000)
conn.commit()
print("  - 적재 및 COMMIT 완료")

# ── 4. 적재 데이터 검증 ────────────────────────────────────────────────────────
print("\n" + "="*80)
print("[4] public.ecos_rate 적재 검증 및 기간말(연말) 기준금리 정렬")
print("="*80)

cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM public.ecos_rate;")
cnt, min_d, max_d = cur.fetchone()
print(f"총 적재 건수: {cnt:,}건 | 기간: {min_d} ~ {max_d}")

# 연도별 기간말(연말 마지막 영업일) 기준금리 추출 쿼리 (Grain 맞춤)
year_end_query = """
    SELECT 
        EXTRACT(YEAR FROM date)::INT AS fiscal_year,
        date AS rate_date,
        rate AS base_rate,
        unit
    FROM (
        SELECT date, rate, unit,
               ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM date) ORDER BY date DESC) AS rn
        FROM public.ecos_rate
        WHERE indicator = '한국은행 기준금리'
    ) sub
    WHERE rn = 1
    ORDER BY fiscal_year;
"""
cur.execute(year_end_query)
rows = cur.fetchall()
df_year_end = pd.DataFrame(rows, columns=["fiscal_year", "rate_date", "base_rate", "unit"])

print("\n[연도별 기간말 기준금리 정렬 결과 (Grain: 연도 1개)]")
print(df_year_end.to_string(index=False))

cur.close()
conn.close()
print("\n" + "="*80)
print("[DONE] STEP 10 ECOS 기준금리 수집 및 적재 완료")
print("="*80)
