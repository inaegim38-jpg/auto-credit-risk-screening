"""
STEP 6: finance_raw 테이블 데이터 적재
- 대상: public.finance_raw
- 원천: data/finance_raw_prepared.csv (3,100건)
- 적재 원칙:
  - 결측값(NULL) 원형 보존 (0으로 변환 금지)
  - 배치 INSERT (psycopg2.extras.execute_values)로 고속/안정 적재
  - 적재 후 기업별, 연도별 데이터 건수 검증

실행: python step06_load_finance_raw.py
"""

import os
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "finance_lab")
DB_USER = os.getenv("DB_USER", "lab_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "lab_admin_2026")

csv_file = "data/finance_raw_prepared.csv"
if not os.path.exists(csv_file):
    raise FileNotFoundError(f"[FAIL] 적재 원천 파일 없음: {csv_file}")

df = pd.read_csv(csv_file)
print(f"[1] 적재 원천 파일 로드 완료: {len(df):,}건 ({csv_file})")

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

# 기존 public.finance_raw 데이터 확인 및 정리 (재실행 멱등성 보장)
cur.execute("SELECT COUNT(*) FROM public.finance_raw;")
existing_count = cur.fetchone()[0]
if existing_count > 0:
    print(f"  - 기존 데이터 존재 ({existing_count:,}건). 재적재를 위해 초기화(TRUNCATE) 수행...")
    cur.execute("TRUNCATE TABLE public.finance_raw RESTART IDENTITY;")

# 배치 적재 튜플 준비
records = []
for _, r in df.iterrows():
    amt = None if pd.isna(r["amount"]) else float(r["amount"])
    aid = None if pd.isna(r["account_id_raw"]) else str(r["account_id_raw"])
    sj = None if pd.isna(r["sj_nm"]) else str(r["sj_nm"])
    
    records.append((
        str(r["corp_code"]).zfill(8),
        str(r["company_name"]),
        str(r["fiscal_year"]),
        str(r["report_type"]),
        aid,
        str(r["account_name_raw"]),
        sj,
        str(r.get("fs_div", "CFS")),
        amt,
        str(r.get("unit", "KRW")),
        str(r.get("source", "OpenDART API")),
        str(r["collected_at"])
    ))

insert_sql = """
    INSERT INTO public.finance_raw (
        corp_code, company_name, fiscal_year, report_type,
        account_id_raw, account_name_raw, sj_nm, fs_div,
        amount, unit, source, collected_at
    ) VALUES %s
"""

print(f"[3] public.finance_raw 에 {len(records):,}건 배치 INSERT 실행...")
execute_values(cur, insert_sql, records, page_size=1000)
conn.commit()
print("  - 적재 완료 및 COMMIT 성공")

# ── 4. 적재 검증 쿼리 실행 ────────────────────────────────────────────────────
print("\n" + "="*70)
print("[4] 적재 정합성 검증 결과")
print("="*70)

cur.execute("SELECT COUNT(*) FROM public.finance_raw;")
total_loaded = cur.fetchone()[0]
print(f"총 적재 행수: {total_loaded:,}건 (원천 {len(df):,}건과 일치 여부: {'일치' if total_loaded == len(df) else '불일치'})")

cur.execute("""
    SELECT company_name, corp_code, fiscal_year, COUNT(*) AS row_cnt,
           COUNT(amount) AS non_null_amt,
           COUNT(*) - COUNT(amount) AS null_amt
    FROM public.finance_raw
    GROUP BY company_name, corp_code, fiscal_year
    ORDER BY company_name, fiscal_year;
""")
summary_rows = cur.fetchall()
col_names = [d[0] for d in cur.description]
df_res = pd.DataFrame(summary_rows, columns=col_names)
print("\n[기업 × 연도별 적재 현황]")
print(df_res.to_string(index=False))

cur.close()
conn.close()
print("\n" + "="*70)
print("[DONE] STEP 6 public.finance_raw 적재 완료")
print("="*70)
