-- ============================================================
-- CORE 초기 데이터: account_mapping 시드 데이터
-- 실제 DART API 조회 결과 기반 (5개 기업 검증 완료)
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- 1. operating_income (영업이익)
-- → 5개 기업 모두 dart_OperatingIncomeLoss 로 통일 매핑 가능
-- ──────────────────────────────────────────────────────────────
INSERT INTO core.account_mapping
    (source_account_id, source_account_nm, source_sj_nm,
     standard_account, priority, is_total_debt_component, notes)
VALUES
-- 삼성전자/현대차: 손익계산서, 계정명 '영업이익'
('dart_OperatingIncomeLoss', '영업이익', '손익계산서',
 'operating_income', 1, FALSE, '삼성전자·현대차 공통. sj_nm=손익계산서'),

-- SK하이닉스/POSCO: 포괄손익계산서, 계정명 '영업이익'
('dart_OperatingIncomeLoss', '영업이익', '포괄손익계산서',
 'operating_income', 1, FALSE, 'SK하이닉스·POSCO홀딩스. sj_nm=포괄손익계산서'),

-- LG전자: 손익계산서, 계정명 '영업이익(손실)'
('dart_OperatingIncomeLoss', '영업이익(손실)', '손익계산서',
 'operating_income', 1, FALSE, 'LG전자. 손실 연도에도 동일 account_id 사용'),

-- SK하이닉스 적자 연도: '영업이익(손실)' + 포괄손익
('dart_OperatingIncomeLoss', '영업이익(손실)', '포괄손익계산서',
 'operating_income', 1, FALSE, 'SK하이닉스 적자 연도 fallback')

ON CONFLICT (source_account_id, source_account_nm, source_sj_nm) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 2. interest_expense (이자비용)
-- → 현금흐름표 '이자의 지급' 우선 (priority=1)
--   손익계산서 '금융비용'은 보조 (priority=2)
--   ※ 금융비용은 이자 외 비용 포함 가능 (환율 손실 등)
-- ──────────────────────────────────────────────────────────────
INSERT INTO core.account_mapping
    (source_account_id, source_account_nm, source_sj_nm,
     standard_account, priority, is_total_debt_component, notes)
VALUES
-- 【우선순위 1】 현금흐름표 이자의 지급 (5개사 공통)
('ifrs-full_InterestPaidClassifiedAsOperatingActivities', '이자의 지급', '현금흐름표',
 'interest_expense', 1, FALSE, '5개사 공통. 현금 기준 이자지급. priority=1 최우선'),

-- POSCO홀딩스는 '이자지급'(공백 없음)으로 기재
('ifrs-full_InterestPaidClassifiedAsOperatingActivities', '이자지급', '현금흐름표',
 'interest_expense', 1, FALSE, 'POSCO홀딩스. 계정명 표기 차이만 있음'),

-- 【우선순위 2】 손익계산서 금융비용 (이자 외 비용 포함 가능 → 보조)
('ifrs-full_FinanceCosts', '금융비용', '손익계산서',
 'interest_expense', 2, FALSE, '이자 외 비용 포함 가능. 현금흐름표 이자지급 없을 때 fallback'),

('ifrs-full_FinanceCosts', '금융비용', '포괄손익계산서',
 'interest_expense', 2, FALSE, 'POSCO·SK하이닉스. 포괄손익계산서 기재'),

-- 삼성전자 금융비용 (표준계정코드 미사용)
('-표준계정코드 미사용-', '금융비용', '손익계산서',
 'interest_expense', 2, FALSE, '삼성전자 금융비용. account_id 미표준화. account_nm 기반 매핑 필요')

ON CONFLICT (source_account_id, source_account_nm, source_sj_nm) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 3. short_term_debt (단기차입금)
-- → 총차입금 합산 대상 (is_total_debt_component = TRUE)
-- ──────────────────────────────────────────────────────────────
INSERT INTO core.account_mapping
    (source_account_id, source_account_nm, source_sj_nm,
     standard_account, priority, is_total_debt_component, notes)
VALUES
-- 표준코드 사용 (삼성전자 2021~22, SK하이닉스, LG전자 일부, 현대차)
('ifrs-full_ShorttermBorrowings', '단기차입금', '재무상태표',
 'short_term_debt', 1, TRUE, '단기차입금 표준. 삼성2021~22·현대차'),

-- SK하이닉스: 계정명 '차입금'으로 기재
('ifrs-full_ShorttermBorrowings', '차입금', '재무상태표',
 'short_term_debt', 1, TRUE, 'SK하이닉스. 계정명 차이만 있음'),

-- 삼성전자 2023년: 표준코드 미사용
('-표준계정코드 미사용-', '단기차입금', '재무상태표',
 'short_term_debt', 1, TRUE, '삼성전자 2023년. account_id 비표준화. account_nm 기반 매핑'),

-- LG전자·POSCO: 유동성 포함 합산 코드 (차입금 총계)
('ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings', '차입금', '재무상태표',
 'short_term_debt', 2, TRUE,
 'LG전자·POSCO 일부. 단기차입금+유동성장기부채 합산값일 수 있으므로 priority=2')

ON CONFLICT (source_account_id, source_account_nm, source_sj_nm) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 4. current_ltd (유동성장기부채)
-- → 총차입금 합산 대상
-- ──────────────────────────────────────────────────────────────
INSERT INTO core.account_mapping
    (source_account_id, source_account_nm, source_sj_nm,
     standard_account, priority, is_total_debt_component, notes)
VALUES
('ifrs-full_CurrentPortionOfLongtermBorrowings', '유동성장기부채', '재무상태표',
 'current_ltd', 1, TRUE, '삼성전자·현대차. 표준코드 사용'),

('-표준계정코드 미사용-', '유동성장기부채', '재무상태표',
 'current_ltd', 1, TRUE, '삼성전자 일부 연도. account_nm 기반 매핑')

ON CONFLICT (source_account_id, source_account_nm, source_sj_nm) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 5. bonds_payable (사채)
-- → 총차입금 합산 대상
-- ──────────────────────────────────────────────────────────────
INSERT INTO core.account_mapping
    (source_account_id, source_account_nm, source_sj_nm,
     standard_account, priority, is_total_debt_component, notes)
VALUES
('dart_BondsIssued', '사채', '재무상태표',
 'bonds_payable', 1, TRUE, '삼성전자·현대차. DART 표준코드'),

('ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued', '사채', '재무상태표',
 'bonds_payable', 1, TRUE, '삼성전자 2023년. IFRS 비유동 사채')

ON CONFLICT (source_account_id, source_account_nm, source_sj_nm) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 6. long_term_debt (장기차입금)
-- → 총차입금 합산 대상
-- ──────────────────────────────────────────────────────────────
INSERT INTO core.account_mapping
    (source_account_id, source_account_nm, source_sj_nm,
     standard_account, priority, is_total_debt_component, notes)
VALUES
('dart_LongTermBorrowingsGross', '장기차입금', '재무상태표',
 'long_term_debt', 1, TRUE, '삼성전자·LG전자·현대차. DART 표준코드'),

('ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived', '장기차입금', '재무상태표',
 'long_term_debt', 1, TRUE, '삼성전자 2023년'),

('-표준계정코드 미사용-', '장기차입금', '재무상태표',
 'long_term_debt', 1, TRUE, 'POSCO홀딩스. account_id 비표준화')

ON CONFLICT (source_account_id, source_account_nm, source_sj_nm) DO NOTHING;


-- ──────────────────────────────────────────────────────────────
-- 검증 쿼리: 삽입 결과 확인
-- ──────────────────────────────────────────────────────────────
SELECT
    standard_account,
    COUNT(*)            AS mapping_count,
    MIN(priority)       AS min_priority,
    MAX(priority)       AS max_priority,
    SUM(CASE WHEN is_total_debt_component THEN 1 ELSE 0 END) AS total_debt_components
FROM core.account_mapping
GROUP BY standard_account
ORDER BY standard_account;
