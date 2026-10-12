"""
Database Connection & Configuration Helper
PostgreSQL / Neon DB 연결 관리 모듈
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """
    환경변수(DATABASE_URL 또는 개별 호스트 정보)를 기반으로 psycopg2 연결 객체를 생성합니다.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    
    # 개별 파라미터 Fallback
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "dart_ecos"),
        user=os.getenv("DB_USER", "neondb_owner"),
        password=os.getenv("DB_PASSWORD", ""),
        sslmode=os.getenv("DB_SSLMODE", "require")
    )

def log_event(conn, event_type, status, message, row_count=0):
    """
    ingestion_event_log 테이블에 작업 이벤트를 기록합니다.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingestion_event_log (event_type, status, message, row_count, created_at)
                VALUES (%s, %s, %s, %s, NOW());
            """, (event_type, status, message, row_count))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[WARN] Failed to write event log: {e}")
