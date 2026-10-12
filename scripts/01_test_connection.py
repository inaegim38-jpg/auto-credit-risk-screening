"""
Script 01: Connection & Environment Test
- .env 환경변수 및 API 키 로드 검증
- PostgreSQL / Neon DB 접속 검증
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from config.db import get_connection

def main():
    print("=" * 60)
    print("STEP 1: 환경변수 및 시스템 연결 테스트")
    print("=" * 60)
    
    dart_key = os.getenv("DART_API_KEY")
    ecos_key = os.getenv("ECOS_API_KEY")
    db_url = os.getenv("DATABASE_URL")
    
    print(f"1. DART_API_KEY: {'LOADED' if dart_key else 'MISSING'}")
    print(f"2. ECOS_API_KEY: {'LOADED' if ecos_key else 'MISSING'}")
    print(f"3. DATABASE_URL: {'CONFIGURED' if db_url else 'USING HOST PARAMS'}")
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        ver = cur.fetchone()[0]
        print(f"4. DB 연결 성공: {ver}")
        cur.close()
        conn.close()
        print("\n[PASS] 모든 환경 및 연결 테스트가 성공적으로 완료되었습니다.")
    except Exception as e:
        print(f"\n[FAIL] DB 연결 오류: {e}")

if __name__ == "__main__":
    main()
