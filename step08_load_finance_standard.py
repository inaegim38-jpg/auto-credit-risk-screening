"""
STEP 8: finance_standard 테이블 생성 및 적재
- 원천: public.finance_raw + public.account_mapping_master
- 대상: public.finance_standard
- 핵심 표준 지표 집계:
  1) operating_profit (영업이익)
  2) interest_expense (이자비용: 손익계산서 우선, 현금흐름표 fallback)
  3) debt (총차입금 = 단기차입금 + 유동성장기부채 + 장기차입금 + 사채)
  4) short_term_debt (단기차입금 + 유동성장기부채)
  5) equity (자기자본 = 자본총계)
- Grain: 기업(corp_code) × 사업연도(fiscal_year) × 기간(period) × 재무제표구분(fs_div)
- 결측값 원칙: 0으로 임의 변환 금지, 실측 결측(NULL) 보존

실행: python step08_load_finance_standard.py
"""

import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "finance_lab")
DB_USER = os.getenv("DB_USER", "lab_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "lab_admin_2026")

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
conn.autocommit = False
cur = conn.cursor()

print(f"[1] PostgreSQL 연결 성공: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# ── 2. RAW + MAPPING → STANDARD 변환 SQL 실행 ─────────────────────────────
transform_sql = """
WITH ranked_raw AS (
    SELECT 
        r.corp_code,
        r.company_name,
        r.fiscal_year,
        'FY' AS period,
        r.fs_div,
        m.standard_account,
        r.amount,
        m.priority,
        m.mapping_status,
        ROW_NUMBER() OVER (
            PARTITION BY r.corp_code, r.fiscal_year, r.fs_div, m.standard_account
            ORDER BY m.priority ASC, r.amount DESC NULLS LAST
        ) AS rn
    FROM public.finance_raw r
    JOIN public.account_mapping_master m
      ON (
           (m.source_account_id = r.account_id_raw AND r.account_id_raw NOT LIKE '%-표준계정코드 미사용-%')
           OR
           (m.source_account_id = '-표준계정코드 미사용-' AND r.account_name_raw = m.source_account_nm)
         )
     AND r.sj_nm = m.source_sj_nm
),
best_mapping AS (
    SELECT * FROM ranked_raw WHERE rn = 1
),
pivoted AS (
    SELECT
        corp_code,
        company_name,
        fiscal_year,
        period,
        fs_div,
        
        -- 1. 영업이익
        MAX(CASE WHEN standard_account = 'operating_profit' THEN amount END) AS operating_profit,
        
        -- 2. 이자비용
        MAX(CASE WHEN standard_account = 'interest_expense' THEN amount END) AS interest_expense,
        
        -- 차입금 구성 요소
        MAX(CASE WHEN standard_account = 'short_term_debt' THEN amount END) AS st_debt,
        MAX(CASE WHEN standard_account = 'current_ltd'     THEN amount END) AS cur_ltd,
        MAX(CASE WHEN standard_account = 'long_term_debt'   THEN amount END) AS lt_debt,
        MAX(CASE WHEN standard_account = 'bonds_payable'    THEN amount END) AS bonds,
        
        -- 3. 자기자본 (자본총계)
        MAX(CASE WHEN standard_account = 'equity'           THEN amount END) AS equity,
        
        -- 매핑 상태 요약
        CASE 
            WHEN BOOL_OR(mapping_status = 'review_required') THEN 'review_required'
            ELSE 'mapped'
        END AS mapping_status
    FROM best_mapping
    GROUP BY corp_code, company_name, fiscal_year, period, fs_div
)
INSERT INTO public.finance_standard (
    corp_code, company_name, fiscal_year, period, fs_div,
    operating_profit, interest_expense, debt, short_term_debt, equity,
    mapping_status, source, collected_at
)
SELECT
    corp_code,
    company_name,
    fiscal_year,
    period,
    fs_div,
    operating_profit,
    interest_expense,
    
    -- 총차입금: 단기차입금 + 유동성장기부채 + 장기차입금 + 사채 (전부 없으면 NULL)
    CASE 
        WHEN st_debt IS NULL AND cur_ltd IS NULL AND lt_debt IS NULL AND bonds IS NULL THEN NULL
        ELSE COALESCE(st_debt, 0) + COALESCE(cur_ltd, 0) + COALESCE(lt_debt, 0) + COALESCE(bonds, 0)
    END AS debt,
    
    -- 단기차입금: 단기차입금 + 유동성장기부채 (둘 다 없으면 NULL)
    CASE 
        WHEN st_debt IS NULL AND cur_ltd IS NULL THEN NULL
        ELSE COALESCE(st_debt, 0) + COALESCE(cur_ltd, 0)
    END AS short_term_debt,
    
    equity,
    
    -- 최종 mapping_status 판정: 필수 4대 계정 중 하나라도 누락되면 review_required
    CASE 
        WHEN operating_profit IS NULL OR interest_expense IS NULL OR equity IS NULL THEN 'review_required'
        ELSE mapping_status
    END AS mapping_status,
    
    'OpenDART Standardized' AS source,
    NOW() AS collected_at
FROM pivoted
ON CONFLICT (corp_code, fiscal_year, period, fs_div)
DO UPDATE SET
    operating_profit = EXCLUDED.operating_profit,
    interest_expense = EXCLUDED.interest_expense,
    debt = EXCLUDED.debt,
    short_term_debt = EXCLUDED.short_term_debt,
    equity = EXCLUDED.equity,
    mapping_status = EXCLUDED.mapping_status,
    collected_at = NOW();
"""

print("[2] public.finance_standard 적재 SQL 실행 중...")
cur.execute(transform_sql)
inserted_count = cur.rowcount
conn.commit()
print(f"  - public.finance_standard 적재 완료 ({inserted_count}행 UPSERT)")

# ── 3. 검증 쿼리 실행 ─────────────────────────────────────────────────────────
print("\n" + "="*80)
print("[3] public.finance_standard 적재 데이터 전수 검증 (5개사 × 3개년)")
print("="*80)

query_check = """
SELECT 
    company_name,
    fiscal_year,
    period,
    ROUND(operating_profit / 1e8) AS "영업이익_억원",
    ROUND(interest_expense / 1e8) AS "이자비용_억원",
    ROUND(short_term_debt  / 1e8) AS "단기차입금_억원",
    ROUND(debt             / 1e8) AS "총차입금_억원",
    ROUND(equity           / 1e8) AS "자기자본_억원",
    mapping_status
FROM public.finance_standard
ORDER BY company_name, fiscal_year;
"""
cur.execute(query_check)
rows = cur.fetchall()
col_names = [d[0] for d in cur.description]
df_res = pd.DataFrame(rows, columns=col_names)

print(df_res.to_string(index=False))

# 품질 요약 통계
print("\n[4] 품질 점검 요약")
print(f"총 행 수: {len(df_res)}행 (예상 15행과 일치 여부: {'일치' if len(df_res) == 15 else '불일치'})")
print(f"영업이익 결측 건수: {df_res['영업이익_억원'].isna().sum()}건")
print(f"이자비용 결측 건수: {df_res['이자비용_억원'].isna().sum()}건")
print(f"총차입금 결측 건수: {df_res['총차입금_억원'].isna().sum()}건")
print(f"자기자본 결측 건수: {df_res['자기자본_억원'].isna().sum()}건")

cur.close()
conn.close()
print("\n" + "="*80)
print("[DONE] STEP 8 finance_standard 적재 완료")
print("="*80)
