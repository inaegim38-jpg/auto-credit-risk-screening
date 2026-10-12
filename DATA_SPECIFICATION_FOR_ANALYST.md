# [인계 문서] 금융 리스크 분석 프로젝트 - 데이터 파이프라인 명세서

> **작성자**: 김인애 (데이터 엔지니어링 담당자 C)  
> **수신자**: 최희지 (금리·환율 리스크 분석 담당자 B), 정우준 (기획·검증 담당자 A), 강미 (BI·리포팅 담당자 D)  
> **데이터베이스**: PostgreSQL 17 (`finance_lab` / `Host: localhost:5432`)

---

## 1. 개요 및 도메인 원칙

본 문서는 김인애(C)가 OpenDART API, ECOS API, K-IFRS 1107 외환 민감도 공시 입력표로부터 수집·정제·표준화하여 PostgreSQL 데이터베이스에 적재 완료한 데이터셋의 명세서입니다.

### 도메인 간 상호 규칙 (팀 협업 원칙)
1. **API 직접 호출 배제**: 분석 담당자(B)는 외부 API(DART/ECOS)를 직접 호출하지 않고, 오직 본 PostgreSQL DB에 적재된 표준화 테이블만 조회하여 분석합니다.
2. **원천 데이터 불변 원칙**: 분석 단계에서 원천 수치나 표준화 수치를 직접 수정하지 않습니다.
3. **금리와 환율 분리**: 금리 위험(영업손익·이자보상배율 단계)과 환율 위험(세전손익·자기자본 단계)은 손익 반영 단계가 다르므로 두 결과를 하나로 합산하지 않습니다.
4. **결측값(NULL) 원형 보존**: 데이터가 없는 실측 결측값은 `0`으로 치환하지 않고 `NULL`로 유지되어 있습니다. 필수 값이 누락된 경우 임의 계산을 지양하고 **'판정 불가'**로 처리합니다.

---

## 2. 테이블 구성 요약 (전체 5대 핵심 테이블)

| 테이블명 | Grain (기본 단위) | 총 행수 | 설명 |
|---|---|---:|---|
| `public.finance_standard` | 기업 × 연도 × 기간 × 재무제표 | 15행 | **[최우선 활용]** 분석가 투입용 4대 표준 재무 지표 |
| `public.fx_risk_input` | 기업 × 연도 × 통화 | 27행 | **[환위험 분석용]** K-IFRS 1107 공시 외환 민감도 입력값 |
| `public.ecos_rate` | 날짜 × 지표명 | 2,557행 | **[금리 분석용]** 한국은행 기준금리 시계열 (일별/기간말) |
| `public.ecos_fx` | 날짜 × 통화 | 2,226행 | **[환율 분석용]** 주요 통화(USD, EUR, JPY) 일별 매매기준율 |
| `public.finance_raw` | 기업 × 연도 × 보고서 × 계정 | 3,100행 | OpenDART 원천 계정 데이터 (감사 및 원형 추적용) |

---

## 3. 핵심 테이블 상세 명세

### 3.1. `public.finance_standard` (표준화 재무 데이터)
- **목적**: 금리 위험(Stress ICR) 및 환율 위험(자기자본 대비 영향액)의 분모/분자 기초 데이터
- **PK**: `id` | **Unique**: `(corp_code, fiscal_year, period, fs_div)`

| 컬럼명 | 데이터 타입 | Nullable | 설명 및 정의 |
|---|---|:---:|---|
| `corp_code` | CHAR(8) | N | DART 8자리 기업 고유번호 (예: `00126380`) |
| `company_name` | TEXT | N | 기업명 (삼성전자, 현대자동차, LG전자, POSCO홀딩스, SK하이닉스) |
| `fiscal_year` | CHAR(4) | N | 사업연도 (2021, 2022, 2023) |
| `period` | VARCHAR(10) | N | 기간 구분 (`FY`=연간, 향후 TTM 계산을 위한 원천 Grain 보존) |
| `fs_div` | VARCHAR(5) | N | 재무제표 구분 (`CFS`=연결재무제표) |
| **`operating_profit`** | NUMERIC(25, 0) | Y | **영업이익** (적자/손실 시 음수 유지) |
| **`interest_expense`** | NUMERIC(25, 0) | Y | **이자비용** (손익계산서 이자비용 우선 → 현금흐름표 이자의 지급 순) |
| **`debt`** | NUMERIC(25, 0) | Y | **총차입금** = 단기차입금 + 유동성장기부채 + 장기차입금 + 사채 (리스부채 제외) |
| **`short_term_debt`** | NUMERIC(25, 0) | Y | **단기차입금** = 단기차입금 + 유동성장기부채 |
| **`equity`** | NUMERIC(25, 0) | Y | **자기자본** = 자본총계 (환위험의 '자기자본 대비 영향액' 계산용) |
| `mapping_status` | VARCHAR(20) | N | 매핑 상태 (`mapped`=정상, `review_required`=검토필요) |

---

### 3.2. `public.fx_risk_input` (환위험 입력 데이터)
- **목적**: K-IFRS 1107(금융상품 위험관리 주석) 외화 금융자산·부채 환산 민감도 원천 입력치
- **PK**: `id` | **Unique**: `(corp_code, fiscal_year, currency)`

| 컬럼명 | 데이터 타입 | Nullable | 설명 및 정의 |
|---|---|:---:|---|
| `corp_code` | CHAR(8) | N | DART 8자리 기업 고유번호 |
| `company_name` | TEXT | N | 기업명 |
| `fiscal_year` | CHAR(4) | N | 사업연도 |
| `currency` | VARCHAR(10) | N | 통화 코드 (`USD`, `EUR`, `JPY`) |
| **`risk_input`** | NUMERIC(25, 0) | Y | **공시 민감도 영향액** (원화 환산액, 기준 충격률 5% 변동 시 세전손익 영향액) |
| `note` | TEXT | Y | 비고 (기준 변동폭, 주석 번호 등 감사 메타데이터) |
| `checked_at` | TIMESTAMPTZ | N | 확인일시 |

> **최희지(B) 환율 분석 공식 권장 가이드**
> - **1%당 영향액** = `risk_input` ÷ 5 (공시 기준 충격률 5% 가정 제거)
> - **자기자본 대비 영향액 (%)** = (1%당 영향액 ÷ `finance_standard.equity`) × 100

---

### 3.3. `public.ecos_rate` (기준금리 시계열) & `public.ecos_fx` (환율 시계열)
- **`ecos_rate` PK**: `id` | **Unique**: `(date, indicator)`
  - `date`: 기준일자 (`DATE`)
  - `rate`: 한국은행 기준금리 (연%, `NUMERIC(8, 4)`)
- **`ecos_fx` PK**: `id` | **Unique**: `(date, currency)`
  - `date`: 기준일자 (`DATE`)
  - `currency`: 통화 (`USD`, `EUR`, `JPY`)
  - `exchange_rate`: 매매기준율 (`NUMERIC(12, 4)`)

---

## 4. 분석 담당자(B)용 표준 조인 가이드 쿼리

### [분석 1: 금리 위험 분석 기초 데이터셋 조회]
DART 재무제표와 ECOS 연말 기준금리를 결합하는 표준 쿼리입니다 (일별 데이터 폭발 방지 Grain 맞춤).

```sql
WITH year_end_rate AS (
    SELECT 
        EXTRACT(YEAR FROM date)::INT AS fiscal_year,
        rate AS base_rate,
        date AS rate_date,
        ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM date) ORDER BY date DESC) AS rn
    FROM public.ecos_rate
    WHERE indicator = '한국은행 기준금리'
)
SELECT 
    s.corp_code,
    s.company_name,
    s.fiscal_year,
    s.operating_profit,
    s.interest_expense,
    s.short_term_debt,
    s.debt AS total_debt,
    r.base_rate AS year_end_base_rate,
    r.rate_date
FROM public.finance_standard s
LEFT JOIN year_end_rate r 
       ON r.fiscal_year = s.fiscal_year::INT AND r.rn = 1
ORDER BY s.company_name, s.fiscal_year;
```

---

### [분석 2: 환율 위험 분석 기초 데이터셋 조회]
환위험 공시 입력치와 자기자본(`equity`), 연말 기준환율을 1:1로 결합하는 표준 쿼리입니다.

```sql
WITH year_end_fx AS (
    SELECT 
        EXTRACT(YEAR FROM date)::INT AS fiscal_year,
        currency,
        exchange_rate AS year_end_fx,
        date AS fx_date,
        ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM date), currency ORDER BY date DESC) AS rn
    FROM public.ecos_fx
)
SELECT 
    f.company_name,
    f.corp_code,
    f.fiscal_year,
    f.currency,
    f.risk_input AS fx_risk_input,     -- 5% 변동 시 공시 영향액
    s.equity AS total_equity,           -- 자기자본 (규모 차이 제거용 분모)
    x.year_end_fx,
    f.note
FROM public.fx_risk_input f
JOIN public.finance_standard s
  ON s.corp_code = f.corp_code 
 AND s.fiscal_year = f.fiscal_year
LEFT JOIN year_end_fx x
       ON x.fiscal_year = f.fiscal_year::INT 
      AND x.currency = f.currency 
      AND x.rn = 1
ORDER BY f.company_name, f.fiscal_year, f.currency;
```

---

## 5. DBeaver 및 데이터베이스 접속 정보

- **Host**: `localhost` (또는 `127.0.0.1`)
- **Port**: `5432`
- **Database**: `finance_lab`
- **Username**: `lab_admin`
- **Password**: `lab_admin_2026`
- **n8n Automation Web UI**: `http://localhost:5678`
- **CloudBeaver Web UI**: `http://localhost:8978`
