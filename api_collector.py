"""
================================================================================
[API 수집 전용 모듈] OpenDART 재무제표 & 한국은행 ECOS 금리·환율 수집 파이프라인
프로젝트: 자동차부품 10개사 기업여신 다중위험 Screening (2021~2025 FY)
작성자: 김인애 (데이터 엔지니어링)
================================================================================
기능:
1. OpenDART API:
   - corpCode.xml 다운로드 및 고유번호-종목코드 매핑
   - 10개사 2021~2025 전 연도 연결(CFS) 및 별도(OFS) 재무제표 수집 (fnlttSinglAcntAll)
   - 에스엘(SL) 특이사항 처리: OpenDART 공시 제출 코드 '00125521' 수집 -> 표준 '00148045' 매핑
2. 한국은행 ECOS API:
   - 통계표 722Y001 (한국은행 기준금리, 2016~2025 일별) 수집
   - 통계표 731Y001 (주요국 대원화 환율: USD, EUR, JPY, 2016~2025 일별) 수집
3. DB 적재 및 로깅:
   - PostgreSQL/Neon DB 원천 테이블(finance_raw, ecos_rate, ecos_fx) 적재
   - 수집 이력 ingestion_event_log 기록
================================================================================
"""

import os
import io
import zipfile
import requests
import psycopg2
from psycopg2.extras import execute_values
import pandas as pd
from datetime import datetime, timezone
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# 1. 환경 설정 및 대상 기업 정의
# ------------------------------------------------------------------------------
load_dotenv()

DART_API_KEY = os.getenv("DART_API_KEY")
ECOS_API_KEY = os.getenv("ECOS_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

BASE_DART_URL = "https://opendart.fss.or.kr/api"
BASE_ECOS_URL = "https://ecos.bok.or.kr/api"

# 분석 대상 10개사 매핑 마스터
# 에스엘: DART API 실제 제출 법인 코드는 '00125521', 프로젝트 분석 표준 코드는 '00148045'
TARGET_COMPANIES = [
    {"corp_code": "00148045", "api_corp_code": "00125521", "stock_code": "005850", "name": "에스엘", "in_sample": True},
    {"corp_code": "01036446", "api_corp_code": "01036446", "stock_code": "200880", "name": "서연이화", "in_sample": True},
    {"corp_code": "00166315", "api_corp_code": "00166315", "stock_code": "010690", "name": "화신", "in_sample": True},
    {"corp_code": "00173078", "api_corp_code": "00173078", "stock_code": "009900", "name": "명신산업", "in_sample": True},
    {"corp_code": "00398792", "api_corp_code": "00398792", "stock_code": "064960", "name": "SNT모티브", "in_sample": True},
    {"corp_code": "01042775", "api_corp_code": "01042775", "stock_code": "204320", "name": "HL만도", "in_sample": True},
    {"corp_code": "00132992", "api_corp_code": "00132992", "stock_code": "015750", "name": "성우하이텍", "in_sample": True},
    {"corp_code": "00164788", "api_corp_code": "00164788", "stock_code": "012330", "name": "현대모비스", "in_sample": True},
    {"corp_code": "00164742", "api_corp_code": "00164742", "stock_code": "005380", "name": "현대자동차", "in_sample": False},
    {"corp_code": "00106641", "api_corp_code": "00106641", "stock_code": "000270", "name": "기아", "in_sample": False},
]

YEARS = ["2021", "2022", "2023", "2024", "2025"]
REPRT_CODE = "11011"  # 사업보고서

ECOS_CURRENCIES = [
    {"code": "0000001", "symbol": "USD", "name": "미국 달러"},
    {"code": "0000002", "symbol": "JPY", "name": "일본 엔(100엔)"},
    {"code": "0000003", "symbol": "EUR", "name": "유로"}
]

# ------------------------------------------------------------------------------
# 2. DB 연결 헬퍼 함수
# ------------------------------------------------------------------------------
def get_db_connection():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "dart_ecos"),
        user=os.getenv("DB_USER", "neondb_owner"),
        password=os.getenv("DB_PASSWORD", ""),
        sslmode=os.getenv("DB_SSLMODE", "require")
    )

def log_event(conn, event_type, status, message, row_count=0):
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion_event_log (event_type, status, message, row_count, created_at)
                VALUES (%s, %s, %s, %s, NOW());
            """, (event_type, status, message, row_count))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[WARN] 이벤트 로그 기록 실패: {e}")

# ------------------------------------------------------------------------------
# 3. OpenDART API 수집 함수
# ------------------------------------------------------------------------------
def fetch_dart_financials(corp_code: str, bsns_year: str, reprt_code: str = "11011", fs_div: str = "CFS"):
    """
    OpenDART 단일회사 전체 재무제표 API (fnlttSinglAcntAll.json) 호출
    """
    url = f"{BASE_DART_URL}/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": fs_div
    }
    resp = requests.get(url, params=params, timeout=20)
    if resp.status_code != 200:
        return []
    data = resp.json()
    if data.get("status") == "000":
        return data.get("list", [])
    return []

def run_dart_ingestion():
    """
    10개사 2021~2025 전 연도 OpenDART 재무제표 수집 및 finance_raw 적재
    """
    print("\n" + "="*70)
    print(" [1] OpenDART 재무제표 API 수집 시작")
    print("="*70)
    
    if not DART_API_KEY:
        raise ValueError("DART_API_KEY 환경변수가 설정되지 않았습니다.")
    
    conn = get_db_connection()
    cur = conn.cursor()
    total_rows = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        for comp in TARGET_COMPANIES:
            target_corp_code = comp["corp_code"]
            api_corp_code = comp["api_corp_code"]
            company_name = comp["name"]
            
            for yr in YEARS:
                for fs_div in ["CFS", "OFS"]:
                    items = fetch_dart_financials(api_corp_code, yr, REPRT_CODE, fs_div)
                    if not items:
                        continue
                    
                    rows = []
                    for item in items:
                        rno = item.get("rcept_no")
                        aid = item.get("account_id")
                        anm = item.get("account_nm")
                        amt_raw = item.get("thstrm_amount")
                        sj_nm = item.get("sj_nm")
                        sj_div = item.get("sj_div")
                        
                        try:
                            amt = float(amt_raw.replace(",", "")) if amt_raw and amt_raw.strip() not in ["-", ""] else None
                        except:
                            amt = None
                        
                        # 표준화된 corp_code (에스엘은 00148045)로 원천 적재
                        rows.append((
                            target_corp_code, int(yr), fs_div, REPRT_CODE, rno,
                            sj_div, sj_nm, aid, anm, amt, "KRW",
                            f"OpenDART fnlttSinglAcntAll (api_code={api_corp_code})",
                            now_iso
                        ))
                    
                    if rows:
                        insert_sql = """
                            INSERT INTO finance_raw (
                                corp_code, fiscal_year, fs_div, reprt_code, rcept_no,
                                sj_div, sj_nm, account_id_raw, account_nm_raw, amount, currency,
                                source_doc, ingested_at
                            ) VALUES %s;
                        """
                        execute_values(cur, insert_sql, rows)
                        total_rows += len(rows)
                        print(f"  - [{company_name}] {yr}년 {fs_div}: {len(rows)}건 수집 완료")
        
        conn.commit()
        log_event(conn, "DART_API_INGESTION", "SUCCESS", f"OpenDART {total_rows}건 수집 및 적재 완료", total_rows)
        print(f"[OpenDART] 수집 성공 완료! 총 {total_rows:,}건 finance_raw 적재")
        return total_rows
    except Exception as e:
        conn.rollback()
        log_event(conn, "DART_API_INGESTION", "FAIL", f"OpenDART 수집 실패: {str(e)}", 0)
        print(f"[OpenDART] 수집 중 오류 발생: {e}")
        raise
    finally:
        cur.close()
        conn.close()

# ------------------------------------------------------------------------------
# 4. 한국은행 ECOS API 수집 함수
# ------------------------------------------------------------------------------
def run_ecos_ingestion():
    """
    한국은행 ECOS API 기준금리(722Y001) 및 환율(731Y001) 수집 및 적재
    """
    print("\n" + "="*70)
    print(" [2] 한국은행 ECOS 기준금리 및 환율 API 수집 시작")
    print("="*70)
    
    if not ECOS_API_KEY:
        raise ValueError("ECOS_API_KEY 환경변수가 설정되지 않았습니다.")
    
    conn = get_db_connection()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        # 1. 기준금리 수집 (722Y001 / 0101000)
        print("  - [기준금리] ECOS 통계표 722Y001 수집 중...")
        url_rate = f"{BASE_ECOS_URL}/StatisticSearch/{ECOS_API_KEY}/json/kr/1/5000/722Y001/D/20160101/20251231/0101000"
        resp_rate = requests.get(url_rate, timeout=20)
        rate_rows = resp_rate.json().get("StatisticSearch", {}).get("row", []) if resp_rate.status_code == 200 else []
        
        if rate_rows:
            rate_tuples = []
            for r in rate_rows:
                d_str = r.get("TIME")
                date_val = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
                val = float(r.get("DATA_VALUE"))
                rate_tuples.append((date_val, "한국은행 기준금리", val, "연%", "ECOS API (722Y001/0101000)", now_iso))
            
            cur.execute("TRUNCATE TABLE ecos_rate;")
            execute_values(cur, """
                INSERT INTO ecos_rate (rate_date, rate_name, rate_value, unit, source_doc, ingested_at)
                VALUES %s;
            """, rate_tuples)
            print(f"  - [기준금리] {len(rate_tuples):,}건 ecos_rate 적재 완료")
            log_event(conn, "ECOS_RATE_INGESTION", "SUCCESS", f"ECOS 기준금리 {len(rate_tuples)}건 적재", len(rate_tuples))
        
        # 2. 대원화 환율 수집 (731Y001 / USD, EUR, JPY)
        print("  - [환율] ECOS 통계표 731Y001 (USD, EUR, JPY) 수집 중...")
        fx_tuples = []
        for curr in ECOS_CURRENCIES:
            item_code = curr["code"]
            symbol = curr["symbol"]
            curr_name = curr["name"]
            
            url_fx = f"{BASE_ECOS_URL}/StatisticSearch/{ECOS_API_KEY}/json/kr/1/5000/731Y001/D/20160101/20251231/{item_code}"
            resp_fx = requests.get(url_fx, timeout=20)
            fx_rows = resp_fx.json().get("StatisticSearch", {}).get("row", []) if resp_fx.status_code == 200 else []
            
            for r in fx_rows:
                d_str = r.get("TIME")
                date_val = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
                val = float(r.get("DATA_VALUE"))
                fx_tuples.append((date_val, symbol, curr_name, val, "원", "ECOS API (731Y001)", now_iso))
        
        if fx_tuples:
            cur.execute("TRUNCATE TABLE ecos_fx;")
            execute_values(cur, """
                INSERT INTO ecos_fx (fx_date, currency, currency_name, fx_rate, unit, source_doc, ingested_at)
                VALUES %s;
            """, fx_tuples)
            print(f"  - [환율] {len(fx_tuples):,}건 ecos_fx 적재 완료")
            log_event(conn, "ECOS_FX_INGESTION", "SUCCESS", f"ECOS 환율 {len(fx_tuples)}건 적재", len(fx_tuples))
        
        conn.commit()
        print("[ECOS] 기준금리 및 환율 수집 적재 성공 완료!")
    except Exception as e:
        conn.rollback()
        log_event(conn, "ECOS_API_INGESTION", "FAIL", f"ECOS 수집 실패: {str(e)}", 0)
        print(f"[ECOS] 수집 오류: {e}")
        raise
    finally:
        cur.close()
        conn.close()

# ------------------------------------------------------------------------------
# 5. 메인 실행 진입점
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    print("*" * 70)
    print(" OpenDART & ECOS 전체 API 수집 파이프라인 가동")
    print("*" * 70)
    run_dart_ingestion()
    run_ecos_ingestion()
    print("\n[COMPLETE] 모든 외부 API 수집 작업이 성공적으로 종료되었습니다.")
