-- ============================================================
-- 금리 × 환율 기업여신 Screening — ERD v5 완전 DDL 스크립트
-- Target DB: PostgreSQL (NeonDB / dart_ecos)
-- ============================================================

-- -----------------------------------------------------------
-- 1. [CORE] dim_company (기업 마스터)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.dim_company (
    corp_code       CHAR(8)      NOT NULL PRIMARY KEY,   -- DART 8자리 기업코드
    company_name    TEXT         NOT NULL,               -- 기업명 (한글)
    stock_code      CHAR(6),                             -- 종목코드 6자리
    industry_group  VARCHAR(20)  NOT NULL DEFAULT '자동차부품', -- 업종 그룹
    in_sample       BOOLEAN      NOT NULL DEFAULT TRUE   -- TRUE=부품 8개사(분석 표본), FALSE=완성차 2개사(참고용)
);

COMMENT ON TABLE  public.dim_company IS '기업 마스터: 자동차부품 표본 8개사 + 완성차 참고 2개사';
COMMENT ON COLUMN public.dim_company.corp_code      IS 'DART 기업고유번호 8자리 (앞 0 포함)';
COMMENT ON COLUMN public.dim_company.company_name   IS '기업명 (한글)';
COMMENT ON COLUMN public.dim_company.stock_code     IS '상장 종목코드 6자리';
COMMENT ON COLUMN public.dim_company.industry_group IS '업종 그룹: 자동차부품 / 완성차';
COMMENT ON COLUMN public.dim_company.in_sample      IS 'TRUE=분석 표본, FALSE=참고용(완성차)';

-- 10개 기업 초기 데이터 등록
INSERT INTO public.dim_company (corp_code, company_name, stock_code, industry_group, in_sample)
VALUES
    ('00561866', '에스엘',      '115390', '자동차부품', TRUE),
    ('01036446', '서연이화',    '200880', '자동차부품', TRUE),
    ('00166315', '화신',        '010690', '자동차부품', TRUE),
    ('00173078', '명신산업',    '009900', '자동차부품', TRUE),
    ('00398792', 'SNT모티브',   '064960', '자동차부품', TRUE),
    ('01042775', 'HL만도',      '204320', '자동차부품', TRUE),
    ('00132992', '성우하이텍',  '015750', '자동차부품', TRUE),
    ('00164788', '현대모비스',  '012330', '자동차부품', TRUE),
    ('00164742', '현대자동차',  '005380', '완성차',     FALSE),
    ('00106641', '기아',        '000270', '완성차',     FALSE),
    -- 기존 5개사 호환용 추가
    ('00126380', '삼성전자',    '005930', '기타',       FALSE),
    ('00164779', 'SK하이닉스',  '000660', '기타',       FALSE),
    ('00401731', 'LG전자',      '066570', '기타',       FALSE),
    ('00155319', 'POSCO홀딩스', '005490', '기타',       FALSE)
ON CONFLICT (corp_code) DO UPDATE
    SET company_name   = EXCLUDED.company_name,
        stock_code     = EXCLUDED.stock_code,
        industry_group = EXCLUDED.industry_group,
        in_sample      = EXCLUDED.in_sample;

-- -----------------------------------------------------------
-- 2. [RAW] finance_raw (OpenDART 원천 재무제표)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.finance_raw (
    id                  BIGSERIAL       PRIMARY KEY,
    corp_code           CHAR(8)         NOT NULL REFERENCES public.dim_company(corp_code),
    fiscal_year         SMALLINT        NOT NULL,
    report_type         VARCHAR(10)     NOT NULL,       -- 11011(사업보고서)
    fs_div              VARCHAR(5)      NOT NULL,       -- CFS(연결), OFS(별도)
    sj_nm               TEXT,                           -- 재무상태표, 손익계산서, 현금흐름표 등
    account_id_raw      TEXT,                           -- DART 표준 계정코드
    account_name_raw    TEXT,                           -- 원본 계정명
    amount              NUMERIC(25, 0),                 -- 금액 (원 단위, 결측 NULL)
    unit                VARCHAR(10)     DEFAULT 'KRW',
    collected_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_finance_raw UNIQUE (corp_code, fiscal_year, fs_div, account_id_raw, account_name_raw)
);

CREATE INDEX IF NOT EXISTS idx_finance_raw_corp_year ON public.finance_raw (corp_code, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_finance_raw_account ON public.finance_raw (account_name_raw);

-- -----------------------------------------------------------
-- 3. [RAW] fx_risk_input (환위험 주석 수기 입력)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.fx_risk_input (
    id              BIGSERIAL       PRIMARY KEY,
    corp_code       CHAR(8)         NOT NULL REFERENCES public.dim_company(corp_code),
    fiscal_year     SMALLINT        NOT NULL,
    currency        VARCHAR(10)     NOT NULL,           -- USD, EUR, JPY, TOTAL, OTHER
    basis           VARCHAR(5)      NOT NULL,           -- CFS / OFS
    shock_pct       NUMERIC,                            -- 공시 충격률 (5, 10 등)
    impact_up       NUMERIC(25, 0),                     -- 외화 상승 시 영향액 (원)
    impact_down     NUMERIC(25, 0),                     -- 외화 하락 시 영향액 (원)
    impact_target   VARCHAR(20)     DEFAULT 'pretax_income', -- pretax_income / equity
    source_doc      TEXT,                               -- 보고서명, 주석번호, 쪽수
    note            TEXT,
    checked_at      TIMESTAMPTZ     DEFAULT NOW(),
    CONSTRAINT uq_fx_risk_input UNIQUE (corp_code, fiscal_year, currency, basis),
    CONSTRAINT ck_fx_risk_basis CHECK (basis IN ('CFS', 'OFS'))
);

-- -----------------------------------------------------------
-- 4. [RAW] rate_sensitivity_input (이자율위험 주석 수기 입력, 검증용)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rate_sensitivity_input (
    id              BIGSERIAL       PRIMARY KEY,
    corp_code       CHAR(8)         NOT NULL REFERENCES public.dim_company(corp_code),
    fiscal_year     SMALLINT        NOT NULL,
    basis           VARCHAR(5)      NOT NULL,           -- CFS / OFS
    shock_pctp      NUMERIC,                            -- 공시 금리 변동폭 %p (100bp = 1)
    impact_up       NUMERIC(25, 0),                     -- 금리 상승 시 이자비용 증가액 (원)
    impact_down     NUMERIC(25, 0),                     -- 금리 하락 시 변화액 (원)
    impact_target   VARCHAR(20)     DEFAULT 'interest_expense',
    source_doc      TEXT,
    note            TEXT,
    checked_at      TIMESTAMPTZ     DEFAULT NOW(),
    CONSTRAINT uq_rate_sensitivity UNIQUE (corp_code, fiscal_year, basis),
    CONSTRAINT ck_rate_sens_basis CHECK (basis IN ('CFS', 'OFS'))
);

-- -----------------------------------------------------------
-- 5. [RAW] ecos_rate (한국은행 기준금리 일별)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ecos_rate (
    id              BIGSERIAL       PRIMARY KEY,
    date            DATE            NOT NULL,
    indicator       VARCHAR(50)     NOT NULL DEFAULT '한국은행 기준금리',
    rate            NUMERIC(8, 4)   NOT NULL,           -- 연% (예: 3.5000)
    unit            VARCHAR(10)     DEFAULT '연%',
    CONSTRAINT uq_ecos_rate UNIQUE (date, indicator)
);

CREATE INDEX IF NOT EXISTS idx_ecos_rate_date ON public.ecos_rate (date DESC);

-- -----------------------------------------------------------
-- 6. [RAW] ecos_fx (ECOS 원/달러, 원/유로 매매기준율 일별)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ecos_fx (
    id              BIGSERIAL       PRIMARY KEY,
    date            DATE            NOT NULL,
    currency        VARCHAR(10)     NOT NULL,           -- USD, EUR, JPY
    exchange_rate   NUMERIC(12, 4)  NOT NULL,           -- 매매기준율
    unit            VARCHAR(20)     DEFAULT 'KRW',
    CONSTRAINT uq_ecos_fx UNIQUE (date, currency)
);

CREATE INDEX IF NOT EXISTS idx_ecos_fx_date_curr ON public.ecos_fx (date DESC, currency);

-- -----------------------------------------------------------
-- 7. [운영] ingestion_event_log (수집 감사 로그)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ingestion_event_log (
    id                  BIGSERIAL       PRIMARY KEY,
    event_type          VARCHAR(30)     NOT NULL,       -- RATE_UPDATE, DART_COLLECT 등
    target_entity       VARCHAR(50)     NOT NULL,
    status              VARCHAR(20)     NOT NULL,       -- SUCCESS, FAILED
    records_affected    INTEGER         DEFAULT 0,
    triggered_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------
-- 8. [CORE] account_mapping_master (계정 매핑 마스터)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.account_mapping_master (
    id                  SERIAL          PRIMARY KEY,
    standard_account    VARCHAR(30)     NOT NULL,       -- operating_profit, interest_expense, etc.
    source_account_id   TEXT            NOT NULL,       -- DART 계정코드
    source_account_nm   TEXT            NOT NULL,       -- DART 계정명
    source_sj_nm        TEXT            NOT NULL,       -- 손익계산서, 재무상태표, 현금흐름표 등
    priority            SMALLINT        NOT NULL DEFAULT 1,
    mapping_status      VARCHAR(20)     NOT NULL DEFAULT 'mapped', -- mapped, review_required
    notes               TEXT,
    CONSTRAINT uq_account_mapping_master UNIQUE (source_account_id, source_account_nm, source_sj_nm)
);

-- 계정 매핑 시드 데이터
INSERT INTO public.account_mapping_master 
    (standard_account, source_sj_nm, source_account_id, source_account_nm, priority, mapping_status, notes)
VALUES
    -- operating_profit (영업이익)
    ('operating_profit', '손익계산서', 'dart_OperatingIncomeLoss', '영업이익', 1, 'mapped', '손익계산서 영업이익 표준'),
    ('operating_profit', '손익계산서', 'dart_OperatingIncomeLoss', '영업이익(손실)', 1, 'mapped', '손익계산서 손실 연도'),
    ('operating_profit', '포괄손익계산서', 'dart_OperatingIncomeLoss', '영업이익', 1, 'mapped', '포괄손익계산서 영업이익'),
    ('operating_profit', '포괄손익계산서', 'dart_OperatingIncomeLoss', '영업이익(손실)', 1, 'mapped', '포괄손익계산서 손실 연도'),
    ('operating_profit', '손익계산서', '-표준계정코드 미사용-', '영업이익', 1, 'mapped', '비표준 영업이익'),
    ('operating_profit', '포괄손익계산서', '-표준계정코드 미사용-', '영업이익', 1, 'mapped', '비표준 영업이익'),

    -- interest_expense (이자비용: ① 이자의 지급(영업) -> ② 이자의 지급(재무) -> ③ 금융비용)
    ('interest_expense', '현금흐름표', 'ifrs-full_InterestPaidClassifiedAsOperatingActivities', '이자의 지급', 1, 'mapped', '현금흐름표 영업활동 이자지급(1순위)'),
    ('interest_expense', '현금흐름표', 'ifrs-full_InterestPaidClassifiedAsOperatingActivities', '이자지급', 1, 'mapped', '현금흐름표 이자지급'),
    ('interest_expense', '현금흐름표', 'ifrs-full_InterestPaidClassifiedAsFinancingActivities', '이자의 지급', 2, 'mapped', '현금흐름표 재무활동 이자지급(2순위)'),
    ('interest_expense', '현금흐름표', 'ifrs-full_InterestPaidClassifiedAsFinancingActivities', '이자지급', 2, 'mapped', '현금흐름표 재무활동 이자지급'),
    ('interest_expense', '손익계산서', 'ifrs-full_FinanceCosts', '금융비용', 3, 'mapped', '손익계산서 금융비용(대체값 3순위)'),
    ('interest_expense', '손익계산서', 'ifrs-full_InterestExpense', '이자비용', 1, 'mapped', '손익계산서 이자비용'),
    ('interest_expense', '포괄손익계산서', 'ifrs-full_InterestExpense', '이자비용', 1, 'mapped', '포괄손익계산서 이자비용'),
    ('interest_expense', '손익계산서', '-표준계정코드 미사용-', '이자비용', 1, 'mapped', '비표준 이자비용'),
    ('interest_expense', '포괄손익계산서', '-표준계정코드 미사용-', '이자비용', 1, 'mapped', '비표준 이자비용'),
    ('interest_expense', '현금흐름표', '-표준계정코드 미사용-', '이자의 지급', 1, 'mapped', '비표준 이자의 지급'),

    -- short_term_borrowings (단기차입금)
    ('short_term_borrowings', '재무상태표', 'ifrs-full_ShorttermBorrowings', '단기차입금', 1, 'mapped', '단기차입금 표준코드'),
    ('short_term_borrowings', '재무상태표', 'ifrs-full_ShorttermBorrowings', '차입금', 1, 'mapped', '단기차입금명 차입금'),
    ('short_term_borrowings', '재무상태표', '-표준계정코드 미사용-', '단기차입금', 1, 'mapped', '비표준 단기차입금'),

    -- current_portion_ltd (유동성장기부채)
    ('current_portion_ltd', '재무상태표', 'ifrs-full_CurrentPortionOfLongtermBorrowings', '유동성장기부채', 1, 'mapped', '유동성장기부채 표준코드'),
    ('current_portion_ltd', '재무상태표', '-표준계정코드 미사용-', '유동성장기부채', 1, 'mapped', '비표준 유동성장기부채'),
    ('current_portion_ltd', '재무상태표', 'ifrs-full_CurrentPortionOfLongtermBorrowings', '유동성장기차입금', 1, 'mapped', '유동성장기차입금'),

    -- (단기+유동성장기부채 합산 계정)
    ('short_term_debt_combined', '재무상태표', 'ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings', '단기차입금및유동성장기부채', 1, 'mapped', '단기+유동성장기부채 합산 계정'),
    ('short_term_debt_combined', '재무상태표', 'ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings', '단기차입금 및 유동성장기부채', 1, 'mapped', '단기+유동성장기부채 합산 계정'),

    -- long_term_borrowings (장기차입금)
    ('long_term_borrowings', '재무상태표', 'dart_LongTermBorrowingsGross', '장기차입금', 1, 'mapped', '장기차입금 DART 표준코드'),
    ('long_term_borrowings', '재무상태표', 'ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived', '장기차입금', 1, 'mapped', '장기차입금 IFRS 코드'),
    ('long_term_borrowings', '재무상태표', '-표준계정코드 미사용-', '장기차입금', 1, 'mapped', '비표준 장기차입금'),

    -- bonds (사채)
    ('bonds', '재무상태표', 'dart_BondsIssued', '사채', 1, 'mapped', '사채 DART 표준코드'),
    ('bonds', '재무상태표', 'ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued', '사채', 1, 'mapped', '사채 IFRS 코드'),
    ('bonds', '재무상태표', '-표준계정코드 미사용-', '사채', 1, 'mapped', '비표준 사채'),

    -- equity (자본총계 / 자기자본)
    ('equity', '재무상태표', 'ifrs-full_Equity', '자본총계', 1, 'mapped', '자본총계 IFRS 표준코드'),
    ('equity', '재무상태표', '-표준계정코드 미사용-', '자본총계', 1, 'mapped', '비표준 자본총계')
ON CONFLICT (source_account_id, source_account_nm, source_sj_nm) DO UPDATE
    SET standard_account = EXCLUDED.standard_account,
        priority         = EXCLUDED.priority,
        mapping_status   = EXCLUDED.mapping_status,
        notes            = EXCLUDED.notes;

-- -----------------------------------------------------------
-- 9. [CORE] finance_standard (표준화 재무 데이터)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.finance_standard (
    id                      BIGSERIAL       PRIMARY KEY,
    corp_code               CHAR(8)         NOT NULL REFERENCES public.dim_company(corp_code),
    fiscal_year             SMALLINT        NOT NULL,
    period                  VARCHAR(10)     NOT NULL DEFAULT 'FY', -- FY(연간)
    fs_div                  VARCHAR(5)      NOT NULL DEFAULT 'CFS',-- CFS(연결) / OFS(별도)
    
    -- 표준 항목
    operating_profit        NUMERIC(25, 0), -- 영업이익 (적자 음수 보존)
    interest_expense        NUMERIC(25, 0), -- 이자비용 (결측 NULL 보존)
    interest_source         VARCHAR(30),    -- paid_operating / paid_financing / finance_costs
    short_term_borrowings   NUMERIC(25, 0), -- 단기차입금 원값
    current_portion_ltd     NUMERIC(25, 0), -- 유동성장기부채 원값
    long_term_borrowings    NUMERIC(25, 0), -- 장기차입금 원값
    bonds                   NUMERIC(25, 0), -- 사채 원값
    short_term_debt         NUMERIC(25, 0), -- STD = 합산계정 또는 (단기차입금 + 유동성장기부채)
    debt                    NUMERIC(25, 0), -- TD = STD + 장기차입금 + 사채 (리스부채 제외)
    equity                  NUMERIC(25, 0), -- EQ = 자본총계
    
    mapping_status          VARCHAR(20)     NOT NULL DEFAULT 'mapped',
    review_note             TEXT,
    CONSTRAINT uq_finance_standard UNIQUE (corp_code, fiscal_year, period, fs_div)
);

CREATE INDEX IF NOT EXISTS idx_finance_std_corp_year ON public.finance_standard (corp_code, fiscal_year);

-- -----------------------------------------------------------
-- 10. [CORE VIEW] v_year_end_rate (연말 기준금리 VIEW)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.v_year_end_rate CASCADE;
CREATE OR REPLACE VIEW public.v_year_end_rate AS
WITH ranked AS (
    SELECT
        EXTRACT(YEAR FROM date)::SMALLINT AS fiscal_year,
        rate AS base_rate,
        date AS rate_date,
        ROW_NUMBER() OVER (
            PARTITION BY EXTRACT(YEAR FROM date)
            ORDER BY date DESC
        ) AS rn
    FROM public.ecos_rate
    WHERE indicator LIKE '%기준금리%'
)
SELECT fiscal_year, base_rate, rate_date
FROM ranked
WHERE rn = 1
ORDER BY fiscal_year;

-- -----------------------------------------------------------
-- 11. [CORE VIEW] v_year_end_fx (연말 환율 및 YoY 변동률 VIEW)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.v_year_end_fx CASCADE;
CREATE OR REPLACE VIEW public.v_year_end_fx AS
WITH ranked AS (
    SELECT
        EXTRACT(YEAR FROM date)::SMALLINT AS fiscal_year,
        currency,
        exchange_rate,
        date,
        ROW_NUMBER() OVER (
            PARTITION BY EXTRACT(YEAR FROM date), currency
            ORDER BY date DESC
        ) AS rn
    FROM public.ecos_fx
),
year_end AS (
    SELECT fiscal_year, currency, exchange_rate AS year_end_fx, date
    FROM ranked
    WHERE rn = 1
)
SELECT
    fiscal_year,
    currency,
    year_end_fx,
    ROUND(
        (year_end_fx - LAG(year_end_fx) OVER (PARTITION BY currency ORDER BY fiscal_year))
        / NULLIF(LAG(year_end_fx) OVER (PARTITION BY currency ORDER BY fiscal_year), 0)
        * 100,
        2
    ) AS yoy_change_pct
FROM year_end
ORDER BY currency, fiscal_year;

-- -----------------------------------------------------------
-- 12. [MART] dim_scenario (금리/환율 충격 시나리오 마스터)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.dim_scenario (
    scenario_id     VARCHAR(10)     PRIMARY KEY,    -- R1, R2, R3, F10
    scenario_type   VARCHAR(10)     NOT NULL,       -- rate, fx
    shock_value     NUMERIC(8, 4)   NOT NULL,       -- 0.0050, 0.0100, 0.0225, 0.1000
    label           VARCHAR(30)     NOT NULL,       -- 금리 +0.5%p, 금리 +1.0%p, 금리 +2.25%p, 환율 ±10%
    rationale       TEXT
);

INSERT INTO public.dim_scenario (scenario_id, scenario_type, shock_value, label, rationale)
VALUES
    ('R1',  'rate', 0.0050, '금리 +0.5%p',  '결산 이후 실제 인상분'),
    ('R2',  'rate', 0.0100, '금리 +1.0%p',  '기업 공시 기준 100bp 이자율 민감도'),
    ('R3',  'rate', 0.0225, '금리 +2.25%p', '2022년 실제 최대 인상폭 및 BCBS 225bp 원화 금리 충격 기준'),
    ('F10', 'fx',   0.1000, '환율 ±10%',    '사업보고서 주석 공시 기준 통화별 충격률')
ON CONFLICT (scenario_id) DO UPDATE
    SET scenario_type = EXCLUDED.scenario_type,
        shock_value   = EXCLUDED.shock_value,
        label         = EXCLUDED.label,
        rationale     = EXCLUDED.rationale;

-- -----------------------------------------------------------
-- 13. [MART] mart_rate_stress (금리 스트레스 마트)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.mart_rate_stress (
    corp_code                   CHAR(8)         NOT NULL REFERENCES public.dim_company(corp_code),
    fiscal_year                 SMALLINT        NOT NULL,
    scenario_id                 VARCHAR(10)     NOT NULL REFERENCES public.dim_scenario(scenario_id),
    
    operating_profit            NUMERIC(25, 0), -- OI
    interest_expense            NUMERIC(25, 0), -- IE
    short_term_debt             NUMERIC(25, 0), -- STD
    debt                        NUMERIC(25, 0), -- TD
    st_debt_ratio               NUMERIC(10, 4), -- STD / TD
    
    icr_current                 NUMERIC(12, 4), -- OI / IE
    add_interest_base           NUMERIC(25, 0), -- STD × Δr
    add_interest_conservative   NUMERIC(25, 0), -- TD × Δr
    icr_stress_base             NUMERIC(12, 4), -- OI / (IE + STD × Δr)
    icr_stress_conservative     NUMERIC(12, 4), -- OI / (IE + TD × Δr) (보수적 등급 기준)
    icr_drop                    NUMERIC(12, 4), -- 현재 ICR - Stress ICR(보수)
    
    grade_current               VARCHAR(10),    -- 정상 / 관찰 / 추가검토 / 판정불가
    grade_stress                VARCHAR(10),    -- 정상 / 관찰 / 추가검토 / 판정불가
    risk_shift_yn               BOOLEAN,        -- 현재 정상·관찰 → 시나리오 추가검토 시 TRUE
    grade_reason                TEXT,           -- 영업적자, 무차입, 데이터 없음 등
    
    CONSTRAINT pk_mart_rate_stress PRIMARY KEY (corp_code, fiscal_year, scenario_id),
    CONSTRAINT ck_grade_current CHECK (grade_current IN ('정상', '관찰', '추가검토', '판정불가')),
    CONSTRAINT ck_grade_stress CHECK (grade_stress IN ('정상', '관찰', '추가검토', '판정불가'))
);

-- -----------------------------------------------------------
-- 14. [MART] mart_fx_exposure (환율 익스포저 마트)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.mart_fx_exposure (
    corp_code           CHAR(8)         NOT NULL REFERENCES public.dim_company(corp_code),
    fiscal_year         SMALLINT        NOT NULL,
    basis               VARCHAR(5)      NOT NULL DEFAULT 'CFS',
    
    s_net_1pct          NUMERIC(25, 0), -- 1%당 순영향 (원)
    s_gross_1pct        NUMERIC(25, 0), -- 1%당 총노출 (원)
    main_currency       VARCHAR(10),    -- 주요 노출통화
    equity              NUMERIC(25, 0), -- 자기자본 (원)
    fx_sensitivity_pct  NUMERIC(10, 4), -- |s_net_1pct| / equity × 100
    direction           VARCHAR(20),    -- 원화 약세 시 손실형 / 원화 강세 시 손실형 / 중립
    
    impact_fx_up10      NUMERIC(25, 0), -- 환율 +10% 영향액
    impact_fx_down10    NUMERIC(25, 0), -- 환율 -10% 영향액
    impact_pct_equity   NUMERIC(10, 4), -- ±10% 손실방향 영향액 / 자기자본 × 100
    relative_position   VARCHAR(5),     -- 부품 8개사 내 상대위치 (상 / 중 / 하)
    k_ref_pct           NUMERIC(10, 4), -- 최근 5년 최대 연간 변동률 (%)
    flags               TEXT,           -- 비고 및 주의표시
    
    CONSTRAINT pk_mart_fx_exposure PRIMARY KEY (corp_code, fiscal_year)
);

-- -----------------------------------------------------------
-- 15. [MART VIEW] v_screening (종합 스크리닝 VIEW - Power BI용)
-- -----------------------------------------------------------
DROP VIEW IF EXISTS public.v_screening CASCADE;
CREATE OR REPLACE VIEW public.v_screening AS
SELECT
    r.corp_code,
    r.fiscal_year,
    r.scenario_id,
    r.grade_stress,
    f.relative_position,
    
    -- risk_type 판정: 금리 / FX / 금리+FX / 해당 없음
    CASE
        WHEN r.grade_stress = '추가검토' AND f.relative_position = '상' THEN '금리+FX'
        WHEN r.grade_stress = '추가검토' THEN '금리'
        WHEN f.relative_position = '상' THEN 'FX'
        ELSE '해당 없음'
    END AS risk_type,
    
    -- 우선검토 대상 (금리 추가검토 또는 FX 상)
    CASE
        WHEN r.grade_stress = '추가검토' OR f.relative_position = '상' THEN TRUE
        ELSE FALSE
    END AS priority_review_yn,
    
    -- 우선순위 단계 (1 = 둘 다 취약, 2 = 하나만 취약, 3 = 해당 없음)
    CASE
        WHEN r.grade_stress = '추가검토' AND f.relative_position = '상' THEN 1
        WHEN r.grade_stress = '추가검토' OR f.relative_position = '상' THEN 2
        ELSE 3
    END AS priority_tier,
    
    c.in_sample
FROM public.mart_rate_stress r
JOIN public.dim_company c ON c.corp_code = r.corp_code
LEFT JOIN public.mart_fx_exposure f 
       ON f.corp_code = r.corp_code AND f.fiscal_year = r.fiscal_year;
