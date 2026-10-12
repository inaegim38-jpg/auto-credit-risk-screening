-- ============================================================
-- MART 레이어 DDL
-- 목적: 기준금리 상승 시나리오별 이자보상배율(ICR) 분석
-- Grain: 기업 1개 × 사업연도 1개 × 금리 상승 시나리오 1개
--
-- 계산 공식:
--   추가이자(하한) = 단기차입금 × 금리상승폭
--   추가이자(상한) = 총차입금 × 금리상승폭
--   ICR(하한) = 영업이익 / (이자비용 + 추가이자(하한))
--   ICR(상한) = 영업이익 / (이자비용 + 추가이자(상한))
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- mart.stress_analysis
-- Grain: 기업 × 사업연도 × 시나리오 (rate_scenario_pct)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mart.stress_analysis (
    id                      BIGSERIAL       PRIMARY KEY,

    -- 기업 + 연도
    corp_code               CHAR(8)         NOT NULL
                            REFERENCES core.company (corp_code) ON UPDATE CASCADE,
    corp_name               TEXT            NOT NULL,
    fiscal_year             SMALLINT        NOT NULL
                            REFERENCES core.annual_interest_rate (fiscal_year),

    -- 기준금리 (연말 기준, core.annual_interest_rate에서 JOIN)
    base_rate               NUMERIC(6, 4),          -- 실제 기준금리 (연%)
    rate_date               DATE,                   -- 기준금리 기준일

    -- 시나리오 (금리 상승폭)
    -- 예: 0.50 = +0.5%p, 1.00 = +1.0%p, 2.00 = +2.0%p
    rate_scenario_pct       NUMERIC(5, 2)   NOT NULL
                            CHECK (rate_scenario_pct > 0),
    scenario_label          TEXT            NOT NULL,   -- 예: '+0.5%p', '+1.0%p', '+2.0%p'

    -- 투입 재무지표 (core.financial_statement에서 조회, 원 단위)
    operating_income        NUMERIC(25, 0),         -- 영업이익 (NULL = 데이터 없음)
    interest_expense        NUMERIC(25, 0),         -- 이자비용 (현금흐름표 이자의 지급 우선)
    short_term_debt         NUMERIC(25, 0),         -- 단기차입금
    long_term_debt          NUMERIC(25, 0),         -- 장기차입금
    bonds_payable           NUMERIC(25, 0),         -- 사채
    current_ltd             NUMERIC(25, 0),         -- 유동성장기부채
    total_debt              NUMERIC(25, 0),         -- 총차입금 = 위 4항목 합산 (NULL 제외)

    -- 시나리오 계산 결과 (원 단위)
    -- 하한: 단기차입금 기준 (확정적으로 단기내 금리 재적용 예상)
    -- 상한: 총차입금 기준 (모든 차입금이 신금리로 재조달되는 최악 시나리오)
    additional_interest_lower   NUMERIC(25, 0),     -- 하한 추가이자 = short_term_debt × rate_scenario_pct / 100
    additional_interest_upper   NUMERIC(25, 0),     -- 상한 추가이자 = total_debt × rate_scenario_pct / 100

    -- 이자보상배율 (ICR: Interest Coverage Ratio)
    -- ICR > 2.0: 양호 / ICR 1.0~2.0: 주의 / ICR < 1.0: 위험
    icr_current             NUMERIC(12, 4),         -- 현재 ICR = 영업이익 / 이자비용
    icr_scenario_lower      NUMERIC(12, 4),         -- 시나리오 ICR(하한) = 영업이익 / (이자비용 + 하한추가이자)
    icr_scenario_upper      NUMERIC(12, 4),         -- 시나리오 ICR(상한) = 영업이익 / (이자비용 + 상한추가이자)

    -- ICR 위험 등급
    -- 'SAFE'(≥2.0) / 'WATCH'(1.0~2.0) / 'DANGER'(<1.0) / 'CRITICAL'(<0.5) / 'NULL'(계산불가)
    icr_grade_current       VARCHAR(8),
    icr_grade_lower         VARCHAR(8),
    icr_grade_upper         VARCHAR(8),

    -- 계산 메타
    has_null_input          BOOLEAN NOT NULL DEFAULT FALSE,  -- 투입값 중 NULL 존재 여부
    null_fields             TEXT[],                          -- NULL인 필드명 목록
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    refreshed_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Grain 보장: 기업 × 연도 × 시나리오는 1건만
    CONSTRAINT uq_stress_grain UNIQUE (corp_code, fiscal_year, rate_scenario_pct)
);

-- 조회 패턴 기반 인덱스
CREATE INDEX IF NOT EXISTS idx_stress_corp_year
    ON mart.stress_analysis (corp_code, fiscal_year);

CREATE INDEX IF NOT EXISTS idx_stress_year_scenario
    ON mart.stress_analysis (fiscal_year, rate_scenario_pct);

CREATE INDEX IF NOT EXISTS idx_stress_icr_grade
    ON mart.stress_analysis (icr_grade_upper, fiscal_year);  -- 위험 기업 필터링

COMMENT ON TABLE  mart.stress_analysis IS '기준금리 상승 시나리오별 이자보상배율(ICR) 분석. Grain = 기업 × 사업연도 × 금리시나리오.';
COMMENT ON COLUMN mart.stress_analysis.rate_scenario_pct     IS '금리 상승폭 (%p). 예: 0.50 = +0.5%p';
COMMENT ON COLUMN mart.stress_analysis.total_debt            IS '총차입금 = 단기차입금 + 유동성장기부채 + 사채 + 장기차입금. NULL 항목은 0으로 처리하지 않고 제외 후 합산.';
COMMENT ON COLUMN mart.stress_analysis.icr_current           IS '현재 ICR. 이자비용이 0이거나 NULL이면 NULL.';
COMMENT ON COLUMN mart.stress_analysis.icr_grade_upper       IS 'ICR 위험 등급(상한). SAFE(≥2.0) / WATCH(1.0~2.0) / DANGER(<1.0) / CRITICAL(<0.5)';
COMMENT ON COLUMN mart.stress_analysis.has_null_input        IS '투입 재무지표 중 NULL이 1개 이상 존재하면 TRUE. 분석 결과 신뢰도 판단에 사용.';
COMMENT ON COLUMN mart.stress_analysis.null_fields           IS 'NULL인 투입 필드 목록. 예: {interest_expense, short_term_debt}';
