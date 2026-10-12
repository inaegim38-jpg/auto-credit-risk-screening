-- ============================================================
-- 전체 DDL 실행 스크립트 (순서 보장)
-- 사용법: psql -U <user> -d <db> -f run_all_ddl.sql
--         또는 각 파일을 순서대로 실행
-- ============================================================

\echo '=== [1/6] 스키마 생성 ==='
\i 00_create_schemas.sql

\echo '=== [2/6] RAW 테이블 생성 ==='
\i 01_raw_tables.sql

\echo '=== [3/6] CORE 테이블 생성 ==='
\i 02_core_tables.sql

\echo '=== [4/6] MART 테이블 생성 ==='
\i 03_mart_tables.sql

\echo '=== [5/6] 계정 매핑 시드 데이터 적재 ==='
\i 04_seed_account_mapping.sql

\echo '=== [6/6] 연간 기준금리 시드 데이터 적재 ==='
\i 05_seed_annual_rate.sql

\echo ''
\echo '=== MART 프로시저/뷰 생성 ==='
\i 06_mart_procedure.sql

\echo ''
\echo '=============================='
\echo '모든 DDL 실행 완료'
\echo '=============================='

-- 최종 확인 쿼리
\echo ''
\echo '--- 생성된 테이블 목록 ---'
SELECT schemaname, tablename, tableowner
FROM pg_tables
WHERE schemaname IN ('raw', 'core', 'mart')
ORDER BY schemaname, tablename;

\echo ''
\echo '--- 계정 매핑 요약 ---'
SELECT standard_account, COUNT(*) AS rules
FROM core.account_mapping
GROUP BY standard_account ORDER BY standard_account;

\echo ''
\echo '--- 기준금리 데이터 ---'
SELECT fiscal_year, base_rate, rate_date
FROM core.annual_interest_rate ORDER BY fiscal_year;
