"""
STEP 2 (수정): OpenDART corp_code 조회 방법 수정
- company.json은 corp_code 필수 → stock_code로 검색 불가
- 대신 corpCode.xml (ZIP) 다운로드 방식 또는 list API 사용
"""

import os
import io
import zipfile
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")

print(f"[OK] API KEY 로드: {DART_API_KEY[:4]}****")

# DART 전체 기업코드 목록 다운로드 (ZIP)
print("\n[1] 전체 기업코드 목록 다운로드 ...")
url = "https://opendart.fss.or.kr/api/corpCode.xml"
params = {"crtfc_key": DART_API_KEY}
resp = requests.get(url, params=params, timeout=30)
print(f"  HTTP Status: {resp.status_code}")
print(f"  Content-Type: {resp.headers.get('Content-Type')}")

# ZIP 파일 처리
zf = zipfile.ZipFile(io.BytesIO(resp.content))
print(f"  ZIP 내 파일: {zf.namelist()}")

xml_data = zf.read("CORPCODE.xml").decode("utf-8")
print(f"  XML 크기: {len(xml_data):,} bytes")

# XML → DataFrame
df_corp = pd.read_xml(io.StringIO(xml_data))
print(f"  전체 기업 수: {len(df_corp):,}")
print(f"  컬럼: {df_corp.columns.tolist()}")

# 삼성전자 조회
samsung = df_corp[df_corp["stock_code"].astype(str).str.strip() == "005930"]
print(f"\n  삼성전자 조회 결과:")
print(samsung.to_string(index=False))
