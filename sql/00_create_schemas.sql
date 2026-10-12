-- ============================================================
-- 금융 데이터 엔지니어링 프로젝트
-- PostgreSQL DDL: Schema 생성
-- 실행 순서: 00_create_schemas.sql → 01_raw → 02_core → 03_mart
-- ============================================================

-- 스키마 생성
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

COMMENT ON SCHEMA raw  IS 'API 원본 데이터 적재 (가공 없음)';
COMMENT ON SCHEMA core IS '정제·정규화된 표준 데이터';
COMMENT ON SCHEMA mart IS '분석용 집계 데이터마트';
