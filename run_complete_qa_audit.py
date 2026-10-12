import os
import json
import psycopg2
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "dart_ecos"),
    user=os.getenv("DB_USER", "neondb_owner"),
    password=os.getenv("DB_PASSWORD"),
    sslmode=os.getenv("DB_SSLMODE", "require")
)
cur = conn.cursor()

results = {}

# -------------------------------------------------------------
# 1. dim_company / corp_code
# -------------------------------------------------------------
cur.execute("""
    SELECT corp_code, company_name, stock_code, industry_group, in_sample
    FROM public.dim_company
    ORDER BY company_name, corp_code;
""")
dim_companies = [
    {"corp_code": r[0], "company_name": r[1], "stock_code": r[2], "industry_group": r[3], "in_sample": r[4]}
    for r in cur.fetchall()
]
results["dim_company"] = dim_companies

# -------------------------------------------------------------
# 2. DART 재무 데이터 (finance_raw, finance_standard)
# -------------------------------------------------------------
cur.execute("""
    SELECT corp_code, fiscal_year, fs_div, COUNT(*) AS count_raw
    FROM public.finance_raw
    GROUP BY corp_code, fiscal_year, fs_div
    ORDER BY corp_code, fiscal_year, fs_div;
""")
raw_breakdown = [
    {"corp_code": r[0], "fiscal_year": r[1], "fs_div": r[2], "count": r[3]}
    for r in cur.fetchall()
]

cur.execute("""
    SELECT c.company_name, f.corp_code, f.fiscal_year, f.fs_div,
           f.operating_profit, f.interest_expense, f.interest_source,
           f.short_term_debt, f.debt, f.equity, f.mapping_status
    FROM public.finance_standard f
    JOIN public.dim_company c ON c.corp_code = f.corp_code
    ORDER BY c.company_name, f.fiscal_year, f.fs_div;
""")
standard_breakdown = [
    {
        "company_name": r[0], "corp_code": r[1], "fiscal_year": r[2], "fs_div": r[3],
        "operating_profit": str(r[4]) if r[4] is not None else None,
        "interest_expense": str(r[5]) if r[5] is not None else None,
        "interest_source": r[6],
        "short_term_debt": str(r[7]) if r[7] is not None else None,
        "debt": str(r[8]) if r[8] is not None else None,
        "equity": str(r[9]) if r[9] is not None else None,
        "mapping_status": r[10]
    }
    for r in cur.fetchall()
]

results["finance_raw_count"] = len(raw_breakdown)
results["finance_standard_count"] = len(standard_breakdown)
results["finance_standard_data"] = standard_breakdown

# -------------------------------------------------------------
# 3. ECOS 데이터 (ecos_rate, ecos_fx, v_year_end_rate, v_year_end_fx)
# -------------------------------------------------------------
cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM public.ecos_rate;")
rate_stat = cur.fetchone()
cur.execute("SELECT currency, COUNT(*), MIN(date), MAX(date) FROM public.ecos_fx GROUP BY currency;")
fx_stat = cur.fetchall()

cur.execute("SELECT fiscal_year, base_rate, rate_date FROM public.v_year_end_rate ORDER BY fiscal_year;")
v_rate_data = [{"fiscal_year": r[0], "base_rate": str(r[1]), "rate_date": str(r[2])} for r in cur.fetchall()]

cur.execute("SELECT fiscal_year, currency, year_end_fx, yoy_change_pct FROM public.v_year_end_fx ORDER BY currency, fiscal_year;")
v_fx_data = [{"fiscal_year": r[0], "currency": r[1], "year_end_fx": str(r[2]), "yoy_change_pct": str(r[3])} for r in cur.fetchall()]

results["ecos"] = {
    "rate_count": rate_stat[0], "rate_min": str(rate_stat[1]), "rate_max": str(rate_stat[2]),
    "fx_by_curr": [{"currency": r[0], "count": r[1], "min": str(r[2]), "max": str(r[3])} for r in fx_stat],
    "v_year_end_rate": v_rate_data,
    "v_year_end_fx": v_fx_data
}

# -------------------------------------------------------------
# 4. B 입력 CSV 적재 상태 (fx_risk_input, rate_sensitivity_input)
# -------------------------------------------------------------
cur.execute("SELECT COUNT(*), COUNT(DISTINCT corp_code), MIN(fiscal_year), MAX(fiscal_year) FROM public.fx_risk_input;")
fxi_stat = cur.fetchone()
cur.execute("SELECT COUNT(*), COUNT(DISTINCT corp_code), MIN(fiscal_year), MAX(fiscal_year) FROM public.rate_sensitivity_input;")
rsi_stat = cur.fetchone()

cur.execute("""
    SELECT corp_code, fiscal_year, currency, basis, COUNT(*)
    FROM public.fx_risk_input
    GROUP BY corp_code, fiscal_year, currency, basis
    HAVING COUNT(*) > 1;
""")
fxi_dups = cur.fetchall()

cur.execute("""
    SELECT corp_code, fiscal_year, basis, COUNT(*)
    FROM public.rate_sensitivity_input
    GROUP BY corp_code, fiscal_year, basis
    HAVING COUNT(*) > 1;
""")
rsi_dups = cur.fetchall()

results["b_inputs"] = {
    "fx_risk_input": {"count": fxi_stat[0], "companies": fxi_stat[1], "min_year": fxi_stat[2], "max_year": fxi_stat[3], "duplicates": len(fxi_dups)},
    "rate_sensitivity_input": {"count": rsi_stat[0], "companies": rsi_stat[1], "min_year": rsi_stat[2], "max_year": rsi_stat[3], "duplicates": len(rsi_dups)}
}

# -------------------------------------------------------------
# 5. 최종 MART 검증
# -------------------------------------------------------------
# 5-1 mart_rate_stress
cur.execute("SELECT COUNT(*), COUNT(DISTINCT corp_code), MIN(fiscal_year), MAX(fiscal_year) FROM public.mart_rate_stress;")
mrs_stat = cur.fetchone()
cur.execute("SELECT scenario_id, COUNT(*) FROM public.mart_rate_stress GROUP BY scenario_id ORDER BY scenario_id;")
mrs_scenarios = {r[0]: r[1] for r in cur.fetchall()}

cur.execute("""
    SELECT c.company_name, m.corp_code, COUNT(DISTINCT m.fiscal_year), COUNT(*)
    FROM public.mart_rate_stress m
    JOIN public.dim_company c ON c.corp_code = m.corp_code
    GROUP BY c.company_name, m.corp_code
    ORDER BY c.company_name;
""")
mrs_companies = [{"company_name": r[0], "corp_code": r[1], "years_count": r[2], "total_rows": r[3]} for r in cur.fetchall()]

cur.execute("SELECT DISTINCT grade_current FROM public.mart_rate_stress;")
grade_current_vals = [r[0] for r in cur.fetchall()]
cur.execute("SELECT DISTINCT grade_stress FROM public.mart_rate_stress;")
grade_stress_vals = [r[0] for r in cur.fetchall()]

# 5-2 mart_fx_exposure
cur.execute("SELECT COUNT(*), COUNT(DISTINCT corp_code), MIN(fiscal_year), MAX(fiscal_year) FROM public.mart_fx_exposure;")
mfe_stat = cur.fetchone()
cur.execute("""
    SELECT c.company_name, m.corp_code, COUNT(*)
    FROM public.mart_fx_exposure m
    JOIN public.dim_company c ON c.corp_code = m.corp_code
    GROUP BY c.company_name, m.corp_code
    ORDER BY c.company_name;
""")
mfe_companies = [{"company_name": r[0], "corp_code": r[1], "years_count": r[2]} for r in cur.fetchall()]

cur.execute("SELECT DISTINCT relative_position FROM public.mart_fx_exposure;")
rel_pos_vals = [r[0] for r in cur.fetchall()]

results["marts"] = {
    "mart_rate_stress": {
        "count": mrs_stat[0], "companies": mrs_stat[1], "min_year": mrs_stat[2], "max_year": mrs_stat[3],
        "scenarios": mrs_scenarios, "companies_list": mrs_companies,
        "grade_current_vals": grade_current_vals, "grade_stress_vals": grade_stress_vals
    },
    "mart_fx_exposure": {
        "count": mfe_stat[0], "companies": mfe_stat[1], "min_year": mfe_stat[2], "max_year": mfe_stat[3],
        "companies_list": mfe_companies, "relative_position_vals": rel_pos_vals
    }
}

# -------------------------------------------------------------
# 6 & 7. v_screening 검증 및 위험분류 로직
# -------------------------------------------------------------
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'v_screening'
    ORDER BY ordinal_position;
""")
v_cols = [{"column_name": r[0], "data_type": r[1]} for r in cur.fetchall()]

cur.execute("SELECT COUNT(*), COUNT(DISTINCT corp_code), MIN(fiscal_year), MAX(fiscal_year) FROM public.v_screening;")
v_stat = cur.fetchone()

cur.execute("SELECT scenario_id, COUNT(*) FROM public.v_screening GROUP BY scenario_id ORDER BY scenario_id;")
v_scenarios = {r[0]: r[1] for r in cur.fetchall()}

cur.execute("SELECT risk_type, COUNT(*) FROM public.v_screening GROUP BY risk_type;")
v_risk_type = {r[0]: r[1] for r in cur.fetchall()}

cur.execute("SELECT priority_review_yn, COUNT(*) FROM public.v_screening GROUP BY priority_review_yn;")
v_priority_review = {str(r[0]): r[1] for r in cur.fetchall()}

cur.execute("SELECT priority_tier, COUNT(*) FROM public.v_screening GROUP BY priority_tier ORDER BY priority_tier;")
v_priority_tier = {str(r[0]): r[1] for r in cur.fetchall()}

results["v_screening"] = {
    "columns": v_cols, "total_rows": v_stat[0], "companies": v_stat[1],
    "min_year": v_stat[2], "max_year": v_stat[3], "scenarios": v_scenarios,
    "risk_type_dist": v_risk_type, "priority_review_dist": v_priority_review,
    "priority_tier_dist": v_priority_tier
}

# -------------------------------------------------------------
# 8. RATE 계산 검산
# -------------------------------------------------------------
cur.execute("""
    SELECT c.company_name, m.corp_code, m.fiscal_year, m.scenario_id, s.shock_value,
           m.operating_profit, m.interest_expense, m.debt,
           m.add_interest_conservative AS db_add_int,
           m.icr_current AS db_icr_curr,
           m.icr_stress_conservative AS db_icr_stress,
           m.icr_drop AS db_icr_drop
    FROM public.mart_rate_stress m
    JOIN public.dim_company c ON c.corp_code = m.corp_code
    JOIN public.dim_scenario s ON s.scenario_id = m.scenario_id
    WHERE m.operating_profit IS NOT NULL AND m.debt IS NOT NULL
    ORDER BY c.company_name, m.fiscal_year, m.scenario_id;
""")
rate_rows = cur.fetchall()
rate_recalc_diffs = []
for r in rate_rows:
    cname, cc, yr, sc_id, shock, oi, ie, td, db_add_int, db_icr_curr, db_icr_stress, db_icr_drop = r
    shock = float(shock)
    oi = float(oi) if oi is not None else None
    ie = float(ie) if ie is not None else 0.0
    td = float(td) if td is not None else 0.0
    
    # calc
    calc_add_int = round(td * shock)
    calc_icr_curr = round(oi / ie, 4) if ie > 0 else None
    calc_icr_stress = round(oi / (ie + td * shock), 4) if (ie + td * shock) > 0 else None
    calc_icr_drop = round(calc_icr_curr - calc_icr_stress, 4) if (calc_icr_curr is not None and calc_icr_stress is not None) else None
    
    # compare
    diff_add_int = abs(float(db_add_int or 0) - calc_add_int)
    diff_icr_curr = abs(float(db_icr_curr or 0) - (calc_icr_curr or 0))
    diff_icr_stress = abs(float(db_icr_stress or 0) - (calc_icr_stress or 0))
    diff_icr_drop = abs(float(db_icr_drop or 0) - (calc_icr_drop or 0))
    
    if diff_add_int > 1 or diff_icr_curr > 0.001 or diff_icr_stress > 0.001 or diff_icr_drop > 0.001:
        rate_recalc_diffs.append({
            "company": cname, "year": yr, "scenario": sc_id,
            "db_add_int": db_add_int, "calc_add_int": calc_add_int,
            "db_icr_stress": db_icr_stress, "calc_icr_stress": calc_icr_stress
        })

results["rate_calc_mismatch_count"] = len(rate_recalc_diffs)
results["rate_calc_sample_tested"] = len(rate_rows)

# -------------------------------------------------------------
# 9. FX 계산 검산
# -------------------------------------------------------------
cur.execute("""
    SELECT c.company_name, m.corp_code, m.fiscal_year,
           m.s_net_1pct, m.equity, m.fx_sensitivity_pct,
           m.impact_fx_up10, m.impact_fx_down10, m.impact_pct_equity, m.relative_position
    FROM public.mart_fx_exposure m
    JOIN public.dim_company c ON c.corp_code = m.corp_code
    ORDER BY c.company_name, m.fiscal_year;
""")
fx_rows = cur.fetchall()
fx_recalc_diffs = []
for r in fx_rows:
    cname, cc, yr, s_net, eq, db_fx_sens, db_up10, db_down10, db_pct_eq, db_rel = r
    if eq is not None and float(eq) > 0 and s_net is not None:
        s_net = float(s_net)
        eq = float(eq)
        calc_fx_sens = round(abs(s_net) / eq * 100, 4)
        calc_up10 = round(s_net * 10)
        calc_down10 = round(s_net * -10)
        calc_pct_eq = round(abs(s_net * 10) / eq * 100, 4)
        
        diff_sens = abs(float(db_fx_sens or 0) - calc_fx_sens)
        diff_up10 = abs(float(db_up10 or 0) - calc_up10)
        diff_down10 = abs(float(db_down10 or 0) - calc_down10)
        diff_pct_eq = abs(float(db_pct_eq or 0) - calc_pct_eq)
        
        if diff_sens > 0.001 or diff_up10 > 1 or diff_down10 > 1 or diff_pct_eq > 0.001:
            fx_recalc_diffs.append({
                "company": cname, "year": yr,
                "db_fx_sens": db_fx_sens, "calc_fx_sens": calc_fx_sens,
                "db_up10": db_up10, "calc_up10": calc_up10
            })

results["fx_calc_mismatch_count"] = len(fx_recalc_diffs)
results["fx_calc_sample_tested"] = len(fx_rows)

# -------------------------------------------------------------
# 11. ingestion_event_log 검증
# -------------------------------------------------------------
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'ingestion_event_log'
    ORDER BY ordinal_position;
""")
iel_cols = [{"column_name": r[0], "data_type": r[1]} for r in cur.fetchall()]

cur.execute("SELECT id, event_type, target_entity, status, records_affected, triggered_at FROM public.ingestion_event_log ORDER BY id DESC LIMIT 10;")
iel_logs = [
    {"id": r[0], "event_type": r[1], "target_entity": r[2], "status": r[3], "records_affected": r[4], "triggered_at": str(r[5])}
    for r in cur.fetchall()
]
results["ingestion_event_log"] = {
    "columns": iel_cols,
    "recent_logs": iel_logs
}

# -------------------------------------------------------------
# 12. 읽기 전용 계정
# -------------------------------------------------------------
cur.execute("SELECT rolname, rolcanlogin, rolsuper FROM pg_roles WHERE rolname = 'analyst_readonly';")
role_info = cur.fetchall()

cur.execute("""
    SELECT table_name, privilege_type
    FROM information_schema.role_table_grants
    WHERE grantee = 'analyst_readonly' AND table_schema = 'public'
    LIMIT 20;
""")
role_grants = [{"table_name": r[0], "privilege_type": r[1]} for r in cur.fetchall()]

results["readonly_account"] = {
    "role_info": [{"rolname": r[0], "rolcanlogin": r[1], "rolsuper": r[2]} for r in role_info],
    "grants": role_grants
}

# -------------------------------------------------------------
# 13. ERD 구조 검증 (테이블, PK, FK)
# -------------------------------------------------------------
cur.execute("""
    SELECT
        tc.table_name, 
        kcu.column_name,
        tc.constraint_type
    FROM information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
      AND tc.table_schema = kcu.table_schema
    WHERE tc.table_schema = 'public' AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
    ORDER BY tc.table_name, tc.constraint_type, kcu.ordinal_position;
""")
erd_constraints = [
    {"table_name": r[0], "column_name": r[1], "constraint_type": r[2]}
    for r in cur.fetchall()
]
results["erd_constraints"] = erd_constraints

with open("qa_audit_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n[DONE] Audit script executed and saved to qa_audit_results.json")
cur.close()
conn.close()
