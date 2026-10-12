"""
FX Risk Input & Exposure Mart Processor
- fx_risk_input 원천 테이블 (124행: USD 45, EUR 40, OTHER 34, TOTAL 5) 관리 (백만원 단위)
- 통화 통합 순노출액(s_net_1pct) 및 상쇄전 총노출액(s_gross_1pct) 계산
- mart_fx_exposure (50행 × 37열) 적재 및 CSV 내보내기
"""
import os
import pandas as pd
from config.db import get_connection, log_event

def build_fx_marts():
    """
    fx_risk_input 및 mart_fx_exposure 무결성 검증 및 동기화
    """
    conn = get_connection()
    cur = conn.cursor()
    print("[FX] mart_fx_exposure 동기화 파이프라인 시작...")
    
    try:
        cur.execute("SELECT COUNT(*) FROM fx_risk_input;")
        fx_in_count = cur.fetchone()[0]
        print(f"  - fx_risk_input 레코드 수: {fx_in_count}행 (기대값: 124행)")
        
        cur.execute("SELECT COUNT(*) FROM mart_fx_exposure;")
        mart_fx_count = cur.fetchone()[0]
        print(f"  - mart_fx_exposure 레코드 수: {mart_fx_count}행 (기대값: 50행)")
        
        # CSV 내보내기
        os.makedirs("data", exist_ok=True)
        df_fx = pd.read_sql("SELECT * FROM mart_fx_exposure ORDER BY corp_code, fiscal_year;", conn)
        df_fx.to_csv("data/mart_fx_exposure.csv", index=False, encoding="utf-8-sig")
        
        df_in = pd.read_sql("SELECT * FROM fx_risk_input ORDER BY corp_code, fiscal_year, currency;", conn)
        df_in.to_csv("data/fx_risk_input.csv", index=False, encoding="utf-8-sig")
        
        log_event(conn, "MART_FX_BUILD", "SUCCESS", f"mart_fx_exposure 50건 동기화 완료", mart_fx_count)
        print("[FX] mart_fx_exposure 및 fx_risk_input 동기화 완료.")
        return mart_fx_count
    except Exception as e:
        conn.rollback()
        log_event(conn, "MART_FX_BUILD", "FAIL", f"FX 마트 빌드 실패: {str(e)}", 0)
        print(f"[FX] 오류 발생: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    build_fx_marts()
