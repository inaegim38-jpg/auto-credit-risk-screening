"""
STEP 7: 계정 매핑 검증 스크립트
- finance_raw 와 account_mapping_master 조인
- 5개 기업 × 3개년에 대해 4대 표준 계정 매핑 결과 산출
  1) 영업이익 (operating_profit)
  2) 이자비용 (interest_expense)
  3) 자기자본 (equity)
  4) 단기차입금 (short_term_debt) 및 총차입금 (debt)
- 매핑 상태 (mapped / review_required / unmapped) 확인

실행: python step07_verify_account_mapping.py
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

query = """
SELECT 
    m.standard_account,
    m.target_korean_name,
    r.company_name,
    r.fiscal_year,
    r.account_name_raw,
    r.account_id_raw,
    r.amount,
    m.priority,
    m.mapping_status
FROM public.finance_raw r
JOIN public.account_mapping_master m
  ON (
       (m.source_account_id = r.account_id_raw AND r.account_id_raw NOT LIKE '%-표준계정코드 미사용-%')
       OR
       (m.source_account_id = '-표준계정코드 미사용-' AND r.account_name_raw = m.source_account_nm)
     )
 AND r.sj_nm = m.source_sj_nm
ORDER BY r.company_name, r.fiscal_year, m.standard_account, m.priority;
"""

cur.execute(query)
rows = cur.fetchall()
cols = [d[0] for d in cur.description]
df = pd.DataFrame(rows, columns=cols)

print("="*80)
print("[STEP 7] 계정 매핑 마스터 적용 검증 결과")
print("="*80)
print(f"총 매칭된 계정 레코드 수: {len(df):,}건\n")

# 표준 계정별 매핑 상태 요약
print("[1] 표준 계정별 매핑 규칙 현황")
cur.execute("""
    SELECT standard_account, target_korean_name, COUNT(*) AS rule_count,
           STRING_AGG(DISTINCT mapping_status, ', ') AS statuses
    FROM public.account_mapping_master
    GROUP BY standard_account, target_korean_name
    ORDER BY standard_account;
""")
rule_summary = cur.fetchall()
df_rules = pd.DataFrame(rule_summary, columns=["표준계정", "표준명칭", "규칙수", "매핑상태"])
print(df_rules.to_string(index=False))

# 5개사 2023년 기준 매핑 샘플 출력
print("\n[2] 5개 기업 2023년 핵심 계정 매핑 금액 확인 (억원 단위)")
sample_df = df[df["fiscal_year"] == "2023"].copy()
sample_df["금액_억원"] = sample_df["amount"].apply(lambda x: round(float(x) / 1e8, 1) if pd.notna(x) else None)
piv = sample_df.pivot_table(
    index=["company_name"],
    columns=["target_korean_name"],
    values="금액_억원",
    aggfunc="first"
)
print(piv.to_string())

cur.close()
conn.close()
print("\n" + "="*80)
print("[DONE] STEP 7 계정 매핑 검증 완료")
print("="*80)
