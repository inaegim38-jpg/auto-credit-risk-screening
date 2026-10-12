"""
Bank of Korea ECOS API Collector Module
- 기준금리(722Y001 / 0101000) 수집 및 ecos_rate 적재
- 대원화 환율(731Y001 / USD, EUR, JPY) 수집 및 ecos_fx 적재
- 연말 결산값 정렬 및 멱등성 보장
"""
import os
import requests
import pandas as pd
from datetime import datetime, timezone
from psycopg2.extras import execute_values
from config.db import get_connection, log_event

BASE_ECOS_URL = "https://ecos.bok.or.kr/api"

CURRENCIES = [
    {"code": "0000001", "symbol": "USD", "name": "미국 달러"},
    {"code": "0000002", "symbol": "JPY", "name": "일본 엔(100엔)"},
    {"code": "0000003", "symbol": "EUR", "name": "유로"}
]

def collect_base_rate(api_key: str, start_date: str = "20160101", end_date: str = "20251231"):
    """
    한국은행 기준금리 일별 시계열 수집
    통계표: 722Y001, 항목: 0101000
    """
    url = f"{BASE_ECOS_URL}/StatisticSearch/{api_key}/json/kr/1/5000/722Y001/D/{start_date}/{end_date}/0101000"
    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data.get("StatisticSearch", {}).get("row", [])

def collect_fx_rate(api_key: str, item_code: str, start_date: str = "20160101", end_date: str = "20251231"):
    """
    주요국 통화 대원화 환율 수집
    통계표: 731Y001
    """
    url = f"{BASE_ECOS_URL}/StatisticSearch/{api_key}/json/kr/1/5000/731Y001/D/{start_date}/{end_date}/{item_code}"
    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        return []
    data = resp.json()
    return data.get("StatisticSearch", {}).get("row", [])

def collect_and_load_ecos_data():
    """
    기준금리 및 환율 ECOS API 수집 및 적재
    """
    api_key = os.getenv("ECOS_API_KEY")
    if not api_key:
        raise ValueError("ECOS_API_KEY 환경변수가 설정되지 않았습니다.")
    
    conn = get_connection()
    cur = conn.cursor()
    print("[ECOS] 수집 파이프라인 시작...")
    now_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        # 1. 기준금리 수집
        rate_rows = collect_base_rate(api_key)
        if rate_rows:
            tuples = []
            for r in rate_rows:
                d_str = r.get("TIME")
                date_val = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
                val = float(r.get("DATA_VALUE"))
                tuples.append((date_val, "한국은행 기준금리", val, "연%", "ECOS API (722Y001/0101000)", now_iso))
            
            cur.execute("TRUNCATE TABLE ecos_rate;")
            insert_rate_sql = """
                INSERT INTO ecos_rate (rate_date, rate_name, rate_value, unit, source_doc, ingested_at)
                VALUES %s;
            """
            execute_values(cur, insert_rate_sql, tuples)
            print(f"  - [기준금리] {len(tuples):,}건 적재 완료")
            log_event(conn, "ECOS_RATE_INGESTION", "SUCCESS", f"ECOS 기준금리 {len(tuples)}건 적재", len(tuples))
        
        # 2. 환율 수집
        fx_tuples = []
        for curr in CURRENCIES:
            item_code = curr["code"]
            symbol = curr["symbol"]
            curr_name = curr["name"]
            rows = collect_fx_rate(api_key, item_code)
            
            for r in rows:
                d_str = r.get("TIME")
                date_val = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
                val = float(r.get("DATA_VALUE"))
                fx_tuples.append((date_val, symbol, curr_name, val, "원", "ECOS API (731Y001)", now_iso))
        
        if fx_tuples:
            cur.execute("TRUNCATE TABLE ecos_fx;")
            insert_fx_sql = """
                INSERT INTO ecos_fx (fx_date, currency, currency_name, fx_rate, unit, source_doc, ingested_at)
                VALUES %s;
            """
            execute_values(cur, insert_fx_sql, fx_tuples)
            print(f"  - [환율] {len(fx_tuples):,}건 적재 완료")
            log_event(conn, "ECOS_FX_INGESTION", "SUCCESS", f"ECOS 환율 {len(fx_tuples)}건 적재", len(fx_tuples))
            
        conn.commit()
        print("[ECOS] 수집 및 적재 완료.")
    except Exception as e:
        conn.rollback()
        log_event(conn, "ECOS_INGESTION", "FAIL", f"ECOS 수집 실패: {str(e)}", 0)
        print(f"[ECOS] 수집 오류: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    collect_and_load_ecos_data()
