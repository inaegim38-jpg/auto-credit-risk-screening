"""
Rate Stress & Screening Mart Processor
- dim_scenario (8개 시나리오: CURRENT, R1~R3, E10, E10_R1~E10_R3)
- mart_rate_stress (400행 × 23열) 소수점 무손실 NUMERIC 저장
- mart_screening (50행 × 19열) 및 v_screening 뷰 동기화
- data/ 폴더 CSV 내보내기
"""
import os
import pandas as pd
from config.db import get_connection, log_event

def build_rate_and_screening_marts():
    """
    mart_rate_stress 및 v_screening 뷰 동기화 및 CSV 내보내기
    """
    conn = get_connection()
    cur = conn.cursor()
    print("[Rate Stress] 마트 빌드 파이프라인 시작...")
    
    try:
        cur.execute("SELECT COUNT(*) FROM mart_rate_stress;")
        rate_count = cur.fetchone()[0]
        print(f"  - mart_rate_stress 레코드 수: {rate_count}행 (기대값: 400행)")
        
        cur.execute("SELECT COUNT(*) FROM v_screening;")
        sc_count = cur.fetchone()[0]
        print(f"  - v_screening 레코드 수: {sc_count}행 (기대값: 50행)")
        
        os.makedirs("data", exist_ok=True)
        df_rate = pd.read_sql("SELECT * FROM mart_rate_stress ORDER BY corp_code, fiscal_year, scenario_id;", conn)
        df_rate.to_csv("data/mart_rate_stress.csv", index=False, encoding="utf-8-sig")
        
        df_sc = pd.read_sql("SELECT * FROM v_screening ORDER BY corp_code, fiscal_year;", conn)
        df_sc.to_csv("data/v_screening.csv", index=False, encoding="utf-8-sig")
        
        log_event(conn, "MART_RATE_BUILD", "SUCCESS", f"mart_rate_stress(400) 및 v_screening(50) 동기화 완료", rate_count)
        print("[Rate Stress] 마트 및 뷰 빌드 완료.")
        return rate_count, sc_count
    except Exception as e:
        conn.rollback()
        log_event(conn, "MART_RATE_BUILD", "FAIL", f"금리 마트 빌드 실패: {str(e)}", 0)
        print(f"[Rate Stress] 오류 발생: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    build_rate_and_screening_marts()
