-- ============================================================
-- RAW 레이어 DDL
-- 목적: API 원본 데이터를 가공 없이 그대로 저장
-- 원칙:
--   - 원본 컬럼명 보존
--   - 금액은 문자열로 수신되나 DB는 numeric 저장 (변환 실패 시 raw_text 컬럼 병용)
--   - loaded_at 자동 기록으로 재적재 추적 가능
--   - 삭제하지 않음 (INSERT only, 재적재 시 batch_id로 구분)
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- raw.dart_financial
-- 원천: OpenDART fnlttSinglAcntAll.json
-- Grain: 기업(corp_code) × 사업연도(bsns_year) × 재무제표구분(fs_div) × 계정(account_id + account_nm)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.dart_financial (
    id                  BIGSERIAL       PRIMARY KEY,

    -- 수집 메타
    batch_id            UUID            NOT NULL DEFAULT gen_random_uuid(),
    loaded_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 기업 식별
    corp_code           CHAR(8)         NOT NULL,   -- DART 8자리 고유번호
    corp_name           TEXT            NOT NULL,

    -- 보고서 식별
    bsns_year           CHAR(4)         NOT NULL,   -- 사업연도 (예: '2023')
    reprt_code          CHAR(5)         NOT NULL,   -- 11011=사업보고서, 11012=반기, 11013=1분기, 11014=3분기
    fs_div              VARCHAR(3)      NOT NULL,   -- CFS=연결, OFS=개별
    rcept_no            VARCHAR(14),                -- 접수번호

    -- 계정 식별 (API 원본)
    sj_div              VARCHAR(5),                 -- BS=재무상태표, IS=손익, CF=현금흐름 등
    sj_nm               TEXT,                       -- 재무제표명 (한글)
    account_id          TEXT,                       -- IFRS/DART 표준계정코드 (없으면 '-표준계정코드 미사용-')
    account_nm          TEXT,                       -- 계정명 (한글, 기업마다 상이)
    account_detail      TEXT,                       -- 계정 세부구분
    ord                 SMALLINT,                   -- 표시 순서

    -- 금액 (단위: 원)
    -- thstrm = 당기, frmtrm = 전기, bfefrmtrm = 전전기
    thstrm_nm           TEXT,                       -- 당기 기수명 (예: '제 53 기')
    thstrm_amount       NUMERIC(25, 0),             -- 당기 금액 (NULL 가능: 미기재)
    thstrm_add_amount   NUMERIC(25, 0),             -- 당기 누적금액 (분기보고서용)
    frmtrm_nm           TEXT,
    frmtrm_amount       NUMERIC(25, 0),
    bfefrmtrm_nm        TEXT,
    bfefrmtrm_amount    NUMERIC(25, 0),

    -- 통화
    currency            CHAR(3)         DEFAULT 'KRW'
);

-- 인덱스: 조회 패턴 기준
CREATE INDEX IF NOT EXISTS idx_raw_dart_corp_year
    ON raw.dart_financial (corp_code, bsns_year);

CREATE INDEX IF NOT EXISTS idx_raw_dart_account_id
    ON raw.dart_financial (account_id)
    WHERE account_id NOT LIKE '%-표준계정코드 미사용-%';  -- 유효한 계정코드만

CREATE INDEX IF NOT EXISTS idx_raw_dart_loaded_at
    ON raw.dart_financial (loaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_dart_batch
    ON raw.dart_financial (batch_id);

-- 테이블 코멘트
COMMENT ON TABLE  raw.dart_financial IS 'OpenDART API 원본 재무제표 데이터. fnlttSinglAcntAll.json 응답 그대로 적재.';
COMMENT ON COLUMN raw.dart_financial.batch_id          IS '적재 배치 단위 식별자. 동일 배치로 적재된 행을 묶어 재적재 추적에 사용.';
COMMENT ON COLUMN raw.dart_financial.corp_code          IS 'DART 기업 고유번호 (8자리, 앞 0 포함)';
COMMENT ON COLUMN raw.dart_financial.reprt_code         IS '보고서 코드: 11011=사업, 11012=반기, 11013=1분기, 11014=3분기';
COMMENT ON COLUMN raw.dart_financial.fs_div             IS '재무제표 구분: CFS=연결재무제표, OFS=별도(개별)재무제표';
COMMENT ON COLUMN raw.dart_financial.account_id         IS 'IFRS/DART 표준 계정코드. 표준 미적용 시 "-표준계정코드 미사용-"';
COMMENT ON COLUMN raw.dart_financial.thstrm_amount      IS '당기 금액 (원 단위). API에서 문자열로 수신하며, 쉼표 제거 후 numeric 변환.';


-- ──────────────────────────────────────────────────────────────
-- raw.ecos_base_rate
-- 원천: 한국은행 ECOS API StatisticSearch (통계코드 722Y001, 항목 0101000)
-- Grain: 날짜 1개 (일별)
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.ecos_base_rate (
    id              BIGSERIAL       PRIMARY KEY,

    -- 수집 메타
    batch_id        UUID            NOT NULL DEFAULT gen_random_uuid(),
    loaded_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- ECOS 원본 필드
    stat_code       VARCHAR(10)     NOT NULL,   -- 통계표 코드 (예: 722Y001)
    stat_name       TEXT,                       -- 통계표명 (예: 1.3.1. 한국은행 기준금리 및 여수신금리)
    item_code1      VARCHAR(10)     NOT NULL,   -- 항목코드1 (예: 0101000)
    item_name1      TEXT,                       -- 항목명1 (예: 한국은행 기준금리)
    unit_name       TEXT,                       -- 단위 (예: 연%)

    -- 시계열 값
    time_period     CHAR(8)         NOT NULL,   -- API 원본 날짜 문자열 (YYYYMMDD)
    rate_date       DATE            NOT NULL,   -- 변환된 날짜 (파티션 키 후보)
    data_value      NUMERIC(8, 4)   NOT NULL,   -- 기준금리 (예: 3.5000)

    -- 유니크 제약: 같은 날짜가 중복 적재되지 않도록 (재적재 시 upsert 기준)
    CONSTRAINT uq_ecos_base_rate_date UNIQUE (stat_code, item_code1, rate_date)
);

CREATE INDEX IF NOT EXISTS idx_raw_ecos_rate_date
    ON raw.ecos_base_rate (rate_date DESC);

COMMENT ON TABLE  raw.ecos_base_rate IS '한국은행 ECOS API 기준금리 일별 원본. 통계코드 722Y001, 항목 0101000.';
COMMENT ON COLUMN raw.ecos_base_rate.time_period  IS 'ECOS API TIME 필드 원본값 (YYYYMMDD 문자열)';
COMMENT ON COLUMN raw.ecos_base_rate.rate_date    IS 'time_period를 DATE 타입으로 변환한 값 (조회 인덱스 키)';
COMMENT ON COLUMN raw.ecos_base_rate.data_value   IS '기준금리 (연%, 소수점 4자리까지 저장)';
