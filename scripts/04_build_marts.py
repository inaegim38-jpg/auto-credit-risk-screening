"""
Script 04: Analysis Marts & Views Builder Runner
- mart_rate_stress (400행 × 23열)
- mart_fx_exposure (50행 × 37열)
- v_screening (50행 × 19열)
- CSV 산출물 data/ 폴더 자동 내보내기
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.processors.fx_processor import build_fx_marts
from src.processors.rate_stress import build_rate_and_screening_marts

def main():
    print("=" * 60)
    print("STEP 4: 분석 마트 및 뷰 생성 (Rate Stress & FX Exposure)")
    print("=" * 60)
    
    print("\n[4-1] FX Exposure 마트 빌드...")
    build_fx_marts()
    
    print("\n[4-2] Rate Stress 마트 및 v_screening 빌드...")
    build_rate_and_screening_marts()
    
    print("\n[PASS] STEP 4 분석 마트 빌드 및 CSV 내보내기가 완료되었습니다.")

if __name__ == "__main__":
    main()
