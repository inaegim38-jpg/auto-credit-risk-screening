"""
STEP 9: PostgreSQL 적재 및 ELT 파이프라인
1. core.company 에 대상 기업 적재
2. raw.dart_financial 에 DART CSV 적재
3. raw.ecos_base_rate 에 ECOS 기준금리 적재
4. RAW → CORE: core.financial_statement 에 매핑 변환 데이터 적재
5. CORE → MART: CALL mart.refresh_stress_analysis() 호출하여 데이터마트 생성

실행: python step09_load_to_postgres.py
"""

import os
import glob
import psycopg2
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "dart_ecos")
DB_USER = os.getenv("DB_USER", "neondb_owner")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require")

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    sslmode=DB_SSLMODE
)
conn.autocommit = False
cur = conn.cursor()

print(f"[OK] PostgreSQL 연결 성공: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# ── 1. core.company 적재 ──────────────────────────────────────────────────────
print("\n[1] core.company 적재...")
corp_cache = Path("data/corp_code_list.csv")
TARGET_STOCKS = {
    "005930": "삼성전자",
    "000660": "SK하이닉스",
    "066570": "LG전자",
    "005380": "현대자동차",
    "005490": "POSCO홀딩스"
}

if corp_cache.exists():
    df_corp = pd.read_csv(corp_cache, dtype=str)
    df_corp["stock_code_str"] = df_corp["stock_code"].fillna("").astype(str).str.strip().str.zfill(6)
    for stock_code, name in TARGET_STOCKS.items():
        sub = df_corp[df_corp["stock_code_str"] == stock_code]
        if not sub.empty:
            row = sub.iloc[0]
            cc = str(row["corp_code"]).zfill(8)
            cn = row["corp_name"]
            c_eng = row.get("corp_eng_name", "")
            sc = stock_code
            cur.execute("""
                INSERT INTO core.company (corp_code, corp_name, corp_eng_name, stock_code, is_listed)
                VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (corp_code) DO UPDATE
                SET corp_name = EXCLUDED.corp_name,
                    stock_code = EXCLUDED.stock_code,
                    updated_at = NOW();
            """, (cc, cn, c_eng, sc))
            print(f"  - {cn} ({cc}, {sc}) 등록/갱신")
conn.commit()

# ── 2. raw.ecos_base_rate 적재 ─────────────────────────────────────────────────
print("\n[2] raw.ecos_base_rate 적재...")
ecos_file = Path("data/ecos/base_rate.csv")
if ecos_file.exists():
    df_ecos = pd.read_csv(ecos_file)
    count = 0
    for _, row in df_ecos.iterrows():
        rdate = row["rate_date"]
        time_period = pd.to_datetime(rdate).strftime("%Y%m%d")
        rval = float(row["rate_value"])
        rname = row.get("rate_name", "한국은행 기준금리")
        cur.execute("""
            INSERT INTO raw.ecos_base_rate (stat_code, stat_name, item_code1, item_name1, unit_name, time_period, rate_date, data_value)
            VALUES ('722Y001', '1.3.1. 한국은행 기준금리 및 여수신금리', '0101000', %s, '연%%', %s, %s, %s)
            ON CONFLICT (stat_code, item_code1, rate_date) DO UPDATE
            SET data_value = EXCLUDED.data_value;
        """, (rname, time_period, rdate, rval))
        count += 1
    conn.commit()
    print(f"  - ECOS 기준금리 {count}건 적재 완료")

# ── 3. raw.dart_financial 적재 ────────────────────────────────────────────────
print("\n[3] raw.dart_financial 적재...")
dart_files = glob.glob("data/raw/dart/*/*.csv")
total_dart_rows = 0

for fpath in dart_files:
    df = pd.read_csv(fpath)
    for _, r in df.iterrows():
        thstrm = None if pd.isna(r.get("thstrm_amount")) else float(r["thstrm_amount"])
        frmtrm = None if pd.isna(r.get("frmtrm_amount")) else float(r["frmtrm_amount"])
        bfefrmtrm = None if pd.isna(r.get("bfefrmtrm_amount")) else float(r["bfefrmtrm_amount"])
        
        cur.execute("""
            INSERT INTO raw.dart_financial (
                corp_code, corp_name, bsns_year, reprt_code, fs_div,
                sj_nm, account_id, account_nm,
                thstrm_amount, frmtrm_amount, bfefrmtrm_amount
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            str(r["corp_code"]).zfill(8),
            str(r["corp_name"]),
            str(r["bsns_year"]),
            str(r["reprt_code"]),
            str(r.get("fs_div_used", "CFS")),
            str(r.get("sj_nm", "")),
            str(r.get("account_id", "")),
            str(r.get("account_nm", "")),
            thstrm, frmtrm, bfefrmtrm
        ))
        total_dart_rows += 1
conn.commit()
print(f"  - DART 재무제표 원본 {len(dart_files)}개 파일, 총 {total_dart_rows}건 적재 완료")

# ── 4. RAW → CORE (core.financial_statement) 변환 적재 ─────────────────────────
print("\n[4] RAW → CORE (core.financial_statement) 정규화 매핑 변환...")
cur.execute("""
    WITH ranked_mapping AS (
        SELECT
            r.id AS raw_dart_id,
            r.corp_code,
            r.bsns_year::SMALLINT AS fiscal_year,
            m.standard_account,
            r.thstrm_amount AS amount,
            r.account_id AS source_account_id,
            r.account_nm AS source_account_nm,
            r.sj_nm AS source_sj_nm,
            r.fs_div,
            m.id AS mapping_rule_id,
            m.priority,
            ROW_NUMBER() OVER (
                PARTITION BY r.corp_code, r.bsns_year, m.standard_account
                ORDER BY m.priority ASC, r.id DESC
            ) AS rn
        FROM raw.dart_financial r
        JOIN core.account_mapping m
          ON (
                (m.source_account_id = r.account_id AND r.account_id NOT LIKE '%-표준계정코드 미사용-%')
                OR
                (m.source_account_id = '-표준계정코드 미사용-' AND r.account_nm = m.source_account_nm)
             )
         AND r.sj_nm = m.source_sj_nm
         AND m.is_active = TRUE
         AND r.thstrm_amount IS NOT NULL
    )
    INSERT INTO core.financial_statement (
        corp_code, fiscal_year, standard_account, amount,
        source_account_id, source_account_nm, source_sj_nm,
        fs_div, mapping_rule_id, raw_dart_id
    )
    SELECT
        corp_code, fiscal_year, standard_account, amount,
        source_account_id, source_account_nm, source_sj_nm,
        fs_div, mapping_rule_id, raw_dart_id
    FROM ranked_mapping
    WHERE rn = 1
    ON CONFLICT (corp_code, fiscal_year, standard_account)
    DO UPDATE SET
        amount = EXCLUDED.amount,
        source_account_id = EXCLUDED.source_account_id,
        source_account_nm = EXCLUDED.source_account_nm,
        source_sj_nm = EXCLUDED.source_sj_nm,
        fs_div = EXCLUDED.fs_div,
        mapping_rule_id = EXCLUDED.mapping_rule_id,
        raw_dart_id = EXCLUDED.raw_dart_id;
""")
core_count = cur.rowcount
conn.commit()
print(f"  - core.financial_statement {core_count}건 정규화 매핑 적재 완료")

# ── 5. CORE → MART (mart.refresh_stress_analysis) 실행 ───────────────────────
print("\n[5] CORE → MART: CALL mart.refresh_stress_analysis() 실행...")
cur.execute("CALL mart.refresh_stress_analysis();")
conn.commit()
print("  - 스트레스 분석 마트 갱신 완료")

# ── 6. 검증 조회 ──────────────────────────────────────────────────────────────
print("\n" + "="*80)
print("MART 결과 요약 (mart.v_stress_summary)")
print("="*80)
cur.execute("""
    SELECT corp_name, fiscal_year, scenario_label,
           "영업이익_억원", "이자비용_억원", "총차입금_억원",
           "현재ICR", "시나리오ICR_상한", "시나리오등급_상한"
    FROM mart.v_stress_summary
    WHERE scenario_label = '+2.00%p'
    ORDER BY fiscal_year, corp_name;
""")
rows = cur.fetchall()
col_names = [desc[0] for desc in cur.description]
df_summary = pd.DataFrame(rows, columns=col_names)
print(df_summary.to_string(index=False))

cur.close()
conn.close()
print("\n[DONE] PostgreSQL 데이터 파이프라인 적재 및 분석 완료!")
