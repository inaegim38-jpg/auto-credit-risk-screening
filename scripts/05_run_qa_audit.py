"""
Script 05: Data Quality Assurance & Audit Runner
- 5대 품질 규칙 및 정합성 전수 검증
- 결측치, 제약조건, 비즈니스 규칙 적합성 평가
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from src.qa.quality_audit import run_qa_audit

def main():
    print("=" * 60)
    print("STEP 5: 데이터 품질 감사 (QA Audit) 실행")
    print("=" * 60)
    
    run_qa_audit()
    print("\n[PASS] STEP 5 데이터 품질 감사가 완료되었습니다.")

if __name__ == "__main__":
    main()
