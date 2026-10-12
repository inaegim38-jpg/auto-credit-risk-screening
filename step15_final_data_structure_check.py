"""
STEP 15: 최종 데이터 구조 종합 점검 (Final Data Structure Check)
- 점검 대상: 김인애(C) 구축 5대 핵심 테이블 및 보조 테이블
  1) public.finance_raw
  2) public.finance_standard
  3) public.fx_risk_input
  4) public.ecos_rate
  5) public.ecos_fx
  - 보조: account_mapping_master, ingestion_event_log
- 점검 항목:
  - 테이블별 Grain, 건수, PK/UK, 인덱스
  - DBeaver 확인용 조회 검증

실행: python step15_final_data_structure_check.py
"""

import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "finance_lab"),
    user=os.getenv("DB_USER", "lab_admin"),
    password=os.getenv("DB_PASSWORD", "lab_admin_2026")
)
cur = conn.cursor()

print("="*90)
print("[STEP 15] 김인애(C) 데이터 엔지니어링 최종 데이터 구조 점검 리포트")
print("="*90)

tables = [
    {"name": "finance_raw", "grain": "기업 × 연도 × 보고서 × 계정", "desc": "OpenDART 원천 재무 데이터 (분기/연간 누적 원형 보존)"},
    {"name": "finance_standard", "grain": "기업 × 연도 × 기간 × 재무제표", "desc": "표준화 재무 데이터 (최희지 B 금리·환율 분석 투입용)"},
    {"name": "fx_risk_input", "grain": "기업 × 연도 × 통화", "desc": "환위험 입력 데이터 (K-IFRS 1107 외환 민감도 공시치)"},
    {"name": "ecos_rate", "grain": "날짜 × 지표명", "desc": "ECOS 한국은행 기준금리 시계열 (기간말 정렬 보장)"},
    {"name": "ecos_fx", "grain": "날짜 × 통화", "desc": "ECOS 주요 통화 환율 시계열 (원/달러, 유로, 엔)"},
    {"name": "account_mapping_master", "grain": "표준계정 × 원본계정 조합", "desc": "DART 계정명 → 표준 계정 매핑 마스터"},
    {"name": "ingestion_event_log", "grain": "이벤트 발생 1건", "desc": "금리변동/신규공시 재수집 이벤트 감사 로그"}
]

summary_list = []

for t in tables:
    tname = t["name"]
    # 1. 행수
    cur.execute(f"SELECT COUNT(*) FROM public.{tname};")
    cnt = cur.fetchone()[0]
    
    # 2. 컬럼 수
    cur.execute(f"""
        SELECT COUNT(*) 
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = '{tname}';
    """)
    col_cnt = cur.fetchone()[0]
    
    # 3. PK / Constraints
    cur.execute(f"""
        SELECT conname, pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE n.nspname = 'public' AND conrelid = 'public.{tname}'::regclass;
    """)
    constraints = [f"{r[0]}: {r[1]}" for r in cur.fetchall()]
    
    summary_list.append({
        "테이블명": tname,
        "행수": f"{cnt:,}행",
        "컬럼수": f"{col_cnt}개",
        "Grain (기본단위)": t["grain"],
        "주요 제약조건": "; ".join(constraints) if constraints else "없음",
        "설명": t["desc"]
    })

df_summary = pd.DataFrame(summary_list)
print(df_summary[["테이블명", "행수", "컬럼수", "Grain (기본단위)", "설명"]].to_string(index=False))

print("\n" + "="*90)
print("[상세 제약조건 및 인덱스 현황]")
print("="*90)
for s in summary_list:
    print(f"\n▶ public.{s['테이블명']} ({s['행수']})")
    print(f"  - Grain: {s['Grain (기본단위)']}")
    print(f"  - 제약조건: {s['주요 제약조건']}")

cur.close()
conn.close()
print("\n" + "="*90)
print("[DONE] STEP 15 최종 데이터 구조 점검 완료")
print("="*90)
