-- ============================================================
-- MART 뷰 및 계산 로직
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- 헬퍼 함수: ICR 위험 등급 분류
-- ──────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION mart.classify_icr_grade(icr NUMERIC)
RETURNS VARCHAR(8)
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT CASE
        WHEN icr IS NULL        THEN 'NULL'     -- 계산 불가 (분모 0 또는 NULL)
        WHEN icr < 0            THEN 'NEGATIVE'  -- 영업이익 음수
        WHEN icr < 0.5          THEN 'CRITICAL'  -- 심각한 위험
        WHEN icr < 1.0          THEN 'DANGER'    -- 이자 감당 불가
        WHEN icr < 2.0          THEN 'WATCH'     -- 주의
        ELSE                         'SAFE'      -- 양호
    END
$$;

COMMENT ON FUNCTION mart.classify_icr_grade IS
'ICR 수치를 위험 등급으로 분류.
SAFE(≥2.0) / WATCH(1.0~2.0) / DANGER(<1.0) / CRITICAL(<0.5) / NEGATIVE(음수) / NULL(계산불가)';


-- ──────────────────────────────────────────────────────────────
-- MART 데이터 생성 Stored Procedure
-- 실행: CALL mart.refresh_stress_analysis();
-- ──────────────────────────────────────────────────────────────
CREATE OR REPLACE PROCEDURE mart.refresh_stress_analysis()
LANGUAGE plpgsql
AS $$
DECLARE
    v_scenarios NUMERIC[] := ARRAY[0.50, 1.00, 2.00];  -- 금리 상승 시나리오 (%p)
    v_scenario  NUMERIC;
    v_label     TEXT;
BEGIN
    FOREACH v_scenario IN ARRAY v_scenarios LOOP
        v_label := '+' || v_scenario::TEXT || '%p';

        INSERT INTO mart.stress_analysis (
            corp_code,
            corp_name,
            fiscal_year,
            base_rate,
            rate_date,
            rate_scenario_pct,
            scenario_label,
            operating_income,
            interest_expense,
            short_term_debt,
            long_term_debt,
            bonds_payable,
            current_ltd,
            total_debt,
            additional_interest_lower,
            additional_interest_upper,
            icr_current,
            icr_scenario_lower,
            icr_scenario_upper,
            icr_grade_current,
            icr_grade_lower,
            icr_grade_upper,
            has_null_input,
            null_fields,
            refreshed_at
        )
        SELECT
            f.corp_code,
            c.corp_name,
            f.fiscal_year,
            r.base_rate,
            r.rate_date,
            v_scenario                              AS rate_scenario_pct,
            v_label                                 AS scenario_label,

            -- 투입 재무지표 피벗
            MAX(CASE WHEN f.standard_account = 'operating_income'  THEN f.amount END) AS operating_income,
            MAX(CASE WHEN f.standard_account = 'interest_expense'  THEN f.amount END) AS interest_expense,
            MAX(CASE WHEN f.standard_account = 'short_term_debt'   THEN f.amount END) AS short_term_debt,
            MAX(CASE WHEN f.standard_account = 'long_term_debt'    THEN f.amount END) AS long_term_debt,
            MAX(CASE WHEN f.standard_account = 'bonds_payable'     THEN f.amount END) AS bonds_payable,
            MAX(CASE WHEN f.standard_account = 'current_ltd'       THEN f.amount END) AS current_ltd,

            -- 총차입금 = NULL 제외 합산
            COALESCE(MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END), 0)
            + COALESCE(MAX(CASE WHEN f.standard_account = 'long_term_debt' THEN f.amount END), 0)
            + COALESCE(MAX(CASE WHEN f.standard_account = 'bonds_payable'  THEN f.amount END), 0)
            + COALESCE(MAX(CASE WHEN f.standard_account = 'current_ltd'    THEN f.amount END), 0)
                                                    AS total_debt,

            -- 하한 추가이자: 단기차입금 × 금리상승폭
            CASE
                WHEN MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END) IS NULL THEN NULL
                ELSE ROUND(
                    MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END)
                    * v_scenario / 100
                )
            END                                     AS additional_interest_lower,

            -- 상한 추가이자: 총차입금 × 금리상승폭
            ROUND((
                COALESCE(MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END), 0)
                + COALESCE(MAX(CASE WHEN f.standard_account = 'long_term_debt' THEN f.amount END), 0)
                + COALESCE(MAX(CASE WHEN f.standard_account = 'bonds_payable'  THEN f.amount END), 0)
                + COALESCE(MAX(CASE WHEN f.standard_account = 'current_ltd'    THEN f.amount END), 0)
            ) * v_scenario / 100)                   AS additional_interest_upper,

            -- 현재 ICR
            CASE
                WHEN MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END) IS NULL THEN NULL
                WHEN MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END) = 0    THEN NULL
                ELSE ROUND(
                    MAX(CASE WHEN f.standard_account = 'operating_income'  THEN f.amount END)::NUMERIC
                    / MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END)::NUMERIC
                , 4)
            END                                     AS icr_current,

            -- 시나리오 ICR (하한)
            CASE
                WHEN MAX(CASE WHEN f.standard_account = 'interest_expense'  THEN f.amount END) IS NULL THEN NULL
                WHEN MAX(CASE WHEN f.standard_account = 'short_term_debt'   THEN f.amount END) IS NULL THEN NULL
                WHEN (MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END)
                      + ROUND(MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END) * v_scenario / 100)) = 0
                     THEN NULL
                ELSE ROUND(
                    MAX(CASE WHEN f.standard_account = 'operating_income'  THEN f.amount END)::NUMERIC
                    / (MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END)
                       + ROUND(MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END) * v_scenario / 100))::NUMERIC
                , 4)
            END                                     AS icr_scenario_lower,

            -- 시나리오 ICR (상한)
            CASE
                WHEN MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END) IS NULL THEN NULL
                WHEN (MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END)
                      + ROUND((
                            COALESCE(MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END), 0)
                            + COALESCE(MAX(CASE WHEN f.standard_account = 'long_term_debt' THEN f.amount END), 0)
                            + COALESCE(MAX(CASE WHEN f.standard_account = 'bonds_payable'  THEN f.amount END), 0)
                            + COALESCE(MAX(CASE WHEN f.standard_account = 'current_ltd'    THEN f.amount END), 0)
                        ) * v_scenario / 100)) = 0
                     THEN NULL
                ELSE ROUND(
                    MAX(CASE WHEN f.standard_account = 'operating_income' THEN f.amount END)::NUMERIC
                    / (MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END)
                       + ROUND((
                            COALESCE(MAX(CASE WHEN f.standard_account = 'short_term_debt' THEN f.amount END), 0)
                            + COALESCE(MAX(CASE WHEN f.standard_account = 'long_term_debt' THEN f.amount END), 0)
                            + COALESCE(MAX(CASE WHEN f.standard_account = 'bonds_payable'  THEN f.amount END), 0)
                            + COALESCE(MAX(CASE WHEN f.standard_account = 'current_ltd'    THEN f.amount END), 0)
                        ) * v_scenario / 100))::NUMERIC
                , 4)
            END                                     AS icr_scenario_upper,

            -- ICR 등급 (별도 함수 호출)
            mart.classify_icr_grade(
                CASE
                    WHEN MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END) IS NULL THEN NULL
                    WHEN MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END) = 0    THEN NULL
                    ELSE ROUND(
                        MAX(CASE WHEN f.standard_account = 'operating_income'  THEN f.amount END)::NUMERIC
                        / MAX(CASE WHEN f.standard_account = 'interest_expense' THEN f.amount END)::NUMERIC
                    , 4)
                END
            )                                       AS icr_grade_current,

            'PENDING'                               AS icr_grade_lower,   -- 후처리로 UPDATE
            'PENDING'                               AS icr_grade_upper,

            -- NULL 존재 여부
            (
                MAX(CASE WHEN f.standard_account = 'operating_income'  THEN f.amount END) IS NULL
             OR MAX(CASE WHEN f.standard_account = 'interest_expense'  THEN f.amount END) IS NULL
             OR MAX(CASE WHEN f.standard_account = 'short_term_debt'   THEN f.amount END) IS NULL
             OR MAX(CASE WHEN f.standard_account = 'long_term_debt'    THEN f.amount END) IS NULL
            )                                       AS has_null_input,

            ARRAY_REMOVE(ARRAY[
                CASE WHEN MAX(CASE WHEN f.standard_account = 'operating_income'  THEN f.amount END) IS NULL THEN 'operating_income'  END,
                CASE WHEN MAX(CASE WHEN f.standard_account = 'interest_expense'  THEN f.amount END) IS NULL THEN 'interest_expense'  END,
                CASE WHEN MAX(CASE WHEN f.standard_account = 'short_term_debt'   THEN f.amount END) IS NULL THEN 'short_term_debt'   END,
                CASE WHEN MAX(CASE WHEN f.standard_account = 'long_term_debt'    THEN f.amount END) IS NULL THEN 'long_term_debt'    END,
                CASE WHEN MAX(CASE WHEN f.standard_account = 'bonds_payable'     THEN f.amount END) IS NULL THEN 'bonds_payable'     END,
                CASE WHEN MAX(CASE WHEN f.standard_account = 'current_ltd'       THEN f.amount END) IS NULL THEN 'current_ltd'       END
            ], NULL)                                AS null_fields,

            NOW()                                   AS refreshed_at

        FROM core.financial_statement  f
        JOIN core.company             c ON c.corp_code = f.corp_code
        JOIN core.annual_interest_rate r ON r.fiscal_year = f.fiscal_year
        GROUP BY f.corp_code, c.corp_name, f.fiscal_year, r.base_rate, r.rate_date

        ON CONFLICT (corp_code, fiscal_year, rate_scenario_pct)
        DO UPDATE SET
            base_rate                   = EXCLUDED.base_rate,
            rate_date                   = EXCLUDED.rate_date,
            operating_income            = EXCLUDED.operating_income,
            interest_expense            = EXCLUDED.interest_expense,
            short_term_debt             = EXCLUDED.short_term_debt,
            long_term_debt              = EXCLUDED.long_term_debt,
            bonds_payable               = EXCLUDED.bonds_payable,
            current_ltd                 = EXCLUDED.current_ltd,
            total_debt                  = EXCLUDED.total_debt,
            additional_interest_lower   = EXCLUDED.additional_interest_lower,
            additional_interest_upper   = EXCLUDED.additional_interest_upper,
            icr_current                 = EXCLUDED.icr_current,
            icr_scenario_lower          = EXCLUDED.icr_scenario_lower,
            icr_scenario_upper          = EXCLUDED.icr_scenario_upper,
            icr_grade_current           = EXCLUDED.icr_grade_current,
            has_null_input              = EXCLUDED.has_null_input,
            null_fields                 = EXCLUDED.null_fields,
            refreshed_at                = NOW();

        -- ICR 등급 후처리 UPDATE (lower, upper)
        UPDATE mart.stress_analysis s
        SET
            icr_grade_lower = mart.classify_icr_grade(s.icr_scenario_lower),
            icr_grade_upper = mart.classify_icr_grade(s.icr_scenario_upper)
        WHERE s.rate_scenario_pct = v_scenario
          AND s.refreshed_at >= NOW() - INTERVAL '1 minute';

    END LOOP;

    RAISE NOTICE 'mart.stress_analysis 갱신 완료 (시나리오: %, %, %)', v_scenarios[1], v_scenarios[2], v_scenarios[3];
END;
$$;

COMMENT ON PROCEDURE mart.refresh_stress_analysis IS
'core.financial_statement + core.annual_interest_rate를 JOIN하여
mart.stress_analysis를 3개 시나리오(+0.5/+1.0/+2.0%p)로 UPSERT.
n8n 또는 pg_cron으로 CORE 적재 완료 후 호출.';


-- ──────────────────────────────────────────────────────────────
-- 조회 편의 뷰
-- ──────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW mart.v_stress_summary AS
SELECT
    s.corp_code,
    s.corp_name,
    s.fiscal_year,
    s.base_rate,
    s.scenario_label,
    -- 금액 (억원 단위로 변환)
    ROUND(s.operating_income   / 1e8)  AS 영업이익_억원,
    ROUND(s.interest_expense   / 1e8)  AS 이자비용_억원,
    ROUND(s.short_term_debt    / 1e8)  AS 단기차입금_억원,
    ROUND(s.total_debt         / 1e8)  AS 총차입금_억원,
    -- ICR
    s.icr_current                       AS "현재ICR",
    s.icr_scenario_lower                AS "시나리오ICR_하한",
    s.icr_scenario_upper                AS "시나리오ICR_상한",
    -- 등급
    s.icr_grade_current                 AS "현재등급",
    s.icr_grade_lower                   AS "시나리오등급_하한",
    s.icr_grade_upper                   AS "시나리오등급_상한",
    -- 데이터 품질
    s.has_null_input                    AS "결측값존재",
    s.null_fields                       AS "결측필드목록"
FROM mart.stress_analysis s
ORDER BY s.fiscal_year, s.corp_name, s.rate_scenario_pct;

COMMENT ON VIEW mart.v_stress_summary IS '스트레스 분석 결과 조회 뷰. 금액은 억원 단위로 변환.';
