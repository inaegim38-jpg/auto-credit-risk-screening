-- =============================================================
-- v3 Schema Update DDL
-- finance_lab (PostgreSQL 17)
-- 실행: docker cp → docker exec psql -f
-- =============================================================

-- -----------------------------------------------------------
-- 1. dim_company (기업 마스터) — 신규 생성
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.dim_company (
    corp_code       CHAR(8)      NOT NULL PRIMARY KEY,   -- DART 기업코드 (8자리, 앞 0 포함)
    company_name    TEXT         NOT NULL,               -- 기업명 (한글)
    stock_code      CHAR(6),                             -- 종목코드 (코스피/코스닥 6자리)
    industry_group  VARCHAR(20)  NOT NULL DEFAULT '자동차부품', -- 업종 그룹 레이블
    in_sample       BOOLEAN      NOT NULL DEFAULT TRUE   -- TRUE = 최종 분석 표본, FALSE = 참고용
);

COMMENT ON TABLE  public.dim_company IS '기업 마스터 — v3 자동차부품 표본 + 완성차 참고사';
COMMENT ON COLUMN public.dim_company.corp_code      IS 'DART 기업고유번호 8자리 (앞 0 포함)';
COMMENT ON COLUMN public.dim_company.company_name   IS '기업명 한글';
COMMENT ON COLUMN public.dim_company.stock_code     IS '증권 종목코드 6자리';
COMMENT ON COLUMN public.dim_company.industry_group IS '업종 그룹: 자동차부품 / 완성차 등';
COMMENT ON COLUMN public.dim_company.in_sample      IS 'TRUE=분석 표본, FALSE=참고용(완성차)';

-- -----------------------------------------------------------
-- 2. dim_company 표본 10개사 삽입
--    corp_code: corpCode.xml 조회 확인값 (2026-10-07 기준)
-- -----------------------------------------------------------
INSERT INTO public.dim_company
    (corp_code, company_name, stock_code, industry_group, in_sample)
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
    ('00106641', '기아',        '000270', '완성차',     FALSE)
ON CONFLICT (corp_code) DO UPDATE
    SET company_name  = EXCLUDED.company_name,
        stock_code    = EXCLUDED.stock_code,
        industry_group= EXCLUDED.industry_group,
        in_sample     = EXCLUDED.in_sample;

-- -----------------------------------------------------------
-- 3. finance_standard — 6개 컬럼 추가
--    (이미 존재하면 ADD COLUMN IF NOT EXISTS 로 안전하게)
-- -----------------------------------------------------------
ALTER TABLE public.finance_standard
    ADD COLUMN IF NOT EXISTS interest_source        VARCHAR(30),    -- 이자비용 출처: cash_operating / cash_financing / fin_cost
    ADD COLUMN IF NOT EXISTS short_term_borrowings  NUMERIC,        -- 단기차입금 (개별 계정 원값)
    ADD COLUMN IF NOT EXISTS current_portion_ltd    NUMERIC,        -- 유동성장기부채 (개별 계정 원값)
    ADD COLUMN IF NOT EXISTS long_term_borrowings   NUMERIC,        -- 장기차입금 (개별 계정 원값)
    ADD COLUMN IF NOT EXISTS bonds                  NUMERIC,        -- 사채 (개별 계정 원값)
    ADD COLUMN IF NOT EXISTS review_note            TEXT;           -- 매핑 검토 메모 (자유기술)

COMMENT ON COLUMN public.finance_standard.interest_source       IS '이자비용 출처: cash_operating=이자지급(영업), cash_financing=이자지급(재무), fin_cost=금융비용(대체값)';
COMMENT ON COLUMN public.finance_standard.short_term_borrowings IS '단기차입금 개별 계정 원값 (합산 계정 이중합산 검증용)';
COMMENT ON COLUMN public.finance_standard.current_portion_ltd   IS '유동성장기부채 개별 계정 원값';
COMMENT ON COLUMN public.finance_standard.long_term_borrowings  IS '장기차입금 개별 계정 원값';
COMMENT ON COLUMN public.finance_standard.bonds                 IS '사채 개별 계정 원값';
COMMENT ON COLUMN public.finance_standard.review_note          IS '매핑 품질 검토 메모 (이중합산 의심 등)';

-- -----------------------------------------------------------
-- 4. fx_risk_input — 컬럼명 변경 + 5개 컬럼 추가
-- -----------------------------------------------------------

-- 4-1. 기존 UNIQUE 제약 제거 (새 제약으로 교체)
ALTER TABLE public.fx_risk_input
    DROP CONSTRAINT IF EXISTS uq_fx_risk_input;

-- 4-2. risk_input → impact_up 컬럼명 변경
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='fx_risk_input' AND column_name='risk_input'
    ) THEN
        ALTER TABLE public.fx_risk_input RENAME COLUMN risk_input TO impact_up;
    END IF;
END $$;

-- 4-3. 신규 컬럼 추가
ALTER TABLE public.fx_risk_input
    ADD COLUMN IF NOT EXISTS basis          VARCHAR(5),     -- CFS(연결) / OFS(별도) — 공시 기준 구분
    ADD COLUMN IF NOT EXISTS shock_pct      NUMERIC,        -- 공시 충격률 (5 또는 10, 단위: %)
    ADD COLUMN IF NOT EXISTS impact_down    NUMERIC,        -- 외화 하락 시 영향액 (음수 or 양수 원문 그대로)
    ADD COLUMN IF NOT EXISTS impact_target  VARCHAR(20),    -- 영향 대상: pretax_income / equity
    ADD COLUMN IF NOT EXISTS source_doc     TEXT;           -- 보고서명 · 주석 번호 · 페이지 (원문 추적)

COMMENT ON COLUMN public.fx_risk_input.impact_up     IS '외화 상승(+충격) 시 세전이익/자본 영향액 (단위: 백만원)';
COMMENT ON COLUMN public.fx_risk_input.impact_down   IS '외화 하락(-충격) 시 세전이익/자본 영향액 (단위: 백만원)';
COMMENT ON COLUMN public.fx_risk_input.shock_pct     IS '공시 환율 충격률 (5 또는 10, 단위: %). 기업·연도마다 다름';
COMMENT ON COLUMN public.fx_risk_input.basis         IS '재무제표 기준: CFS=연결, OFS=별도';
COMMENT ON COLUMN public.fx_risk_input.impact_target IS '영향 대상 계정: pretax_income(세전이익) / equity(자본)';
COMMENT ON COLUMN public.fx_risk_input.source_doc    IS '원문 출처 (보고서명, 주석번호, 페이지)';

-- 4-4. 새 UNIQUE 제약 추가 (currency + basis 포함)
ALTER TABLE public.fx_risk_input
    ADD CONSTRAINT uq_fx_risk_input
        UNIQUE (corp_code, fiscal_year, currency, basis);

-- -----------------------------------------------------------
-- 5. rate_sensitivity_input — 신규 생성 (이자율 민감도, 검증 전용)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.rate_sensitivity_input (
    id              BIGSERIAL    NOT NULL PRIMARY KEY,
    corp_code       CHAR(8)      NOT NULL REFERENCES public.dim_company(corp_code),
    fiscal_year     SMALLINT     NOT NULL,
    basis           VARCHAR(5)   NOT NULL,               -- CFS / OFS
    shock_pctp      NUMERIC,                             -- 공시 금리 변동폭 %p (예: 1)
    impact_up       NUMERIC,                             -- 금리 상승 시 영향액
    impact_down     NUMERIC,                             -- 금리 하락 시 영향액
    impact_target   VARCHAR(20),                         -- pretax_income / interest_expense
    source_doc      TEXT,                                -- 보고서명 · 주석 번호 · 페이지
    note            TEXT,                                -- 비고: 공시 없음 / 미확인 / 등
    CONSTRAINT uq_rate_sensitivity UNIQUE (corp_code, fiscal_year, basis)
);

COMMENT ON TABLE  public.rate_sensitivity_input IS '이자율 민감도 공시 — v3 검증 전용. Stress ICR 계산 투입 아님';
COMMENT ON COLUMN public.rate_sensitivity_input.corp_code     IS 'dim_company FK';
COMMENT ON COLUMN public.rate_sensitivity_input.fiscal_year   IS '회계연도 (2021~2023)';
COMMENT ON COLUMN public.rate_sensitivity_input.basis         IS '재무제표 기준: CFS=연결, OFS=별도';
COMMENT ON COLUMN public.rate_sensitivity_input.shock_pctp    IS '공시 금리 충격 크기 (%p). 대부분 1';
COMMENT ON COLUMN public.rate_sensitivity_input.impact_up     IS '금리 상승 시 세전이익/이자비용 영향액';
COMMENT ON COLUMN public.rate_sensitivity_input.impact_down   IS '금리 하락 시 영향액 (공시 있으면 입력)';
COMMENT ON COLUMN public.rate_sensitivity_input.impact_target IS '영향 대상: pretax_income / interest_expense';
COMMENT ON COLUMN public.rate_sensitivity_input.source_doc    IS '원문 출처 (보고서명, 주석번호, 페이지)';
COMMENT ON COLUMN public.rate_sensitivity_input.note         IS '비고: 공시 없음 / 미확인 / 특이사항';

-- -----------------------------------------------------------
-- 6. v_year_end_rate — 뷰 생성 (연말 기준금리)
-- -----------------------------------------------------------
CREATE OR REPLACE VIEW public.v_year_end_rate AS
/*
  연말(12-31) 기준금리 뷰.
  ecos_rate 테이블에서 각 연도의 12월 가장 마지막 날짜 행을 추출한다.
  indicator = '한국은행 기준금리'인 행만 대상 (stat_code 722Y001, item 0101000).
*/
WITH ranked AS (
    SELECT
        EXTRACT(YEAR FROM date)::SMALLINT   AS fiscal_year,
        rate                                AS base_rate,
        date                                AS rate_date,
        ROW_NUMBER() OVER (
            PARTITION BY EXTRACT(YEAR FROM date)
            ORDER BY date DESC              -- 연도 내 가장 늦은 날짜 = 연말
        )                                   AS rn
    FROM public.ecos_rate
    WHERE EXTRACT(MONTH FROM date) = 12
      AND indicator LIKE '%%기준금리%%'
)
SELECT fiscal_year, base_rate, rate_date
FROM   ranked
WHERE  rn = 1
ORDER  BY fiscal_year;

COMMENT ON VIEW public.v_year_end_rate IS '연말 한국은행 기준금리 (ecos_rate 기반). Stress ICR 산정 기준값으로 사용';

-- -----------------------------------------------------------
-- 7. v_year_end_fx — 뷰 생성 (연말 환율 + 전년 대비 변동률)
-- -----------------------------------------------------------
CREATE OR REPLACE VIEW public.v_year_end_fx AS
/*
  연말 환율 뷰. 각 연도의 12월 가장 마지막 영업일 환율을 추출하고,
  LAG()으로 전년 연말 대비 YoY 변동률을 계산한다.
  최근 5년 최대 연간 변동률(충격 k) 계산에 활용.
*/
WITH ranked AS (
    SELECT
        EXTRACT(YEAR FROM date)::SMALLINT   AS fiscal_year,
        currency,
        exchange_rate,
        date,
        ROW_NUMBER() OVER (
            PARTITION BY EXTRACT(YEAR FROM date), currency
            ORDER BY date DESC              -- 연도 내 가장 늦은 날짜 = 연말
        )                                   AS rn
    FROM public.ecos_fx
),
year_end AS (
    SELECT fiscal_year, currency, exchange_rate AS year_end_fx, date
    FROM   ranked
    WHERE  rn = 1
)
SELECT
    fiscal_year,
    currency,
    year_end_fx,
    date                                    AS rate_date,
    ROUND(
        (year_end_fx
         - LAG(year_end_fx) OVER (PARTITION BY currency ORDER BY fiscal_year)
        )
        / LAG(year_end_fx) OVER (PARTITION BY currency ORDER BY fiscal_year)
        * 100,
        2
    )                                       AS yoy_change_pct  -- 전년 연말 대비 변동률 (%)
FROM year_end
ORDER BY currency, fiscal_year;

COMMENT ON VIEW public.v_year_end_fx IS '연말 환율 + 전년 대비 YoY 변동률 (ecos_fx 기반). 충격 k(최근 5년 최대) 계산에 사용';

-- -----------------------------------------------------------
-- 완료 확인
-- -----------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE '=== v3 Schema Update 완료 ===';
    RAISE NOTICE 'dim_company         : 신규 생성 + 10개사 INSERT';
    RAISE NOTICE 'finance_standard    : 6개 컬럼 추가';
    RAISE NOTICE 'fx_risk_input       : risk_input→impact_up 변경, 5개 컬럼 추가';
    RAISE NOTICE 'rate_sensitivity_input : 신규 생성';
    RAISE NOTICE 'v_year_end_rate     : 뷰 생성';
    RAISE NOTICE 'v_year_end_fx       : 뷰 생성';
END $$;
