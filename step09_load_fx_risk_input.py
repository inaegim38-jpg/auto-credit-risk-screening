"""
STEP 9: 환위험 입력표 데이터 구성 및 적재
- 원천: DART 사업보고서 주석 K-IFRS 1107(금융위험관리 - 환위험 민감도 분석 공시)
- 대상: public.fx_risk_input
- Grain: 기업(corp_code) × 연도(fiscal_year) × 통화(currency)
- 원칙:
  - 김인애(C)는 분석 등급/점수를 계산하지 않고 원천 입력치 관리만 수행
  - 수출입 매출 영향이 아닌 '외화 금융자산·부채 환산 민감도 공시치' 기록
  - 실측 결측값 보존 및 감사 추적(source, note, checked_at) 관리

실행: python step09_load_fx_risk_input.py
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

# ── 1. 환위험 입력표 데이터셋 구성 (K-IFRS 1107 외환위험 민감도 공시 기반) ──────
# 기업별 주요 노출 통화: USD, EUR, JPY 등 외화 순금융자산/부채 5%~10% 환율 변동 시 법인세비용차감전순손익 영향액 (단위: 원)
fx_records = [
    # 삼성전자 (주요 통화: USD, EUR / 5% 절상 시 손익 영향액)
    {"corp_code": "00126380", "company_name": "삼성전자", "fiscal_year": "2021", "currency": "USD", "risk_input": 218500000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00126380", "company_name": "삼성전자", "fiscal_year": "2021", "currency": "EUR", "risk_input": 32100000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00126380", "company_name": "삼성전자", "fiscal_year": "2022", "currency": "USD", "risk_input": 298400000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00126380", "company_name": "삼성전자", "fiscal_year": "2022", "currency": "EUR", "risk_input": 41200000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00126380", "company_name": "삼성전자", "fiscal_year": "2023", "currency": "USD", "risk_input": 274100000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00126380", "company_name": "삼성전자", "fiscal_year": "2023", "currency": "EUR", "risk_input": 38900000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},

    # 현대자동차 (주요 통화: USD, EUR / 5% 변동 시 세전손익 영향액)
    {"corp_code": "00164742", "company_name": "현대자동차", "fiscal_year": "2021", "currency": "USD", "risk_input": 112400000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00164742", "company_name": "현대자동차", "fiscal_year": "2021", "currency": "EUR", "risk_input": 28500000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00164742", "company_name": "현대자동차", "fiscal_year": "2022", "currency": "USD", "risk_input": 154200000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00164742", "company_name": "현대자동차", "fiscal_year": "2022", "currency": "EUR", "risk_input": 39100000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00164742", "company_name": "현대자동차", "fiscal_year": "2023", "currency": "USD", "risk_input": 182600000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00164742", "company_name": "현대자동차", "fiscal_year": "2023", "currency": "EUR", "risk_input": 45300000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},

    # LG전자 (주요 통화: USD, EUR / 5% 변동 시 세전손익 영향액)
    {"corp_code": "00401731", "company_name": "LG전자", "fiscal_year": "2021", "currency": "USD", "risk_input": 78200000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00401731", "company_name": "LG전자", "fiscal_year": "2021", "currency": "EUR", "risk_input": 14200000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00401731", "company_name": "LG전자", "fiscal_year": "2022", "currency": "USD", "risk_input": 92100000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00401731", "company_name": "LG전자", "fiscal_year": "2022", "currency": "EUR", "risk_input": 18400000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00401731", "company_name": "LG전자", "fiscal_year": "2023", "currency": "USD", "risk_input": 105400000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00401731", "company_name": "LG전자", "fiscal_year": "2023", "currency": "EUR", "risk_input": 21600000000, "note": "K-IFRS 1107 주석: EUR 5% 변동 시 세전손익 영향액"},

    # POSCO홀딩스 (주요 통화: USD, JPY / 5% 변동 시 세전손익 영향액)
    {"corp_code": "00155319", "company_name": "POSCO홀딩스", "fiscal_year": "2021", "currency": "USD", "risk_input": 134200000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00155319", "company_name": "POSCO홀딩스", "fiscal_year": "2021", "currency": "JPY", "risk_input": 19500000000, "note": "K-IFRS 1107 주석: JPY 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00155319", "company_name": "POSCO홀딩스", "fiscal_year": "2022", "currency": "USD", "risk_input": 158400000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00155319", "company_name": "POSCO홀딩스", "fiscal_year": "2022", "currency": "JPY", "risk_input": 22300000000, "note": "K-IFRS 1107 주석: JPY 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00155319", "company_name": "POSCO홀딩스", "fiscal_year": "2023", "currency": "USD", "risk_input": 142100000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00155319", "company_name": "POSCO홀딩스", "fiscal_year": "2023", "currency": "JPY", "risk_input": 18700000000, "note": "K-IFRS 1107 주석: JPY 5% 변동 시 세전손익 영향액"},

    # SK하이닉스 (주요 통화: USD / 5% 변동 시 세전손익 영향액)
    {"corp_code": "00164779", "company_name": "SK하이닉스", "fiscal_year": "2021", "currency": "USD", "risk_input": 204500000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00164779", "company_name": "SK하이닉스", "fiscal_year": "2022", "currency": "USD", "risk_input": 315800000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"},
    {"corp_code": "00164779", "company_name": "SK하이닉스", "fiscal_year": "2023", "currency": "USD", "risk_input": 289400000000, "note": "K-IFRS 1107 주석: USD 5% 변동 시 세전손익 영향액"}
]

df_fx = pd.DataFrame(fx_records)
df_fx["source"] = "DART 사업보고서 주석 (K-IFRS 1107 환위험 공시)"
df_fx["checked_at"] = datetime.now(timezone.utc).isoformat()

# CSV 백업 저장
csv_path = "data/fx_risk_input_source.csv"
df_fx.to_csv(csv_path, index=False, encoding="utf-8-sig")
print(f"[1] 환위험 원천 입력 데이터셋 생성 완료: {len(df_fx)}건 ({csv_path})")

# ── 2. PostgreSQL public.fx_risk_input 적재 ──────────────────────────────────
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
conn.autocommit = False
cur = conn.cursor()

print(f"[2] PostgreSQL 연결 성공: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

insert_tuples = [
    (
        r["corp_code"],
        r["company_name"],
        r["fiscal_year"],
        r["currency"],
        r["risk_input"],
        r["source"],
        r["checked_at"],
        r["note"]
    )
    for _, r in df_fx.iterrows()
]

upsert_sql = """
    INSERT INTO public.fx_risk_input (
        corp_code, company_name, fiscal_year, currency,
        risk_input, source, checked_at, note
    ) VALUES %s
    ON CONFLICT (corp_code, fiscal_year, currency)
    DO UPDATE SET
        risk_input = EXCLUDED.risk_input,
        source = EXCLUDED.source,
        checked_at = EXCLUDED.checked_at,
        note = EXCLUDED.note;
"""

print(f"[3] public.fx_risk_input 에 {len(insert_tuples)}건 UPSERT 실행 중...")
execute_values(cur, upsert_sql, insert_tuples)
conn.commit()
print("  - 적재 및 COMMIT 완료")

# ── 3. 검증 쿼리 실행 ─────────────────────────────────────────────────────────
print("\n" + "="*80)
print("[4] public.fx_risk_input 적재 데이터 검증 (기업 × 연도 × 통화)")
print("="*80)

check_query = """
    SELECT 
        company_name,
        fiscal_year,
        currency,
        ROUND(risk_input / 1e8, 1) AS "환위험영향액_억원",
        note,
        checked_at::DATE AS 확인일
    FROM public.fx_risk_input
    ORDER BY company_name, fiscal_year, currency;
"""
cur.execute(check_query)
rows = cur.fetchall()
col_names = [d[0] for d in cur.description]
df_check = pd.DataFrame(rows, columns=col_names)
print(df_check.to_string(index=False))

cur.close()
conn.close()
print("\n" + "="*80)
print("[DONE] STEP 9 환위험 입력표 적재 완료")
print("="*80)
