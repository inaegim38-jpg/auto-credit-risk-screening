"""
STEP 12: 전체 데이터 품질 검증 (Data Quality Audit)
- 검증 대상 테이블 (김인애 C 담당 5대 테이블):
  1) public.finance_raw
  2) public.finance_standard
  3) public.fx_risk_input
  4) public.ecos_rate
  5) public.ecos_fx
- 검증 항목:
  - 필수 식별자 결측치 검증 (corp_code, company_name, fiscal_year, date, currency)
  - 중복 레코드 검증 (Grain 유일성)
  - 결측값 0 오염 여부 검증 (NULL -> 0 왜곡 방지)
  - 도메인 유효성 및 이상치 검증 (금리 0~10%, 환율 > 0)
  - 분석가(최희지 B) 투입 필수 계정 완전성 검증

실행: python step12_data_quality_audit.py
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
cur = conn.cursor()

print("="*80)
print("[STEP 12] 김인애(C) 데이터 엔지니어링 전체 데이터 품질 검증")
print("="*80)

audit_results = []

def run_check(test_no, target_table, check_name, query, expected_cond):
    cur.execute(query)
    val = cur.fetchone()[0]
    is_pass = expected_cond(val)
    status = "PASS" if is_pass else "FAIL"
    audit_results.append({
        "No": test_no,
        "Target Table": target_table,
        "Check Item": check_name,
        "Value": val,
        "Status": status
    })
    print(f"[{status}] #{test_no} {target_table} - {check_name}: {val}")

# ── 1. finance_raw 품질 검증 ──────────────────────────────────────────────────
run_check("R01", "finance_raw", "총 건수 확인", 
          "SELECT COUNT(*) FROM public.finance_raw;", lambda x: x == 3100)

run_check("R02", "finance_raw", "필수 식별자 결측치(corp_code, company_name, fiscal_year)", 
          "SELECT COUNT(*) FROM public.finance_raw WHERE corp_code IS NULL OR company_name IS NULL OR fiscal_year IS NULL;", lambda x: x == 0)

run_check("R03", "finance_raw", "기업코드 8자리 규격 준수", 
          "SELECT COUNT(*) FROM public.finance_raw WHERE LENGTH(corp_code) != 8;", lambda x: x == 0)

run_check("R04", "finance_raw", "계정명(account_name_raw) 누락 건수", 
          "SELECT COUNT(*) FROM public.finance_raw WHERE account_name_raw IS NULL OR TRIM(account_name_raw) = '';", lambda x: x == 0)

run_check("R05", "finance_raw", "원천 실측 결측값(NULL) 보존 건수", 
          "SELECT COUNT(*) FROM public.finance_raw WHERE amount IS NULL;", lambda x: x == 96)

# ── 2. finance_standard 품질 검증 ─────────────────────────────────────────────
run_check("S01", "finance_standard", "총 건수 확인 (5개사 × 3개년)", 
          "SELECT COUNT(*) FROM public.finance_standard;", lambda x: x == 15)

run_check("S02", "finance_standard", "Grain 중복 검증 (corp_code, fiscal_year, period, fs_div)", 
          "SELECT COUNT(*) - COUNT(DISTINCT (corp_code, fiscal_year, period, fs_div)) FROM public.finance_standard;", lambda x: x == 0)

run_check("S03", "finance_standard", "영업이익 결측 건수", 
          "SELECT COUNT(*) FROM public.finance_standard WHERE operating_profit IS NULL;", lambda x: x == 0)

run_check("S04", "finance_standard", "이자비용 결측 건수", 
          "SELECT COUNT(*) FROM public.finance_standard WHERE interest_expense IS NULL;", lambda x: x == 0)

run_check("S05", "finance_standard", "총차입금 결측 건수", 
          "SELECT COUNT(*) FROM public.finance_standard WHERE debt IS NULL;", lambda x: x == 0)

run_check("S06", "finance_standard", "자기자본(자본총계) 결측 건수", 
          "SELECT COUNT(*) FROM public.finance_standard WHERE equity IS NULL;", lambda x: x == 0)

run_check("S07", "finance_standard", "자기자본 비정상(<= 0) 건수", 
          "SELECT COUNT(*) FROM public.finance_standard WHERE equity <= 0;", lambda x: x == 0)

# ── 3. fx_risk_input 품질 검증 ────────────────────────────────────────────────
run_check("F01", "fx_risk_input", "총 건수 확인", 
          "SELECT COUNT(*) FROM public.fx_risk_input;", lambda x: x == 27)

run_check("F02", "fx_risk_input", "Grain 중복 검증 (corp_code, fiscal_year, currency)", 
          "SELECT COUNT(*) - COUNT(DISTINCT (corp_code, fiscal_year, currency)) FROM public.fx_risk_input;", lambda x: x == 0)

run_check("F03", "fx_risk_input", "환위험 입력값(risk_input) 결측 건수", 
          "SELECT COUNT(*) FROM public.fx_risk_input WHERE risk_input IS NULL;", lambda x: x == 0)

run_check("F04", "fx_risk_input", "통화코드 유효성 (USD, EUR, JPY 외 비표준)", 
          "SELECT COUNT(*) FROM public.fx_risk_input WHERE currency NOT IN ('USD', 'EUR', 'JPY');", lambda x: x == 0)

# ── 4. ecos_rate 품질 검증 ───────────────────────────────────────────────────
run_check("E01", "ecos_rate", "총 건수 확인 (2017~2023 일별)", 
          "SELECT COUNT(*) FROM public.ecos_rate;", lambda x: x == 2556)

run_check("E02", "ecos_rate", "날짜 중복 건수 (date, indicator)", 
          "SELECT COUNT(*) - COUNT(DISTINCT (date, indicator)) FROM public.ecos_rate;", lambda x: x == 0)

run_check("E03", "ecos_rate", "기준금리 범위 유효성 (0% < rate < 10%) 위반", 
          "SELECT COUNT(*) FROM public.ecos_rate WHERE rate <= 0 OR rate >= 10;", lambda x: x == 0)

# ── 5. ecos_fx 품질 검증 ──────────────────────────────────────────────────────
run_check("X01", "ecos_fx", "총 건수 확인 (2021~2023 3개 통화)", 
          "SELECT COUNT(*) FROM public.ecos_fx;", lambda x: x == 2226)

run_check("X02", "ecos_fx", "Grain 중복 건수 (date, currency)", 
          "SELECT COUNT(*) - COUNT(DISTINCT (date, currency)) FROM public.ecos_fx;", lambda x: x == 0)

run_check("X03", "ecos_fx", "환율 범위 유효성 (exchange_rate <= 0) 위반", 
          "SELECT COUNT(*) FROM public.ecos_fx WHERE exchange_rate <= 0;", lambda x: x == 0)

run_check("X04", "ecos_fx", "통화별 영업일수 균일성 검증 (불일치 통화 수)", 
          """SELECT COUNT(*) FROM (
                SELECT currency, COUNT(*) AS cnt FROM public.ecos_fx GROUP BY currency
             ) sub WHERE cnt != 742;""", lambda x: x == 0)

# ── 종합 리포트 출력 ─────────────────────────────────────────────────────────
df_audit = pd.DataFrame(audit_results)
fail_count = len(df_audit[df_audit["Status"] == "FAIL"])

print("\n" + "="*80)
print(f"품질 검증 최종 결과: 총 {len(df_audit)}개 검사 항목 중 {len(df_audit) - fail_count}개 통과 (FAIL: {fail_count}건)")
print("="*80)
print(df_audit.to_string(index=False))

cur.close()
conn.close()

if fail_count > 0:
    print("\n[WARN] 품질 검증 실패 항목이 존재합니다. 상세 내용을 검토하세요.")
else:
    print("\n[SUCCESS] 전체 20개 품질 검사 항목 100% 통과! 분석가(최희지 B)에게 무결한 데이터셋 제공 보장.")
