"""
Script 02: API Data Collection Runner
- OpenDART 재무제표 API 수집 및 finance_raw 적재
- ECOS 기준금리 및 환율 API 수집 및 ecos_rate / ecos_fx 적재
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.collectors.dart_collector import collect_and_load_dart_data
from src.collectors.ecos_collector import collect_and_load_ecos_data

def main():
    print("=" * 60)
    print("STEP 2: OpenDART 및 ECOS API 수집 실행")
    print("=" * 60)
    
    print("\n[2-1] ECOS API 수집...")
    collect_and_load_ecos_data()
    
    print("\n[2-2] OpenDART API 수집...")
    collect_and_load_dart_data()
    
    print("\n[PASS] STEP 2 데이터 수집이 완료되었습니다.")

if __name__ == "__main__":
    main()
