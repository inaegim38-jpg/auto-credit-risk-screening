"""
Script 03: Core Financial Standardization Runner
- RAW 데이터 -> finance_standard 표준화 가공
- 자본총계 복원, 무차입 처리, 이자비용 ABS() 적용
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.processors.finance_core import standardize_finance_data

def main():
    print("=" * 60)
    print("STEP 3: 재무 데이터 표준화 (finance_standard) 실행")
    print("=" * 60)
    
    standardize_finance_data()
    print("\n[PASS] STEP 3 재무 표준화 가공이 완료되었습니다.")

if __name__ == "__main__":
    main()
