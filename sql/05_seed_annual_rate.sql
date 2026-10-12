-- ============================================================
-- CORE 초기 데이터: annual_interest_rate 시드
-- ECOS API 실측값 기준 (2017~2023 연말 기준금리)
-- ============================================================

INSERT INTO core.annual_interest_rate
    (fiscal_year, base_rate, rate_date, aggregation_method)
VALUES
    (2017, 1.5000, '2017-12-31', 'year_end'),
    (2018, 1.7500, '2018-12-31', 'year_end'),
    (2019, 1.2500, '2019-12-31', 'year_end'),
    (2020, 0.5000, '2020-12-31', 'year_end'),
    (2021, 1.0000, '2021-12-31', 'year_end'),
    (2022, 3.2500, '2022-12-31', 'year_end'),
    (2023, 3.5000, '2023-12-31', 'year_end')
ON CONFLICT (fiscal_year) DO UPDATE
    SET base_rate          = EXCLUDED.base_rate,
        rate_date          = EXCLUDED.rate_date,
        aggregation_method = EXCLUDED.aggregation_method,
        updated_at         = NOW();

-- 확인
SELECT fiscal_year, base_rate, rate_date FROM core.annual_interest_rate ORDER BY fiscal_year;
