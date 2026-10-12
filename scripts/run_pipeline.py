"""
Master End-to-End Pipeline Orchestrator
기업여신 Screening 데이터 파이프라인 마스터 실행기
"""
import sys
import time
import importlib
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

def run_step(module_name: str, step_title: str):
    print("\n" + "=" * 80)
    print(f" >>> {step_title} ({module_name})")
    print("=" * 80)
    mod = importlib.import_module(f"scripts.{module_name}")
    if hasattr(mod, "main"):
        mod.main()

def run_all():
    start_time = time.time()
    print("=" * 80)
    print(" [MASTER] 자동차부품 기업여신 다중위험 Screening 통합 파이프라인 가동")
    print("=" * 80)
    
    run_step("01_test_connection", "STEP 1: 환경변수 및 시스템 연결 테스트")
    run_step("02_collect_api_data", "STEP 2: OpenDART 및 ECOS API 수집")
    run_step("03_transform_core", "STEP 3: 재무 데이터 표준화")
    run_step("04_build_marts", "STEP 4: 분석 마트 및 뷰 생성")
    run_step("05_run_qa_audit", "STEP 5: 데이터 품질 감사 (QA Audit)")
    
    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f" [COMPLETE] 전체 파이프라인이 성공적으로 완료되었습니다! (총 소요 시간: {elapsed:.2f}초)")
    print("=" * 80)

if __name__ == "__main__":
    run_all()
