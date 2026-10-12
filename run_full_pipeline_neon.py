"""
============================================================
금리 × 환율 기업여신 Screening — NeonDB 통합 파이프라인
Target DB: NeonDB (dart_ecos / PostgreSQL 18)
============================================================
단계:
1. RAW 적재:
   - public.finance_raw (DART 재무제표 원본)
   - public.ecos_rate (ECOS 기준금리 원본)
   - public.ecos_fx (ECOS 환율 원본)
   - public.fx_risk_input (환위험 공시 주석 원본)
2. CORE 가공:
   - public.account_mapping_master 검증
   - public.finance_standard 생성 (표준화 4대 재무지표)
3. MART 분석 계산 (산식 명세 기준):
   - public.mart_rate_stress (금리 스트레스 ICR 산출 및 등급 판정)
   - public.mart_fx_exposure (외환 민감도, 방향, 상대위치 산출)
4. VIEW & 정합성 검증:
   - public.v_screening (Power BI 뷰 조회 검증)
   - 산식 손계산 예시 일치 검증
============================================================
"""

import os
import glob
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "dart_ecos")
DB_USER = os.getenv("DB_USER", "neondb_owner")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require")

print(f"[1] Connecting to NeonDB ({DB_NAME} on {DB_HOST})...")
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
print("  [OK] Connection established successfully!")

# -------------------------------------------------------------
# STEP 1: RAW 데이터 적재
# -------------------------------------------------------------
print("\n" + "="*80)
print("[STEP 1] RAW Layer Data Ingestion")
print("="*80)

# 1-1. ECOS 기준금리 (public.ecos_rate)
ecos_rate_file = "data/ecos/base_rate.csv"
if os.path.exists(ecos_rate_file):
    df_rate = pd.read_csv(ecos_rate_file)
    rate_tuples = [
        (
            pd.to_datetime(r["rate_date"]).strftime("%Y-%m-%d"),
            str(r.get("rate_name", "한국은행 기준금리")),
            float(r["rate_value"]),
            "연%"
        )
        for _, r in df_rate.iterrows()
    ]
    upsert_rate_sql = """
        INSERT INTO public.ecos_rate (date, indicator, rate, unit)
        VALUES %s
        ON CONFLICT (date, indicator) DO UPDATE
        SET rate = EXCLUDED.rate, unit = EXCLUDED.unit;
    """
    execute_values(cur, upsert_rate_sql, rate_tuples, page_size=1000)
    conn.commit()
    print(f"  - public.ecos_rate: {len(rate_tuples):,} rows loaded")

# 1-2. ECOS 환율 (public.ecos_fx)
ecos_fx_file = "data/ecos/fx_rate_raw.csv"
if os.path.exists(ecos_fx_file):
    df_fx = pd.read_csv(ecos_fx_file)
    fx_tuples = [
        (
            pd.to_datetime(r["date"]).strftime("%Y-%m-%d"),
            str(r["currency"]),
            float(r["exchange_rate"]),
            str(r.get("unit", "KRW"))
        )
        for _, r in df_fx.iterrows()
    ]
    upsert_fx_sql = """
        INSERT INTO public.ecos_fx (date, currency, exchange_rate, unit)
        VALUES %s
        ON CONFLICT (date, currency) DO UPDATE
        SET exchange_rate = EXCLUDED.exchange_rate, unit = EXCLUDED.unit;
    """
    execute_values(cur, upsert_fx_sql, fx_tuples, page_size=1000)
    conn.commit()
    print(f"  - public.ecos_fx: {len(fx_tuples):,} rows loaded")

# 1-3. DART 재무제표 원본 (public.finance_raw)
dart_files = glob.glob("data/raw/dart/*/*.csv")
total_dart_rows = 0
for fpath in dart_files:
    df_d = pd.read_csv(fpath)
    records = []
    for _, r in df_d.iterrows():
        amt = None if pd.isna(r.get("thstrm_amount")) else float(r["thstrm_amount"])
        aid = None if pd.isna(r.get("account_id")) else str(r["account_id"]).strip()
        anm = None if pd.isna(r.get("account_nm")) else str(r["account_nm"]).strip()
        sj = None if pd.isna(r.get("sj_nm")) else str(r["sj_nm"]).strip()
        if not anm:
            continue
        records.append((
            str(r["corp_code"]).zfill(8),
            int(r["bsns_year"]),
            str(r["reprt_code"]),
            str(r.get("fs_div_used", "CFS")),
            sj,
            aid if aid else "-표준계정코드 미사용-",
            anm,
            amt,
            "KRW"
        ))
    if records:
        # 동일 배치 내 고유키 중복 제거 (corp_code, fiscal_year, fs_div, account_id_raw, account_name_raw)
        df_rec = pd.DataFrame(records, columns=[
            "corp_code", "fiscal_year", "report_type", "fs_div", "sj_nm",
            "account_id_raw", "account_name_raw", "amount", "unit"
        ])
        df_rec = df_rec.drop_duplicates(subset=["corp_code", "fiscal_year", "fs_div", "account_id_raw", "account_name_raw"], keep="last")
        deduped_records = [tuple(x) for x in df_rec.to_numpy()]

        upsert_dart_sql = """
            INSERT INTO public.finance_raw (
                corp_code, fiscal_year, report_type, fs_div, sj_nm,
                account_id_raw, account_name_raw, amount, unit
            ) VALUES %s
            ON CONFLICT (corp_code, fiscal_year, fs_div, account_id_raw, account_name_raw)
            DO UPDATE SET amount = EXCLUDED.amount;
        """
        execute_values(cur, upsert_dart_sql, deduped_records, page_size=1000)
        total_dart_rows += len(deduped_records)
conn.commit()
print(f"  - public.finance_raw: {total_dart_rows:,} rows loaded from {len(dart_files)} files")

# 1-4. 환위험 주석 수기 입력 (public.fx_risk_input)
fx_source_file = "data/fx_risk_input_source.csv"
if os.path.exists(fx_source_file):
    df_fxi = pd.read_csv(fx_source_file)
    fx_input_records = []
    for _, r in df_fxi.iterrows():
        up_amt = None if pd.isna(r.get("impact_up")) else float(r["impact_up"]) * 1_000_000
        down_amt = None if pd.isna(r.get("impact_down")) else float(r["impact_down"]) * 1_000_000
        shock = None if pd.isna(r.get("shock_pct")) else float(r["shock_pct"])
        target = str(r.get("impact_target", "pretax_income"))
        doc = None if pd.isna(r.get("source_doc")) else str(r["source_doc"])
        note_str = None if pd.isna(r.get("note")) else str(r["note"])
        
        fx_input_records.append((
            str(r["corp_code"]).zfill(8),
            int(r["fiscal_year"]),
            str(r["currency"]).strip(),
            str(r.get("basis", "CFS")).strip(),
            shock,
            up_amt,
            down_amt,
            target,
            doc,
            note_str
        ))
    upsert_fxi_sql = """
        INSERT INTO public.fx_risk_input (
            corp_code, fiscal_year, currency, basis, shock_pct,
            impact_up, impact_down, impact_target, source_doc, note
        ) VALUES %s
        ON CONFLICT (corp_code, fiscal_year, currency, basis)
        DO UPDATE SET
            shock_pct = EXCLUDED.shock_pct,
            impact_up = EXCLUDED.impact_up,
            impact_down = EXCLUDED.impact_down,
            impact_target = EXCLUDED.impact_target,
            source_doc = EXCLUDED.source_doc,
            note = EXCLUDED.note;
    """
    execute_values(cur, upsert_fxi_sql, fx_input_records)
    conn.commit()
    print(f"  - public.fx_risk_input: {len(fx_input_records)} rows loaded")

# 1-5. 이자율위험 주석 수기 입력 (public.rate_sensitivity_input)
rate_sens_file = "data/rate_sensitivity_input_filled.csv"
if os.path.exists(rate_sens_file):
    df_rsi = pd.read_csv(rate_sens_file)
    rsi_records = []
    for _, r in df_rsi.iterrows():
        up_amt = None if pd.isna(r.get("impact_up")) else float(r["impact_up"]) * 1_000_000
        down_amt = None if pd.isna(r.get("impact_down")) else float(r["impact_down"]) * 1_000_000
        shock_p = None if pd.isna(r.get("shock_pctp")) else float(r["shock_pctp"])
        target = str(r.get("impact_target", "interest_expense"))
        doc = None if pd.isna(r.get("source_doc")) else str(r["source_doc"])
        note_str = None if pd.isna(r.get("note")) else str(r["note"])
        
        rsi_records.append((
            str(r["corp_code"]).zfill(8),
            int(r["fiscal_year"]),
            str(r.get("basis", "CFS")).strip(),
            shock_p,
            up_amt,
            down_amt,
            target,
            doc,
            note_str
        ))
    upsert_rsi_sql = """
        INSERT INTO public.rate_sensitivity_input (
            corp_code, fiscal_year, basis, shock_pctp,
            impact_up, impact_down, impact_target, source_doc, note
        ) VALUES %s
        ON CONFLICT (corp_code, fiscal_year, basis)
        DO UPDATE SET
            shock_pctp = EXCLUDED.shock_pctp,
            impact_up = EXCLUDED.impact_up,
            impact_down = EXCLUDED.impact_down,
            impact_target = EXCLUDED.impact_target,
            source_doc = EXCLUDED.source_doc,
            note = EXCLUDED.note;
    """
    execute_values(cur, upsert_rsi_sql, rsi_records)
    conn.commit()
    print(f"  - public.rate_sensitivity_input: {len(rsi_records)} rows loaded")

# -------------------------------------------------------------
# STEP 2: CORE 데이터 변환 (public.finance_standard)
# -------------------------------------------------------------
print("\n" + "="*80)
print("[STEP 2] CORE Layer Transformation (public.finance_standard)")
print("="*80)

transform_standard_sql = """
WITH ranked_mapping AS (
    SELECT
        r.corp_code,
        r.fiscal_year,
        'FY' AS period,
        r.fs_div,
        m.standard_account,
        r.amount,
        m.priority,
        m.source_sj_nm,
        m.source_account_nm,
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
     AND r.amount IS NOT NULL
),
best_mapping AS (
    SELECT * FROM ranked_mapping WHERE rn = 1
),
pivoted AS (
    SELECT
        corp_code,
        fiscal_year,
        period,
        fs_div,
        
        -- 1. 영업이익 (operating_profit)
        MAX(CASE WHEN standard_account = 'operating_profit' THEN amount END) AS operating_profit,
        
        -- 2. 이자비용 (interest_expense) 및 출처
        MAX(CASE WHEN standard_account = 'interest_expense' THEN amount END) AS interest_expense,
        MAX(CASE WHEN standard_account = 'interest_expense' AND source_sj_nm = '현금흐름표' AND priority = 1 THEN 'paid_operating'
                 WHEN standard_account = 'interest_expense' AND source_sj_nm = '현금흐름표' AND priority = 2 THEN 'paid_financing'
                 WHEN standard_account = 'interest_expense' AND source_sj_nm IN ('손익계산서','포괄손익계산서') THEN 'finance_costs'
                 ELSE NULL END) AS interest_source,
        
        -- 3. 차입금 구성 원값
        MAX(CASE WHEN standard_account = 'short_term_borrowings' THEN amount END) AS short_term_borrowings,
        MAX(CASE WHEN standard_account = 'current_portion_ltd' THEN amount END) AS current_portion_ltd,
        MAX(CASE WHEN standard_account = 'short_term_debt_combined' THEN amount END) AS short_term_debt_combined,
        MAX(CASE WHEN standard_account = 'long_term_borrowings' THEN amount END) AS long_term_borrowings,
        MAX(CASE WHEN standard_account = 'bonds' THEN amount END) AS bonds,
        
        -- 4. 자기자본 (자본총계)
        MAX(CASE WHEN standard_account = 'equity' THEN amount END) AS equity
    FROM best_mapping
    GROUP BY corp_code, fiscal_year, period, fs_div
)
INSERT INTO public.finance_standard (
    corp_code, fiscal_year, period, fs_div,
    operating_profit, interest_expense, interest_source,
    short_term_borrowings, current_portion_ltd, long_term_borrowings, bonds,
    short_term_debt, debt, equity, mapping_status
)
SELECT
    corp_code,
    fiscal_year,
    period,
    fs_div,
    operating_profit,
    interest_expense,
    interest_source,
    short_term_borrowings,
    current_portion_ltd,
    long_term_borrowings,
    bonds,
    
    -- short_term_debt (STD): 합산 계정이 있으면 그것만, 없으면 단기차입금 + 유동성장기부채
    CASE 
        WHEN short_term_debt_combined IS NOT NULL THEN short_term_debt_combined
        WHEN short_term_borrowings IS NULL AND current_portion_ltd IS NULL THEN NULL
        ELSE COALESCE(short_term_borrowings, 0) + COALESCE(current_portion_ltd, 0)
    END AS short_term_debt,
    
    -- debt (TD): STD + 장기차입금 + 사채 (리스부채 제외)
    CASE 
        WHEN short_term_debt_combined IS NULL AND short_term_borrowings IS NULL 
             AND current_portion_ltd IS NULL AND long_term_borrowings IS NULL AND bonds IS NULL THEN NULL
        ELSE COALESCE(short_term_debt_combined, COALESCE(short_term_borrowings, 0) + COALESCE(current_portion_ltd, 0))
             + COALESCE(long_term_borrowings, 0) + COALESCE(bonds, 0)
    END AS debt,
    
    equity,
    
    CASE 
        WHEN operating_profit IS NULL OR interest_expense IS NULL OR equity IS NULL THEN 'review_required'
        ELSE 'mapped'
    END AS mapping_status
FROM pivoted
ON CONFLICT (corp_code, fiscal_year, period, fs_div) DO UPDATE
SET
    operating_profit      = EXCLUDED.operating_profit,
    interest_expense      = EXCLUDED.interest_expense,
    interest_source       = EXCLUDED.interest_source,
    short_term_borrowings = EXCLUDED.short_term_borrowings,
    current_portion_ltd   = EXCLUDED.current_portion_ltd,
    long_term_borrowings  = EXCLUDED.long_term_borrowings,
    bonds                 = EXCLUDED.bonds,
    short_term_debt       = EXCLUDED.short_term_debt,
    debt                  = EXCLUDED.debt,
    equity                = EXCLUDED.equity,
    mapping_status        = EXCLUDED.mapping_status;
"""

cur.execute(transform_standard_sql)
conn.commit()
print(f"  - public.finance_standard: {cur.rowcount} rows upserted")

# -------------------------------------------------------------
# STEP 3: MART 1 - 금리 스트레스 분석 (public.mart_rate_stress)
# 산식 명세 및 등급 판정 순서 적용
# -------------------------------------------------------------
print("\n" + "="*80)
print("[STEP 3] MART Layer 1: Stress ICR (public.mart_rate_stress)")
print("="*80)

mart_rate_stress_sql = """
WITH stress_calc AS (
    SELECT
        f.corp_code,
        f.fiscal_year,
        s.scenario_id,
        s.shock_value AS delta_r,
        
        f.operating_profit,
        f.interest_expense,
        f.short_term_debt,
        f.debt,
        
        -- 단기차입 비중
        ROUND(f.short_term_debt / NULLIF(f.debt, 0), 4) AS st_debt_ratio,
        
        -- 현재 ICR = OI / IE
        CASE WHEN f.interest_expense > 0 THEN ROUND(f.operating_profit / f.interest_expense, 4) ELSE NULL END AS icr_current,
        
        -- 추가 이자
        ROUND(f.short_term_debt * s.shock_value, 0) AS add_interest_base,
        ROUND(f.debt * s.shock_value, 0) AS add_interest_conservative,
        
        -- Stress ICR
        CASE WHEN (COALESCE(f.interest_expense, 0) + COALESCE(f.short_term_debt, 0) * s.shock_value) > 0
             THEN ROUND(f.operating_profit / (f.interest_expense + f.short_term_debt * s.shock_value), 4)
             ELSE NULL END AS icr_stress_base,
             
        CASE WHEN (COALESCE(f.interest_expense, 0) + COALESCE(f.debt, 0) * s.shock_value) > 0
             THEN ROUND(f.operating_profit / (f.interest_expense + f.debt * s.shock_value), 4)
             ELSE NULL END AS icr_stress_conservative
    FROM public.finance_standard f
    CROSS JOIN public.dim_scenario s
    WHERE s.scenario_type = 'rate'
      AND f.fs_div = 'CFS'
),
evaluated AS (
    SELECT
        c.*,
        ROUND(c.icr_current - c.icr_stress_conservative, 4) AS icr_drop,
        
        -- 1. 현재 등급 판정
        CASE
            WHEN c.operating_profit IS NULL OR c.interest_expense IS NULL OR c.debt IS NULL THEN '판정불가'
            WHEN c.operating_profit <= 0 THEN '추가검토'
            WHEN c.interest_expense = 0 AND c.debt = 0 THEN '정상'
            WHEN c.interest_expense = 0 AND c.debt > 0 THEN '판정불가'
            WHEN c.icr_current < 1.0 THEN '추가검토'
            WHEN c.icr_current < 1.5 THEN '관찰'
            ELSE '정상'
        END AS grade_current,
        
        -- 2. 시나리오 등급 판정 (보수적 Stress ICR 기준)
        CASE
            WHEN c.operating_profit IS NULL OR c.interest_expense IS NULL OR c.debt IS NULL THEN '판정불가'
            WHEN c.operating_profit <= 0 THEN '추가검토'
            WHEN c.interest_expense = 0 AND c.debt = 0 THEN '정상'
            WHEN c.interest_expense = 0 AND c.debt > 0 THEN '판정불가'
            WHEN c.icr_stress_conservative < 1.0 THEN '추가검토'
            WHEN c.icr_stress_conservative < 1.5 THEN '관찰'
            ELSE '정상'
        END AS grade_stress,
        
        -- 3. 판정 사유
        CASE
            WHEN c.operating_profit IS NULL OR c.interest_expense IS NULL OR c.debt IS NULL THEN '데이터 없음'
            WHEN c.operating_profit <= 0 THEN '영업적자'
            WHEN c.interest_expense = 0 AND c.debt = 0 THEN '무차입'
            WHEN c.interest_expense = 0 AND c.debt > 0 THEN '이자 계정 확인 필요'
            ELSE NULL
        END AS grade_reason
    FROM stress_calc c
)
INSERT INTO public.mart_rate_stress (
    corp_code, fiscal_year, scenario_id,
    operating_profit, interest_expense, short_term_debt, debt, st_debt_ratio,
    icr_current, add_interest_base, add_interest_conservative,
    icr_stress_base, icr_stress_conservative, icr_drop,
    grade_current, grade_stress, risk_shift_yn, grade_reason
)
SELECT
    corp_code,
    fiscal_year,
    scenario_id,
    operating_profit,
    interest_expense,
    short_term_debt,
    debt,
    st_debt_ratio,
    icr_current,
    add_interest_base,
    add_interest_conservative,
    icr_stress_base,
    icr_stress_conservative,
    icr_drop,
    grade_current,
    grade_stress,
    -- 위험전환: 현재 정상/관찰 → 시나리오 추가검토 시 TRUE
    CASE
        WHEN grade_current IN ('정상', '관찰') AND grade_stress = '추가검토' THEN TRUE
        ELSE FALSE
    END AS risk_shift_yn,
    grade_reason
FROM evaluated
ON CONFLICT (corp_code, fiscal_year, scenario_id) DO UPDATE SET
    operating_profit          = EXCLUDED.operating_profit,
    interest_expense          = EXCLUDED.interest_expense,
    short_term_debt           = EXCLUDED.short_term_debt,
    debt                      = EXCLUDED.debt,
    st_debt_ratio             = EXCLUDED.st_debt_ratio,
    icr_current               = EXCLUDED.icr_current,
    add_interest_base         = EXCLUDED.add_interest_base,
    add_interest_conservative = EXCLUDED.add_interest_conservative,
    icr_stress_base           = EXCLUDED.icr_stress_base,
    icr_stress_conservative   = EXCLUDED.icr_stress_conservative,
    icr_drop                  = EXCLUDED.icr_drop,
    grade_current             = EXCLUDED.grade_current,
    grade_stress              = EXCLUDED.grade_stress,
    risk_shift_yn             = EXCLUDED.risk_shift_yn,
    grade_reason              = EXCLUDED.grade_reason;
"""

cur.execute(mart_rate_stress_sql)
conn.commit()
print(f"  - public.mart_rate_stress: {cur.rowcount} rows upserted")

# -------------------------------------------------------------
# STEP 4: MART 2 - 환율 익스포저 분석 (public.mart_fx_exposure)
# -------------------------------------------------------------
print("\n" + "="*80)
print("[STEP 4] MART Layer 2: FX Exposure (public.mart_fx_exposure)")
print("="*80)

mart_fx_sql = """
WITH fx_calc AS (
    -- 1. 통화별 1%당 영향액 s_c = impact_up / shock_pct
    SELECT
        f.corp_code,
        f.fiscal_year,
        f.basis,
        f.currency,
        f.impact_up,
        f.shock_pct,
        (f.impact_up / NULLIF(f.shock_pct, 0)) AS s_c
    FROM public.fx_risk_input f
),
fx_agg AS (
    -- 2. 순영향 S_net = Σ s_c, 총노출 S_gross = Σ |s_c|
    SELECT
        corp_code,
        fiscal_year,
        basis,
        ROUND(SUM(s_c), 0) AS s_net_1pct,
        ROUND(SUM(ABS(s_c)), 0) AS s_gross_1pct
    FROM fx_calc
    GROUP BY corp_code, fiscal_year, basis
),
main_curr AS (
    -- 3. 주요 노출통화 (|s_c| 최대 통화)
    SELECT DISTINCT ON (corp_code, fiscal_year, basis)
        corp_code,
        fiscal_year,
        basis,
        currency AS main_currency
    FROM fx_calc
    ORDER BY corp_code, fiscal_year, basis, ABS(s_c) DESC NULLS LAST
),
k_val AS (
    -- 4. 최근 5년 USD 연간 최대 변동률
    SELECT MAX(ABS(yoy_change_pct)) AS k_ref_pct
    FROM public.v_year_end_fx
    WHERE currency = 'USD'
),
combined AS (
    SELECT
        a.corp_code,
        a.fiscal_year,
        a.basis,
        a.s_net_1pct,
        a.s_gross_1pct,
        m.main_currency,
        s.equity,
        
        -- FX 민감도 = |S_net| / EQ × 100
        ROUND(ABS(a.s_net_1pct) / NULLIF(s.equity, 0) * 100, 4) AS fx_sensitivity_pct,
        
        -- 방향: s_net < 0 -> 원화 약세 시 손실형, > 0 -> 원화 강세 시 손실형
        CASE
            WHEN a.s_net_1pct < 0 THEN '원화 약세 시 손실형'
            WHEN a.s_net_1pct > 0 THEN '원화 강세 시 손실형'
            ELSE '중립'
        END AS direction,
        
        -- ±10% 영향액
        ROUND(a.s_net_1pct * 10, 0) AS impact_fx_up10,
        ROUND(a.s_net_1pct * -10, 0) AS impact_fx_down10,
        ROUND(ABS(a.s_net_1pct * 10) / NULLIF(s.equity, 0) * 100, 4) AS impact_pct_equity,
        
        COALESCE(k.k_ref_pct, 14.0) AS k_ref_pct
    FROM fx_agg a
    JOIN main_curr m ON m.corp_code = a.corp_code AND m.fiscal_year = a.fiscal_year AND m.basis = a.basis
    LEFT JOIN public.finance_standard s 
           ON s.corp_code = a.corp_code AND s.fiscal_year = a.fiscal_year AND s.fs_div = a.basis
    CROSS JOIN k_val k
),
ranked_position AS (
    SELECT
        c.*,
        comp.in_sample,
        -- 부품 8개사(in_sample = TRUE) 안에서 상대위치 상·중·하 NTILE(3)
        CASE
            WHEN comp.in_sample = TRUE THEN
                CASE NTILE(3) OVER (
                    PARTITION BY c.fiscal_year, comp.in_sample
                    ORDER BY c.fx_sensitivity_pct DESC NULLS LAST
                )
                    WHEN 1 THEN '상'
                    WHEN 2 THEN '중'
                    WHEN 3 THEN '하'
                END
            ELSE NULL
        END AS relative_position
    FROM combined c
    JOIN public.dim_company comp ON comp.corp_code = c.corp_code
)
INSERT INTO public.mart_fx_exposure (
    corp_code, fiscal_year, basis,
    s_net_1pct, s_gross_1pct, main_currency, equity,
    fx_sensitivity_pct, direction, impact_fx_up10, impact_fx_down10,
    impact_pct_equity, relative_position, k_ref_pct, flags
)
SELECT
    corp_code,
    fiscal_year,
    basis,
    s_net_1pct,
    s_gross_1pct,
    main_currency,
    equity,
    fx_sensitivity_pct,
    direction,
    impact_fx_up10,
    impact_fx_down10,
    impact_pct_equity,
    relative_position,
    k_ref_pct,
    CASE 
        WHEN equity IS NULL OR equity <= 0 THEN '자본잠식/미기재로 판정 불가'
        ELSE NULL
    END AS flags
FROM ranked_position
ON CONFLICT (corp_code, fiscal_year) DO UPDATE SET
    basis              = EXCLUDED.basis,
    s_net_1pct         = EXCLUDED.s_net_1pct,
    s_gross_1pct       = EXCLUDED.s_gross_1pct,
    main_currency      = EXCLUDED.main_currency,
    equity             = EXCLUDED.equity,
    fx_sensitivity_pct = EXCLUDED.fx_sensitivity_pct,
    direction          = EXCLUDED.direction,
    impact_fx_up10     = EXCLUDED.impact_fx_up10,
    impact_fx_down10   = EXCLUDED.impact_fx_down10,
    impact_pct_equity  = EXCLUDED.impact_pct_equity,
    relative_position  = EXCLUDED.relative_position,
    k_ref_pct          = EXCLUDED.k_ref_pct,
    flags              = EXCLUDED.flags;
"""

cur.execute(mart_fx_sql)
conn.commit()
print(f"  - public.mart_fx_exposure: {cur.rowcount} rows upserted")

# -------------------------------------------------------------
# STEP 5: 검증 및 리포팅
# -------------------------------------------------------------
print("\n" + "="*80)
print("[STEP 5] Final Results & Quality Check (v_screening)")
print("="*80)

check_screening_sql = """
SELECT
    c.company_name,
    v.fiscal_year,
    v.scenario_id,
    v.grade_stress,
    v.relative_position,
    v.risk_type,
    v.priority_review_yn,
    v.priority_tier,
    v.in_sample
FROM public.v_screening v
JOIN public.dim_company c ON c.corp_code = v.corp_code
WHERE v.scenario_id = 'R2'
ORDER BY v.priority_tier ASC, v.fiscal_year DESC, c.company_name;
"""

cur.execute(check_screening_sql)
rows_screen = cur.fetchall()
col_names = [d[0] for d in cur.description]
df_screen = pd.DataFrame(rows_screen, columns=col_names)
print("\n[Screening 결과 Summary (Scenario: R2 +1.0%p 기준)]")
print(df_screen.to_string(index=False))

cur.close()
conn.close()
print("\n" + "="*80)
print("[SUCCESS] NeonDB 전체 데이터 파이프라인 및 마트 적재 완료!")
print("="*80)
