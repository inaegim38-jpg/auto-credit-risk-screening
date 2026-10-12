-- ============================================================
-- 김인애(C) 데이터 엔지니어링 전용 데이터베이스 구조 (STEP 3)
--
-- 목적:
--   외부 데이터(OpenDART, ECOS, 환위험 입력표)를 수집 및 표준화하여
--   분석 담당자(최희지 B)에게 무결한 데이터셋을 제공
--
-- 원칙:
--   1. 기존 DB 테이블(public, raw, core, mart)을 삭제하거나 변경하지 않음.
--   2. 결측값(NULL)을 0으로 변환하지 않음.
--   3. TTM 계산이나 스트레스 분석 등 분석 로직은 일절 포함하지 않음 (순수 데이터 적재/정규화).
--   4. 모든 테이블에 데이터 출처(source)와 수집일시(collected_at)를 보존.
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- ① finance_raw
-- OpenDART에서 수집한 원천 재무 데이터 (분기/연간 누적 원형 보존)
-- Grain: 기업(corp_code) × 사업연도(fiscal_year) × 보고서(report_type) × 계정
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.finance_raw (
    id                  BIGSERIAL       PRIMARY KEY,
    corp_code           CHAR(8)         NOT NULL,       -- DART 8자리 고유번호
    company_name        TEXT            NOT NULL,       -- 기업명
    fiscal_year         CHAR(4)         NOT NULL,       -- 사업연도 (예: '2023')
    report_type         VARCHAR(20)     NOT NULL,       -- 11011(사업), 11012(반기), 11013(1분기), 11014(3분기)
    account_id_raw      TEXT,                           -- DART/IFRS 원본 계정코드
    account_name_raw    TEXT            NOT NULL,       -- DART 원본 계정명
    sj_nm               TEXT,                           -- 재무제표 구분 (재무상태표, 손익계산서, 현금흐름표 등)
    fs_div              VARCHAR(5)      DEFAULT 'CFS',  -- CFS(연결), OFS(별도)
    amount              NUMERIC(25, 0),                 -- 금액 (NULL=실측 결측 보존, 0 변환 금지)
    unit                VARCHAR(10)     DEFAULT 'KRW',  -- 통화 단위
    source              TEXT            DEFAULT 'OpenDART API (fnlttSinglAcntAll)',
    collected_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finance_raw_corp_year 
    ON public.finance_raw (corp_code, fiscal_year, report_type);
CREATE INDEX IF NOT EXISTS idx_finance_raw_account 
    ON public.finance_raw (account_name_raw);

COMMENT ON TABLE  public.finance_raw IS 'OpenDART 원천 재무 데이터. 분기/연간 누적 원형 보존.';
COMMENT ON COLUMN public.finance_raw.amount IS '재무 금액 (원). 실측 결측값은 NULL로 보존.';


-- ──────────────────────────────────────────────────────────────
-- ② finance_standard
-- 계정 매핑을 거쳐 표준화된 재무 데이터 (최희지 B 분석 투입용)
-- Grain: 기업(corp_code) × 사업연도(fiscal_year) × 기간구분(period) × 재무제표(fs_div)
-- 표준 계정: 영업이익, 이자비용, 총차입금, 자기자본
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.finance_standard (
    id                  BIGSERIAL       PRIMARY KEY,
    corp_code           CHAR(8)         NOT NULL,       -- DART 기업코드
    company_name        TEXT            NOT NULL,       -- 기업명
    fiscal_year         CHAR(4)         NOT NULL,       -- 사업연도 (YYYY)
    period              VARCHAR(10)     NOT NULL DEFAULT 'FY', -- FY(연간), Q1, Q2, Q3 (TTM 계산용 원천 보장)
    fs_div              VARCHAR(5)      NOT NULL DEFAULT 'CFS',-- CFS(연결), OFS(별도)

    -- 핵심 표준 재무 지표 (단위: 원)
    operating_profit    NUMERIC(25, 0),                 -- 영업이익 (operating_profit)
    interest_expense    NUMERIC(25, 0),                 -- 이자비용 (손익계산서 우선, 없으면 현금흐름표 이자의지급)
    debt                NUMERIC(25, 0),                 -- 총차입금 (단기차입금 + 유동성장기부채 + 장기차입금 + 사채)
    short_term_debt     NUMERIC(25, 0),                 -- 단기차입금 + 유동성장기부채 (이자 영향 세부 분석용)
    equity              NUMERIC(25, 0),                 -- 자기자본 (자본총계)

    -- 품질 및 매핑 메타데이터
    mapping_status      VARCHAR(20)     NOT NULL DEFAULT 'mapped', -- mapped, unmapped, review_required
    source              TEXT            DEFAULT 'OpenDART Standardized',
    collected_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_finance_standard UNIQUE (corp_code, fiscal_year, period, fs_div)
);

CREATE INDEX IF NOT EXISTS idx_fin_std_corp_year 
    ON public.finance_standard (corp_code, fiscal_year);

COMMENT ON TABLE  public.finance_standard IS '표준화된 재무 데이터. 최희지(B) 금리·환율 분석 투입용.';
COMMENT ON COLUMN public.finance_standard.operating_profit IS '영업이익';
COMMENT ON COLUMN public.finance_standard.interest_expense IS '이자비용 (손익계산서 이자비용 -> 현금흐름표 이자의 지급 순)';
COMMENT ON COLUMN public.finance_standard.debt             IS '총차입금 (단기차입금+유동성장기부채+장기차입금+사채)';
COMMENT ON COLUMN public.finance_standard.equity           IS '자기자본 (자본총계 - 자기자본 대비 영향액 계산용)';


-- ──────────────────────────────────────────────────────────────
-- ③ fx_risk_input
-- 환위험 분석을 위한 입력 데이터
-- Grain: 기업(corp_code) × 연도(fiscal_year) × 통화(currency)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.fx_risk_input (
    id                  BIGSERIAL       PRIMARY KEY,
    corp_code           CHAR(8)         NOT NULL,       -- DART 기업코드
    company_name        TEXT            NOT NULL,       -- 기업명
    fiscal_year         CHAR(4)         NOT NULL,       -- 사업연도
    currency            VARCHAR(10)     NOT NULL,       -- 통화 코드 (USD, EUR, JPY 등)
    risk_input          NUMERIC(25, 0),                 -- 환위험 관련 입력값 (외화 순노출액 또는 공시 민감도 영향액)
    source              TEXT            DEFAULT 'DART 주석 수기 입력',
    checked_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    note                TEXT,                           -- 비고 (주석 번호, 환율 변동 가정 등)

    CONSTRAINT uq_fx_risk_input UNIQUE (corp_code, fiscal_year, currency)
);

CREATE INDEX IF NOT EXISTS idx_fx_risk_corp_year 
    ON public.fx_risk_input (corp_code, fiscal_year);

COMMENT ON TABLE  public.fx_risk_input IS '환위험 입력 데이터. 기업 × 연도 × 통화 단위 관리.';


-- ──────────────────────────────────────────────────────────────
-- ④ ecos_rate
-- ECOS 한국은행 기준금리 (일별 및 기간말 정렬 보장)
-- Grain: 날짜(date) × 지표명(indicator)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ecos_rate (
    id                  BIGSERIAL       PRIMARY KEY,
    date                DATE            NOT NULL,       -- 기준일
    indicator           VARCHAR(50)     NOT NULL DEFAULT '한국은행 기준금리',
    rate                NUMERIC(8, 4)   NOT NULL,       -- 기준금리 (연%)
    unit                VARCHAR(10)     DEFAULT '연%',
    source              TEXT            DEFAULT 'ECOS API (722Y001 / 0101000)',
    collected_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ecos_rate UNIQUE (date, indicator)
);

CREATE INDEX IF NOT EXISTS idx_ecos_rate_date 
    ON public.ecos_rate (date DESC);

COMMENT ON TABLE  public.ecos_rate IS 'ECOS 한국은행 기준금리 시계열 데이터.';


-- ──────────────────────────────────────────────────────────────
-- ⑤ ecos_fx
-- ECOS 주요 통화 환율 시계열 (원/달러 등 매매기준율)
-- Grain: 날짜(date) × 통화(currency)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.ecos_fx (
    id                  BIGSERIAL       PRIMARY KEY,
    date                DATE            NOT NULL,       -- 기준일
    currency            VARCHAR(10)     NOT NULL,       -- 통화 (USD, EUR, JPY 등)
    exchange_rate       NUMERIC(12, 4)  NOT NULL,       -- 환율 (원화 환산 매매기준율)
    unit                VARCHAR(10)     DEFAULT 'KRW',
    source              TEXT            DEFAULT 'ECOS API (731Y001)',
    collected_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_ecos_fx UNIQUE (date, currency)
);

CREATE INDEX IF NOT EXISTS idx_ecos_fx_date_curr 
    ON public.ecos_fx (date DESC, currency);

COMMENT ON TABLE  public.ecos_fx IS 'ECOS 환율 데이터 (원/달러 등 기간말 정렬용).';
