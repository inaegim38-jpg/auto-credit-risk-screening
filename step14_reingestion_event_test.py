"""
STEP 14: 재수집 이벤트 테스트 (Re-ingestion Event Test)
- 목적:
  1) 한국은행 기준금리 변동 감지 시 자동 재수집 이벤트
  2) DART 신규 공시 접수 감지 시 대상 기업 자동 재수집 이벤트
- 이벤트 파이프라인 흐름:
  [Event Trigger (금리변동/신규공시)]
          ↓
  [타겟 재수집 (Targeted Re-ingestion)]
          ↓
  [PostgreSQL 원천 및 표준 테이블 갱신]
          ↓
  [이벤트 처리 이력 기록 (public.ingestion_event_log)]

실행: python step14_reingestion_event_test.py
"""

import os
import psycopg2
from datetime import datetime, timezone
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

print("="*80)
print("[STEP 14] 금리 변경 및 신규 공시 재수집 이벤트 테스트")
print("="*80)

# ── 1. 이벤트 추적 테이블 (ingestion_event_log) 생성 ──────────────────────────
cur.execute("""
CREATE TABLE IF NOT EXISTS public.ingestion_event_log (
    id              BIGSERIAL       PRIMARY KEY,
    event_type      VARCHAR(30)     NOT NULL, -- RATE_CHANGE, NEW_DISCLOSURE, MANUAL_TRIGGER
    target_entity   VARCHAR(50)     NOT NULL, -- BOK_BASE_RATE, CORP_00126380 등
    event_payload   TEXT,                     -- 이벤트 세부 내용 (변경 전후 값, 공시번호 등)
    status          VARCHAR(20)     NOT NULL, -- SUCCESS, FAILED, SKIPPED
    records_affected INTEGER        DEFAULT 0,
    triggered_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
""")
conn.commit()
print("[1] 이벤트 로그 테이블(public.ingestion_event_log) 준비 완료")

# ── 2. 이벤트 시나리오 1: 한국은행 기준금리 변경 감지 이벤트 ──────────────────
print("\n[2] 시나리오 1: 한국은행 기준금리 변경 감지 이벤트 시뮬레이션")
simulated_event_date = "2024-01-11"
simulated_new_rate = 3.5000  # 당시 동결 결정치 또는 신규 발표치

# DB 내 기존 데이터 확인
cur.execute("SELECT rate FROM public.ecos_rate WHERE date = %s AND indicator = '한국은행 기준금리';", (simulated_event_date,))
existing_rate = cur.fetchone()

print(f"  - 이벤트 발생: [금리변동감지] 날짜: {simulated_event_date}, 신규금리: {simulated_new_rate}%")

# 이벤트 처리: ecos_rate UPSERT
cur.execute("""
    INSERT INTO public.ecos_rate (date, indicator, rate, unit, source, collected_at)
    VALUES (%s, '한국은행 기준금리', %s, '연%%', 'ECOS Event Trigger Pipeline', NOW())
    ON CONFLICT (date, indicator)
    DO UPDATE SET rate = EXCLUDED.rate, collected_at = NOW();
""", (simulated_event_date, simulated_new_rate))
affected = cur.rowcount

# 이벤트 로그 기록
cur.execute("""
    INSERT INTO public.ingestion_event_log (event_type, target_entity, event_payload, status, records_affected, completed_at)
    VALUES ('RATE_CHANGE', 'BOK_BASE_RATE', %s, 'SUCCESS', %s, NOW());
""", (f"Date: {simulated_event_date}, Rate: {simulated_new_rate} pct", affected))
conn.commit()
print(f"  - [성공] public.ecos_rate 갱신 완료 ({affected}건) 및 이벤트 로그 기록 완료")

# ── 3. 이벤트 시나리오 2: 기업 신규 공시 접수 이벤트 ──────────────────────────
print("\n[3] 시나리오 2: 기업 신규 공시 발생 시 타겟 재수집 및 표준화 이벤트 시뮬레이션")
target_corp = "00126380"
target_name = "삼성전자"
target_year = "2023"
target_report = "11011"

print(f"  - 이벤트 발생: [신규공시접수] 기업: {target_name} ({target_corp}), 연도: {target_year}")

# 신규 공시 감지 시 finance_raw 타겟 수집/갱신 시뮬레이션 (수집일시 최신화)
cur.execute("""
    UPDATE public.finance_raw
    SET collected_at = NOW(), source = 'OpenDART Event Pipeline (Re-ingested)'
    WHERE corp_code = %s AND fiscal_year = %s AND report_type = %s;
""", (target_corp, target_year, target_report))
raw_updated = cur.rowcount

# 표준화 테이블(finance_standard) 자동 갱신 트리거 실행
cur.execute("""
    UPDATE public.finance_standard
    SET collected_at = NOW(), source = 'OpenDART Standardized (Auto-Refreshed)'
    WHERE corp_code = %s AND fiscal_year = %s;
""", (target_corp, target_year))
std_updated = cur.rowcount

# 이벤트 로그 기록
cur.execute("""
    INSERT INTO public.ingestion_event_log (event_type, target_entity, event_payload, status, records_affected, completed_at)
    VALUES ('NEW_DISCLOSURE', %s, %s, 'SUCCESS', %s, NOW());
""", (f"CORP_{target_corp}", f"Report: {target_report}, Year: {target_year}, Raw: {raw_updated}건, Std: {std_updated}건", std_updated))
conn.commit()
print(f"  - [성공] finance_raw ({raw_updated}건) 및 finance_standard ({std_updated}건) 최신화 완료")

# ── 4. 이벤트 로그 검증 ────────────────────────────────────────────────────────
print("\n" + "="*80)
print("[4] 이벤트 로그(public.ingestion_event_log) 조회 검증")
print("="*80)
cur.execute("""
    SELECT id, event_type, target_entity, event_payload, status, records_affected, triggered_at
    FROM public.ingestion_event_log
    ORDER BY id DESC
    LIMIT 5;
""")
logs = cur.fetchall()
col_names = [d[0] for d in cur.description]
df_logs = pd.DataFrame(logs, columns=col_names)
print(df_logs.to_string(index=False))

cur.close()
conn.close()
print("\n" + "="*80)
print("[DONE] STEP 14 재수집 이벤트 테스트 완료")
print("="*80)
