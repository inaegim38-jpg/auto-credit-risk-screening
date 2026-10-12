-- ============================================================
-- CORE 레이어 DDL
-- 목적: 정제·정규화된 표준 데이터. RAW에서 계정 매핑을 거쳐 적재.
-- 원칙:
--   - 기업별 계정명 차이를 core_account_mapping으로 흡수
--   - Grain을 엄격히 정의하여 MART JOIN 오류 방지
--   - NULL은 실측 결측을 의미 (0으로 대체 금지)
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- core.company
-- Grain: 기업 1개
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.company (
    corp_code       CHAR(8)         PRIMARY KEY,    -- DART 8자리 고유번호
    corp_name       TEXT            NOT NULL,       -- 기업명 (한글)
    corp_eng_name   TEXT,                           -- 기업명 (영문)
    stock_code      CHAR(6),                        -- 주식코드 (상장사만 존재)
    is_listed       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_core_company_stock
    ON core.company (stock_code)
    WHERE stock_code IS NOT NULL;

COMMENT ON TABLE  core.company IS '기업 마스터. DART corpCode.xml 기반. Grain = 기업 1개.';
COMMENT ON COLUMN core.company.corp_code     IS 'DART 8자리 고유번호. 앞 0 포함 (예: 00126380)';
COMMENT ON COLUMN core.company.stock_code    IS '6자리 주식코드. 비상장사는 NULL.';


-- ──────────────────────────────────────────────────────────────
-- core.account_mapping
-- Grain: 원본 계정 조합 1개 (account_id + account_nm + sj_nm)
-- 목적: 기업마다 다른 원본 계정명 → 표준계정으로 변환 규칙 관리
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.account_mapping (
    id                  SERIAL          PRIMARY KEY,

    -- 원본 계정 식별 (3가지 조합으로 고유성 보장)
    source_account_id   TEXT            NOT NULL,   -- account_id (미사용 코드 포함)
    source_account_nm   TEXT            NOT NULL,   -- 원본 계정명 (한글)
    source_sj_nm        TEXT            NOT NULL,   -- 재무제표명 (재무상태표/손익계산서/현금흐름표 등)

    -- 표준계정 (매핑 대상)
    -- operating_income / interest_expense / short_term_debt /
    -- long_term_debt / bonds_payable / current_ltd / total_debt_component
    standard_account    VARCHAR(30)     NOT NULL,

    -- 매핑 우선순위 (동일 standard_account에 복수 원본이 매핑될 때)
    -- 1 = 최우선 (단독 사용), 2 = 보조 (1 없을 때 사용), 9 = 제외 검토
    priority            SMALLINT        NOT NULL DEFAULT 1
                        CHECK (priority BETWEEN 1 AND 9),

    -- 총차입금 구성 여부 (단기차입금·장기차입금·사채·유동성장기부채 합산 시 포함)
    is_total_debt_component BOOLEAN     NOT NULL DEFAULT FALSE,

    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    notes               TEXT,                       -- 판단 근거 및 주의사항
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_account_mapping UNIQUE (source_account_id, source_account_nm, source_sj_nm)
);

CREATE INDEX IF NOT EXISTS idx_acct_map_standard
    ON core.account_mapping (standard_account) WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_acct_map_account_id
    ON core.account_mapping (source_account_id) WHERE is_active = TRUE;

COMMENT ON TABLE  core.account_mapping IS '원본 DART 계정 → 표준계정 변환 규칙. 기업별 계정명 차이를 흡수.';
COMMENT ON COLUMN core.account_mapping.source_account_id IS 'DART account_id. 표준 미적용 시 "-표준계정코드 미사용-"이므로 account_nm 병용 필수.';
COMMENT ON COLUMN core.account_mapping.standard_account  IS '표준계정 코드: operating_income | interest_expense | short_term_debt | long_term_debt | bonds_payable | current_ltd | total_debt_component';
COMMENT ON COLUMN core.account_mapping.priority          IS '동일 standard_account에 복수 원본 존재 시 사용 우선순위. 1이 최우선.';
COMMENT ON COLUMN core.account_mapping.is_total_debt_component IS 'TRUE이면 total_debt 합산 대상 (단기차입금, 유동성장기부채, 사채, 장기차입금).';


-- ──────────────────────────────────────────────────────────────
-- core.financial_statement
-- Grain: 기업 1개 × 사업연도 1개 × 표준계정 1개
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.financial_statement (
    id                  BIGSERIAL       PRIMARY KEY,

    -- 기업 + 연도
    corp_code           CHAR(8)         NOT NULL
                        REFERENCES core.company (corp_code) ON UPDATE CASCADE,
    fiscal_year         SMALLINT        NOT NULL
                        CHECK (fiscal_year BETWEEN 2000 AND 2100),

    -- 표준계정
    standard_account    VARCHAR(30)     NOT NULL,   -- core.account_mapping.standard_account

    -- 정규화된 금액 (원 단위, 당기 기준)
    amount              NUMERIC(25, 0),             -- NULL = 실측 결측 (0 대체 금지)
    currency            CHAR(3)         NOT NULL DEFAULT 'KRW',

    -- 추적: 어떤 원본 계정에서 왔는가
    source_account_id   TEXT,
    source_account_nm   TEXT,
    source_sj_nm        TEXT,
    fs_div              VARCHAR(3),                 -- CFS or OFS
    mapping_rule_id     INTEGER
                        REFERENCES core.account_mapping (id),

    -- 원천 RAW 참조
    raw_dart_id         BIGINT
                        REFERENCES raw.dart_financial (id),

    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Grain 보장: 기업 × 연도 × 표준계정은 1건만 존재
    CONSTRAINT uq_fin_stmt_grain UNIQUE (corp_code, fiscal_year, standard_account)
);

CREATE INDEX IF NOT EXISTS idx_fin_stmt_corp_year
    ON core.financial_statement (corp_code, fiscal_year);

CREATE INDEX IF NOT EXISTS idx_fin_stmt_standard
    ON core.financial_statement (standard_account, fiscal_year);

COMMENT ON TABLE  core.financial_statement IS '정규화 재무제표. Grain = 기업 × 사업연도 × 표준계정. RAW에서 account_mapping을 거쳐 적재.';
COMMENT ON COLUMN core.financial_statement.amount            IS '당기 금액(원). NULL은 실측 결측. 0으로 대체하지 않음.';
COMMENT ON COLUMN core.financial_statement.standard_account  IS 'operating_income | interest_expense | short_term_debt | long_term_debt | bonds_payable | current_ltd | total_debt';
COMMENT ON COLUMN core.financial_statement.mapping_rule_id   IS '적용된 account_mapping 규칙 ID. 매핑 감사 추적용.';


-- ──────────────────────────────────────────────────────────────
-- core.annual_interest_rate
-- Grain: 연도 1개
-- 목적: ECOS 일별 데이터를 DART 연도 grain에 맞게 집계
--       → MART JOIN 시 날짜 폭발(fan-out) 방지
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS core.annual_interest_rate (
    fiscal_year         SMALLINT        PRIMARY KEY
                        CHECK (fiscal_year BETWEEN 2000 AND 2100),
    base_rate           NUMERIC(6, 4)   NOT NULL,   -- 연말 기준금리 (연%, 예: 3.5000)
    rate_date           DATE            NOT NULL,   -- 기준금리 기준일 (연말일, 예: 2023-12-31)
    aggregation_method  TEXT            NOT NULL DEFAULT 'year_end',
                        -- 'year_end' = 연말 마지막 영업일 기준
                        -- 'annual_avg' = 연간 평균 (향후 확장용)
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  core.annual_interest_rate IS '연도별 기준금리. ECOS 일별 → 연말 기준으로 집계. Grain = 연도 1개. MART JOIN 기준 테이블.';
COMMENT ON COLUMN core.annual_interest_rate.base_rate          IS '해당 연도 연말 기준금리 (연%). 소수점 4자리 저장.';
COMMENT ON COLUMN core.annual_interest_rate.aggregation_method IS '집계 방법. MVP는 year_end(연말 마지막 값) 사용.';
