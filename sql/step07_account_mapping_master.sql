-- ============================================================
-- STEP 7: 김인애(C) 계정 매핑 마스터 테이블 정의 및 데이터 등록
--
-- 목표:
--   원천 DART 계정명 → 4대 표준 계정 (operating_profit, interest_expense, debt, equity) 매핑
--
-- 상태값:
--   - mapped: 1:1 또는 표준 합산으로 매핑 확정
--   - review_required: 계정명 비표준, 확인 필요
--   - unmapped: 매핑 제외/미지정
-- ============================================================

CREATE TABLE IF NOT EXISTS public.account_mapping_master (
    id                  SERIAL          PRIMARY KEY,
    standard_account    VARCHAR(30)     NOT NULL,   -- operating_profit, interest_expense, short_term_debt, long_term_debt, bonds_payable, current_ltd, equity
    target_korean_name  TEXT            NOT NULL,   -- 표준 한글명 (영업이익, 이자비용, 단기차입금, 장기차입금, 사채, 유동성장기부채, 자기자본)
    source_sj_nm        TEXT            NOT NULL,   -- 재무상태표, 손익계산서, 포괄손익계산서, 현금흐름표
    source_account_id   TEXT            NOT NULL,   -- DART/IFRS 원본 계정코드
    source_account_nm   TEXT            NOT NULL,   -- DART 원본 계정명
    priority            SMALLINT        NOT NULL DEFAULT 1, -- 우선순위 (1=최우선, 2=보조)
    mapping_status      VARCHAR(20)     NOT NULL DEFAULT 'mapped', -- mapped, review_required, unmapped
    notes               TEXT,
    
    CONSTRAINT uq_account_mapping_master UNIQUE (standard_account, source_sj_nm, source_account_id, source_account_nm)
);

-- 기존 데이터 갱신을 위해 멱등성 유지 삽입
INSERT INTO public.account_mapping_master 
    (standard_account, target_korean_name, source_sj_nm, source_account_id, source_account_nm, priority, mapping_status, notes)
VALUES
-- ──────────────────────────────────────────────────────────────
-- 1. operating_profit (영업이익)
-- ──────────────────────────────────────────────────────────────
('operating_profit', '영업이익', '손익계산서', 'dart_OperatingIncomeLoss', '영업이익', 1, 'mapped', '삼성전자, 현대차, LG전자 손익계산서 표준'),
('operating_profit', '영업이익', '손익계산서', 'dart_OperatingIncomeLoss', '영업이익(손실)', 1, 'mapped', 'LG전자 손실 연도 대비'),
('operating_profit', '영업이익', '포괄손익계산서', 'dart_OperatingIncomeLoss', '영업이익', 1, 'mapped', 'SK하이닉스, POSCO홀딩스 포괄손익계산서 표준'),
('operating_profit', '영업이익', '포괄손익계산서', 'dart_OperatingIncomeLoss', '영업이익(손실)', 1, 'mapped', 'SK하이닉스 적자 연도 대비'),

-- ──────────────────────────────────────────────────────────────
-- 2. interest_expense (이자비용)
-- 용어사전: 손익계산서 이자비용 우선 -> 없으면 현금흐름표 이자의 지급 -> 없으면 판정 불가(NULL)
-- ──────────────────────────────────────────────────────────────
('interest_expense', '이자비용', '손익계산서', 'ifrs-full_InterestExpense', '이자비용', 1, 'mapped', '손익계산서 이자비용 (공시된 경우 최우선)'),
('interest_expense', '이자비용', '포괄손익계산서', 'ifrs-full_InterestExpense', '이자비용', 1, 'mapped', '포괄손익계산서 이자비용 (최우선)'),
('interest_expense', '이자비용', '현금흐름표', 'ifrs-full_InterestPaidClassifiedAsOperatingActivities', '이자의 지급', 2, 'mapped', '5개사 공통 현금흐름표 이자 지급액 (실제 금융비용 유출액)'),
('interest_expense', '이자비용', '현금흐름표', 'ifrs-full_InterestPaidClassifiedAsOperatingActivities', '이자지급', 2, 'mapped', 'POSCO홀딩스 현금흐름표 이자지급'),

-- ──────────────────────────────────────────────────────────────
-- 3. equity (자기자본 = 자본총계)
-- 용어사전: 재무제표 내 자기자본(자본총계)
-- ──────────────────────────────────────────────────────────────
('equity', '자기자본', '재무상태표', 'ifrs-full_Equity', '자본총계', 1, 'mapped', '재무상태표 자본총계 (5개사 전사 동일 코드)'),

-- ──────────────────────────────────────────────────────────────
-- 4. short_term_debt (단기차입금 세부)
-- ──────────────────────────────────────────────────────────────
('short_term_debt', '단기차입금', '재무상태표', 'ifrs-full_ShorttermBorrowings', '단기차입금', 1, 'mapped', '단기차입금 표준코드'),
('short_term_debt', '단기차입금', '재무상태표', 'ifrs-full_ShorttermBorrowings', '차입금', 1, 'mapped', 'SK하이닉스 단기차입금 기재명'),
('short_term_debt', '단기차입금', '재무상태표', '-표준계정코드 미사용-', '단기차입금', 1, 'mapped', '삼성전자 2023년 및 POSCO홀딩스 비표준 코드'),
('short_term_debt', '단기차입금', '재무상태표', 'ifrs-full_CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings', '차입금', 2, 'review_required', '유동차입금+유동성장기차입금 합산 계정 가능성'),

-- ──────────────────────────────────────────────────────────────
-- 5. current_ltd (유동성장기부채)
-- ──────────────────────────────────────────────────────────────
('current_ltd', '유동성장기부채', '재무상태표', 'ifrs-full_CurrentPortionOfLongtermBorrowings', '유동성장기부채', 1, 'mapped', '유동성장기부채 표준코드'),
('current_ltd', '유동성장기부채', '재무상태표', '-표준계정코드 미사용-', '유동성장기부채', 1, 'mapped', '삼성전자 비표준 유동성장기부채'),

-- ──────────────────────────────────────────────────────────────
-- 6. long_term_debt (장기차입금)
-- ──────────────────────────────────────────────────────────────
('long_term_debt', '장기차입금', '재무상태표', 'dart_LongTermBorrowingsGross', '장기차입금', 1, 'mapped', '장기차입금 표준코드'),
('long_term_debt', '장기차입금', '재무상태표', 'ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived', '장기차입금', 1, 'mapped', '장기차입금 IFRS 코드'),
('long_term_debt', '장기차입금', '재무상태표', '-표준계정코드 미사용-', '장기차입금', 1, 'mapped', 'POSCO홀딩스 비표준 장기차입금'),

-- ──────────────────────────────────────────────────────────────
-- 7. bonds_payable (사채)
-- ──────────────────────────────────────────────────────────────
('bonds_payable', '사채', '재무상태표', 'dart_BondsIssued', '사채', 1, 'mapped', '사채 발행액 DART 표준코드'),
('bonds_payable', '사채', '재무상태표', 'ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued', '사채', 1, 'mapped', '비유동 사채 IFRS 표준코드')

ON CONFLICT (standard_account, source_sj_nm, source_account_id, source_account_nm) 
DO UPDATE SET 
    priority = EXCLUDED.priority,
    mapping_status = EXCLUDED.mapping_status,
    notes = EXCLUDED.notes;
