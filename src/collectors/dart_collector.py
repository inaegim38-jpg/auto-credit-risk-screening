"""
OpenDART API Collector Module
- corpCode.xml 고유번호 조회 및 매핑
- fnlttSinglAcntAll.json 전체 재무제표 수집 (2021~2025, CFS/OFS)
- 에스엘(00125521 -> 00148045) 특별 매핑 처리
- finance_raw 테이블 적재 및 ingestion_event_log 로깅
"""
import os
import io
import zipfile
import requests
import pandas as pd
from datetime import datetime, timezone
from psycopg2.extras import execute_values
from config.db import get_connection, log_event

BASE_DART_URL = "https://opendart.fss.or.kr/api"

# 대상 10개사 기본 정보
# 에스엘의 경우 OpenDART API 수집용 corp_code는 '00125521', 분석 표준 코드는 '00148045'
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

def download_corp_code_mapping(api_key: str) -> pd.DataFrame:
    """
    OpenDART corpCode.xml 을 다운로드하여 corp_code - stock_code 매핑 DataFrame을 반환합니다.
    """
    url = f"{BASE_DART_URL}/corpCode.xml"
    resp = requests.get(url, params={"crtfc_key": api_key}, timeout=30)
    if resp.status_code != 200:
        raise ConnectionError(f"corpCode.xml download failed with status {resp.status_code}")
    
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    xml_data = zf.read("CORPCODE.xml")
    df = pd.read_xml(io.BytesIO(xml_data), parser="lxml")
    df["stock_code"] = df["stock_code"].fillna("").astype(str).str.strip().str.zfill(6)
    df["corp_code"] = df["corp_code"].astype(str).str.strip().str.zfill(8)
    return df

def fetch_financial_statements(api_key: str, api_corp_code: str, bsns_year: str, reprt_code: str = "11011", fs_div: str = "CFS"):
    """
    OpenDART fnlttSinglAcntAll.json 호출
    """
    url = f"{BASE_DART_URL}/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": api_corp_code,
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

def collect_and_load_dart_data():
    """
    10개사 2021~2025 전 연도 재무제표 API 수집 및 finance_raw 테이블 적재 파이프라인
    """
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        raise ValueError("DART_API_KEY 환경변수가 설정되지 않았습니다.")
    
    conn = get_connection()
    cur = conn.cursor()
    print("[OpenDART] 수집 파이프라인 시작...")
    
    total_inserted = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        for comp in TARGET_COMPANIES:
            target_corp_code = comp["corp_code"]
            api_corp_code = comp["api_corp_code"]
            cname = comp["name"]
            
            for yr in YEARS:
                for fs_div in ["CFS", "OFS"]:
                    items = fetch_financial_statements(api_key, api_corp_code, yr, REPRT_CODE, fs_div)
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
                            
                        # 표준 corp_code로 적재 (에스엘의 경우 00148045)
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
                        total_inserted += len(rows)
                        print(f"  - [{cname}] {yr}년 {fs_div}: {len(rows)}건 적재 완료")
        
        conn.commit()
        log_event(conn, "DART_INGESTION", "SUCCESS", f"OpenDART {total_inserted}건 수집 및 적재 완료", total_inserted)
        print(f"[OpenDART] 성공적으로 완료되었습니다. 총 {total_inserted:,}건 적재.")
        return total_inserted
    except Exception as e:
        conn.rollback()
        log_event(conn, "DART_INGESTION", "FAIL", f"OpenDART 수집 실패: {str(e)}", 0)
        print(f"[OpenDART] 수집 오류 발생: {e}")
        raise
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    collect_and_load_dart_data()
