"""
STEP 2 완성본: OpenDART API 연결 테스트
- 삼성전자(005930) corp_code 조회 (corpCode.xml ZIP)
- 2021~2023 재무제표 조회 (연결 → 개별 fallback)
- 원본 JSON/CSV 저장
- 계정 탐색 (영업이익, 이자비용, 차입금)

실행: python step02_dart_full.py
"""

import os
import io
import json
import zipfile
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# ── 설정 ───────────────────────────────────────────────────────────────────────
load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")
if not DART_API_KEY:
    raise EnvironmentError("[ERROR] DART_API_KEY 환경변수 없음")
print(f"[OK] DART_API_KEY 로드: {DART_API_KEY[:4]}****")

BASE_DART = "https://opendart.fss.or.kr/api"
TARGET_STOCK_CODE = "005930"  # 삼성전자
YEARS = ["2021", "2022", "2023"]
REPRT_CODE = "11011"  # 사업보고서

KEYWORDS = ["영업이익", "이자", "금융원가", "금융비용", "차입", "단기차입", "장기차입", "사채", "유동성장기"]

# ── STEP 2-1: corpCode.xml 다운로드 → 삼성전자 corp_code 추출 ───────────────────
print("\n" + "="*60)
print("STEP 2-1: 기업코드 목록 다운로드")
print("="*60)

url = f"{BASE_DART}/corpCode.xml"
resp = requests.get(url, params={"crtfc_key": DART_API_KEY}, timeout=30)
print(f"HTTP Status: {resp.status_code}")
print(f"Content-Length: {len(resp.content):,} bytes")

if resp.status_code != 200:
    raise SystemExit(f"[FAIL] corpCode.xml 다운로드 실패: {resp.status_code}")

# ZIP 압축 해제
zf = zipfile.ZipFile(io.BytesIO(resp.content))
print(f"ZIP 내 파일: {zf.namelist()}")
xml_bytes = zf.read("CORPCODE.xml")
print(f"XML 크기: {len(xml_bytes):,} bytes")

# XML 파싱 (lxml 또는 etree)
df_corp = pd.read_xml(io.BytesIO(xml_bytes), parser="lxml")
print(f"전체 기업 수: {len(df_corp):,}")
print(f"컬럼: {df_corp.columns.tolist()}")

# stock_code 기준으로 삼성전자 조회
df_corp["stock_code_str"] = df_corp["stock_code"].astype(str).str.strip().str.zfill(6)
samsung = df_corp[df_corp["stock_code_str"] == TARGET_STOCK_CODE]

if samsung.empty:
    raise SystemExit(f"[FAIL] stock_code={TARGET_STOCK_CODE} 기업을 찾을 수 없음")

corp_code = str(samsung.iloc[0]["corp_code"]).zfill(8)
corp_name = samsung.iloc[0]["corp_name"]
print(f"\n[OK] 삼성전자 corp_code: {corp_code}")
print(f"[OK] 삼성전자 corp_name: {corp_name}")

# 기업코드 목록 캐시 저장
Path("data").mkdir(exist_ok=True)
corp_cache_path = Path("data/corp_code_list.csv")
df_corp.to_csv(corp_cache_path, index=False, encoding="utf-8-sig")
print(f"[OK] 기업코드 목록 저장: {corp_cache_path}")

# ── STEP 2-2: 연도별 재무제표 조회 ────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 2-2: 2021~2023 재무제표 조회")
print("="*60)

FS_URL = f"{BASE_DART}/fnlttSinglAcntAll.json"
all_dfs = {}

for year in YEARS:
    print(f"\n--- {year}년 ---")

    # 연결재무제표 우선
    for fs_div in ["CFS", "OFS"]:
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": year,
            "reprt_code": REPRT_CODE,
            "fs_div": fs_div
        }
        resp = requests.get(FS_URL, params=params, timeout=20)
        data = resp.json()
        status = data.get("status")
        message = data.get("message")
        items = data.get("list", [])

        print(f"  [{fs_div}] HTTP:{resp.status_code} | API status:{status} | msg:{message} | 행수:{len(items)}")

        if status == "000" and items:
            df = pd.DataFrame(items)
            df["corp_code"] = corp_code
            df["corp_name"] = corp_name
            df["bsns_year"] = year
            df["fs_div_used"] = fs_div
            all_dfs[year] = df

            # 원본 JSON 저장
            raw_dir = Path(f"data/raw/dart/{year}")
            raw_dir.mkdir(parents=True, exist_ok=True)
            json_path = raw_dir / f"{corp_code}_{year}_{fs_div}_raw.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"  [저장] JSON: {json_path}")

            # CSV 저장 (표준 컬럼)
            cols = [
                "corp_code","corp_name","bsns_year","reprt_code",
                "account_id","account_nm","sj_nm","fs_nm",
                "thstrm_amount","frmtrm_amount","bfefrmtrm_amount","fs_div_used"
            ]
            existing = [c for c in cols if c in df.columns]
            csv_path = raw_dir / f"{corp_code}_{year}.csv"
            df[existing].to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"  [저장] CSV: {csv_path}")
            break  # CFS 성공 시 OFS 시도 안 함
    else:
        print(f"  [WARN] {year}년 CFS/OFS 모두 실패")
        all_dfs[year] = None

# ── STEP 2-3: 컬럼 목록 확인 ──────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 2-3: 컬럼 목록 (첫 번째 성공 연도)")
print("="*60)
first_ok = next((df for df in all_dfs.values() if df is not None), None)
if first_ok is not None:
    print("컬럼:", first_ok.columns.tolist())
    print("\n샘플 (상위 3행):")
    print(first_ok.head(3).to_string(index=False))

# ── STEP 2-4: 계정 탐색 ────────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 2-4: 계정 탐색")
print("="*60)

for year, df in all_dfs.items():
    if df is None:
        continue
    print(f"\n[{year}년 계정 탐색]")
    if "account_nm" not in df.columns:
        print("  account_nm 컬럼 없음")
        continue

    mask = df["account_nm"].str.contains("|".join(KEYWORDS), na=False)
    found = df[mask][["account_nm","account_id","sj_nm","fs_nm","thstrm_amount"]].drop_duplicates("account_nm")
    if found.empty:
        print("  [NOTE] 키워드 매칭 계정 없음")
    else:
        print(found.to_string(index=False))

# ── 요약 ───────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("STEP 2 요약")
print("="*60)
print(f"기업: {corp_name} (corp_code={corp_code})")
for year, df in all_dfs.items():
    if df is not None:
        fs_div = df["fs_div_used"].iloc[0]
        print(f"  {year}: {len(df)}행 조회 성공 ({fs_div})")
    else:
        print(f"  {year}: 조회 실패")
print("="*60)
print("다음 단계: python step05_ecos_test.py")
