# 🚗 자동차부품 기업여신 다중위험 Screening (금리 × 환율) 데이터 파이프라인

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL 18](https://img.shields.io/badge/PostgreSQL-18%20(Neon%20DB)-336791.svg?style=flat&logo=postgresql&logoColor=white)](https://neon.tech/)
[![QA Audit](https://img.shields.io/badge/QA%20Audit-100%25%20PASSED-success.svg?style=flat)](scripts/05_run_qa_audit.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **본 프로젝트는 국내 주요 자동차부품 8개사 및 완성차 2개사(총 10개사, 2021~2025 회계연도)를 대상으로, 공공 API(OpenDART, 한국은행 ECOS) 및 사업보고서 주석 데이터를 연계하여 금리 인상 충격과 환율 변동 위험을 결합한 기업여신 다중위험 Screening 데이터 마트를 구축하는 엔터프라이즈 데이터 엔지니어링 파이프라인입니다.**

---

## 📌 목차 (Table of Contents)
1. [프로젝트 개요 및 배경](#1-프로젝트-개요-및-배경)
2. [분석 대상 기업 정의](#2-분석-대상-기업-정의)
3. [엔터프라이즈 데이터 아키텍처](#3-엔터프라이즈-데이터-아키텍처)
4. [데이터 계층별 상세 설계 (RAW → CORE → MART)](#4-데이터-계층별-상세-설계-raw--core--mart)
5. [핵심 데이터 엔지니어링 해결 과제 (Deep-Dive)](#5-핵심-데이터-엔지니어링-해결-과제-deep-dive)
6. [시나리오 및 스크리닝 비즈니스 로직](#6-시나리오-및-스크리닝-비즈니스-로직)
7. [프로젝트 디렉토리 구조](#7-프로젝트-디렉토리-구조)
8. [설치 및 환경 설정 (Quick Start)](#8-설치-및-환경-설정-quick-start)
9. [파이프라인 실행 가이드 (CLI)](#9-파이프라인-실행-가이드-cli)
10. [데이터 품질 감사 (QA Audit)](#10-데이터-품질-감사-qa-audit)
11. [Git 형상관리 및 협업 컨벤션](#11-git-형상관리-및-협업-컨벤션)

---

## 1. 프로젝트 개요 및 배경

국내 자동차 부품업계는 대규모 설비투자로 인한 **차입금 의존도(이자율 변동 위험)**와 글로벌 완성차 및 해외법인 납품에 따른 **외화 결제 비중(환율 변동 위험)**이 공존하는 대표적인 다중위험 노출 업종입니다. 

금융기관의 기업여신 심사 관점에서 단일 지표(이자보상배율 등)만을 평가하는 한계를 극복하기 위해, 본 데이터 파이프라인은:
- **공공 API 원천 데이터 자동 수집**: OpenDART 재무제표 및 한국은행 ECOS 거시경제 지표 시계열 자동화.
- **회계 계정 표준화 및 결측치 복원**: 최신 공시 계정 변경 및 복수 표기에 대응하는 지능형 매핑 마스터 및 회계 항등식 교차 검증 적용.
- **8대 스트레스 시나리오 모델링**: 금리 충격(+0.5%p, +1.0%p, +2.25%p) 및 영업이익 충격(−10%) 복합 스트레스 마트 산출.
- **다중통화 순노출 산출**: USD, EUR 외에 공시된 기타 통화(OTHER 34행)를 전수 분해하여 환율 1% 및 ±10% 변동 시 순영향액 집계.
- **Power BI 실시간 서빙 최적화**: 19개 핵심 심사 지표로 정제된 `v_screening` 뷰를 통해 대시보드 즉시 시각화 지원.

---

## 2. 분석 대상 기업 정의

총 10개사 (부품 8개사 + 완성차 2개사, 2021~2025년 5개년):

| 회사명 | 종목코드 | 관리 corp_code | API 수집 corp_code | 업종 구분 | 표본군(in_sample) | 비고 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **에스엘** | 005850 | `00148045` | `00125521` | 자동차부품 | `TRUE` | DART 공시 제출 법인 코드 이중 매핑 처리 |
| **서연이화** | 200880 | `01036446` | `01036446` | 자동차부품 | `TRUE` | 연결재무제표 CFS 기준 |
| **화신** | 010690 | `00166315` | `00166315` | 자동차부품 | `TRUE` | 유동성사채 단기차입금 편입 |
| **명신산업** | 009900 | `00173078` | `00173078` | 자동차부품 | `TRUE` | 이자지급 유출 음수 부호 ABS() 보정 |
| **SNT모티브** | 064960 | `00398792` | `00398792` | 자동차부품 | `TRUE` | 무차입 경영 기업 예외 규칙(차입금·이자=0) |
| **HL만도** | 204320 | `01042775` | `01042775` | 자동차부품 | `TRUE` | 복합 차입금 및 사채 매핑 |
| **성우하이텍** | 015750 | `00132992` | `00132992` | 자동차부품 | `TRUE` | 2024.03 소급 재작성 반영 정합성 보장 |
| **현대모비스** | 012330 | `00164788` | `00164788` | 자동차부품 | `TRUE` | 통화 미구분 외화합계 공시(TOTAL) 처리 |
| **현대자동차** | 005380 | `00164742` | `00164742` | 완성차 | `FALSE` | 참고군 (부품사 순위 산정 시 제외) |
| **기아** | 000270 | `00106641` | `00106641` | 완성차 | `FALSE` | 참고군 (부품사 순위 산정 시 제외) |

---

## 3. 엔터프라이즈 데이터 아키텍처

```mermaid
flowchart TD
    subgraph EXT ["외부 원천 소스 (External Source)"]
        DART_API["OpenDART API\n• fnlttSinglAcntAll (재무제표)\n• corpCode (고유번호)"]
        ECOS_API["한국은행 ECOS API\n• 722Y001 (기준금리)\n• 731Y001 (원/달러·원/유로)"]
        NOTES["사업보고서 주석 원문\n• 환위험 민감도 공시\n• 이자율 민감도 공시"]
    end

    subgraph RAW ["RAW Layer (불변 원천 저장소)"]
        F_RAW[("public.finance_raw\n(원 단위 미가공 재무데이터)")]
        E_RATE[("public.ecos_rate\n(일별 기준금리 시계열)")]
        E_FX[("public.ecos_fx\n(일별 주요환율 시계열)")]
        FX_IN[("public.fx_risk_input\n(124행 통화별 주석 원천)")]
    end

    subgraph CORE ["CORE Layer (계정 정제 및 표준화)"]
        MAP_MST[("account_mapping_master\n(계정 코드 매핑 룰)")]
        F_STD[("public.finance_standard\n(4대 지표 백만원 단위 표준화\n자본총계 복원 / 무차입 규칙)")]
        SCENARIO[("dim_scenario\n(8대 스트레스 시나리오 정의)")]
        COMPANY[("dim_company\n(10개사 마스터)")]
    end

    subgraph MART ["MART Layer (분석 및 지표 집계)"]
        M_RATE[("public.mart_rate_stress\n(400행 × 23열\n소수점 무손실 NUMERIC)")]
        M_FX[("public.mart_fx_exposure\n(50행 × 37열\ns_net_1pct 통합 노출액)")]
        M_SCR[("public.mart_screening\n(50행 × 19열)")]
        V_SCR[["public.v_screening\n(최종 Screening View)"]]
    end

    subgraph BI ["서빙 및 활용 계층 (Serving Layer)"]
        PBI["Power BI Dashboard\n• 화면 1: 우선순위 산점도\n• 화면 2: Stress ICR & 환율 카드\n• 화면 3: 주석 출처 검증"]
        CSV_EXP["data/*.csv Export\n(팀 공유 및 감사용)"]
    end

    DART_API -->|배치 수집| F_RAW
    ECOS_API -->|시계열 수집| E_RATE & E_FX
    NOTES -->|정제 적재| FX_IN

    F_RAW & MAP_MST --> F_STD
    F_STD & SCENARIO & E_RATE --> M_RATE
    F_STD & FX_IN & E_FX --> M_FX
    M_RATE & M_FX & COMPANY --> M_SCR --> V_SCR

    V_SCR & M_RATE & M_FX --> PBI
    V_SCR & M_RATE & M_FX --> CSV_EXP
```

---

## 4. 데이터 계층별 상세 설계 (RAW → CORE → MART)

### 4.1. RAW 계층
- **`finance_raw`**: OpenDART API 수집 결과 원본. 단위(KRW 원), 계정명, 계정코드, 재무제표 구분(`sj_div`: BS, IS, CIS, CF, SCE)을 100% 원형 보존.
- **`ecos_rate`**: 한국은행 기준금리 일별 시계열 (통계코드 722Y001 / 항목 0101000).
- **`ecos_fx`**: 주요 통화(USD, EUR, JPY) 대원화 일별 매매기준율 (통계코드 731Y001).
- **`fx_risk_input`**: 사업보고서 외환 위험 주석 공시 원천(총 124행). 공시 충격률(`shock_pct`), 상승/하락 영향액(`impact_up`, `impact_down`), 공시 대상(`impact_target`), 출처 문서(`source_doc`)를 백만원 단위로 관리.

### 4.2. CORE 계층
- **`account_mapping_master`**: 기업별 상이한 XBRL 계정명(예: 영업이익, 이자비용, 단기차입금, 유동성사채, 장기차입금, 자본총계)을 표준 계정코드로 매핑하는 룰셋.
- **`finance_standard`**: 기업 × 연도 × 회계기준(CFS/OFS) 단위로 표준화된 4대 핵심 재무지표(백만원 단위):
  - `operating_profit`: 영업이익
  - `interest_expense`: 현금흐름표상 '이자의 지급' (ABS 처리)
  - `short_term_debt`: 단기차입금 + 유동성장기부채 + 유동성사채
  - `debt`: 총차입금 (리스부채 제외)
  - `equity`: 자본총계 (자산-부채 항등식 및 지배+비지배 합산 보정)

### 4.3. MART 계층
- **`mart_rate_stress` (400행 × 23열)**: 10개사 × 5개년 × 8개 시나리오별 금리·영업이익 스트레스 ICR 및 등급 산출 마트.
- **`mart_fx_exposure` (50행 × 37열)**: 10개사 × 5개년 단위의 통화 통합 순노출액(`s_net_1pct`), 상쇄전 총노출액(`s_gross_1pct`), 네팅비율(`netting_ratio`), 자기자본 대비 민감도(`fx_sensitivity_pct`), 부품사 내 상대순위(`rank_in_parts`) 집계.
- **`v_screening` (50행 × 19열)**: 기준 시나리오(`E10_R3`) 기준 기업×연도 1행으로 집약된 최종 스크리닝 뷰.

---

## 5. 핵심 데이터 엔지니어링 해결 과제 (Deep-Dive)

### 💡 1. 에스엘(SL) DART 공시 코드 이중화 및 소멸법인 영구 정제
- **문제**: OpenDART API 수집 시 프로젝트 관리 코드인 `00148045`로 호출하면 `status: 013 (조회된 데이터 없음)` 에러가 발생하여 재무 데이터가 전수 누락됨.
- **원인 규명**: OpenDART의 공시 제출 마스터(`corpCode.xml`) 분석 결과, 현재 실제 공시를 제출하는 유효 존속법인 코드는 **`00125521`**(종목 005850)이고, `00148045`는 과거 상호(삼립산업) 등록 코드이며, `00561866`은 피흡수합병된 소멸법인(에스엘라이팅) 코드임을 밝혀냄.
- **해결**: API 수집 스크립트(`dart_collector.py`)에서 `00125521`로 5개년 2,586건을 정상 수집하고, DB 적재 파이프라인에서 분석 표준 코드인 `00148045`로 매핑하여 적재. `dim_company`에서 소멸법인(`00561866`)을 완전 삭제하고 `00148045`를 `in_sample=True`로 확정.

### 💡 2. 최신 자본총계(`equity`) 결측치 복원 (회계 항등식 적용)
- **문제**: 기아, 명신산업, 서연이화, 성우하이텍, 현대모비스 등 9개 기업의 2023~2025년 자본총계가 `NULL`이거나 자본금(`1,560,650백만원`)으로 오매핑됨.
- **원인 규명**: 최신 공시 서식에서 `ifrs-full_Equity` 대신 DART 전용 계정인 `dart_TotalEquity`가 사용되었고, 자본변동표(SCE)의 자본금 항목이 필터 없이 유입됨.
- **해결**: 재무상태표(`sj_div = 'BS'`) 우선 필터 및 회계 기본 항등식인 **`자본총계 = 자산총계 - 부채총계`**를 파이프라인에 구축하여 50개 기업-연도 전수 결측치 0건 달성.

### 💡 3. 유동성사채 편입 및 SNT모티브 무차입 비즈니스 규칙 반영
- **문제**: 화신·HL만도의 차입금이 누락되고, SNT모티브는 차입금과 이자가 비정상 집계됨.
- **원인 규명**: 1년 이내 만기도래 사채인 `dart_CurrentPortionOfBonds`가 단기차입금 매핑에서 빠져 있었음. SNT모티브는 실제 무차입 경영 기업으로 BS에 차입금 계정이 없음.
- **해결**: 유동성사채 계정을 매핑 마스터에 전면 편입. SNT모티브는 `debt=0, short_term_debt=0, interest_expense=0, review_note='무차입'` 규칙 적용. 현금흐름표 이자지급 유출 음수 표기는 `ABS()`로 양수 통일.

### 💡 4. 성우하이텍 2021·2022 영업이익 공시 이력 및 소급 재작성 추적
- **문제**: OpenDART API 수집값과 분석가 사업보고서 수치 간에 각각 −1.7%, −3.5% 차이가 발생함.
- **원인 규명**: DART API의 원본 접수보고서 번호 추적 결과, 2021년 본보고서(`20220322000858`, 76,353.91백만원)와 2022년 본보고서(`20230322000912`, 99,182.73백만원)의 당초 제출값을 가져온 것임. 이후 성우하이텍은 2024.03 사업보고서에서 과거 회계 오류를 **소급 재작성(Restatement)** 하였음(2021: 77,648.47백만원, 2022: 102,793.65백만원).
- **해결**: 원본 공시 이력을 완벽히 규명하고, 분석 정합성을 위해 최신 2024.03 보고서 기준 소급 재작성 수치로 마트 동기화 완료.

### 💡 5. 마트 금액 컬럼의 소수점 무손실 임의 정밀도(`NUMERIC`) 전면 개편
- **문제**: 마트 금액이 정수로 반올림되어 SNT모티브 2021년 ICR 재계산 시 오차(`2,824.6` vs `2,862.3`) 발생.
- **해결**: `mart_rate_stress` 및 `mart_fx_exposure`의 모든 금액 컬럼을 정수형에서 임의 정밀도 `NUMERIC`으로 변경하여 소수점 6자리까지 완벽 보존, DB 쿼리 재계산 오차 0 달성.

### 💡 6. 외환 공시 주석 124행 전수 복원 및 백만원 단위 통일
- **문제**: 원천 테이블 `fx_risk_input`에 기타 통화가 누락(90행)되어 마트의 `s_net_1pct`와 차이가 발생하고, 금액 단위가 원 단위로 들어감.
- **해결**: 공시 전체 합계에서 USD·EUR를 차감한 `OTHER` 통화 34행과 현대모비스 전체 합계 5행을 복원하여 **총 124행**(USD 45, EUR 40, OTHER 34, TOTAL 5) 백만원 단위 적재 완료. 원천 표에서 재계산한 `s_net_1pct`와 마트 값 간 오차 0 검증.

---

## 6. 시나리오 및 스크리닝 비즈니스 로직

### 6.1. 8대 스트레스 시나리오 (`dim_scenario`)
1. **`CURRENT`**: 현재 금리 및 영업이익 유지 (Base, rate_shock=0.0%, op_shock=0.0%)
2. **`R1`**: 결산 이후 실제 금리 인상분 반영 (rate_shock=+0.5%p, op_shock=0.0%)
3. **`R2`**: 기업 공시 기준 100bp 충격 (rate_shock=+1.0%p, op_shock=0.0%)
4. **`R3`**: 2022년 최대 인상폭 및 BCBS 원화 기준 (rate_shock=+2.25%p, op_shock=0.0%)
5. **`E10`**: 자동차 수요 둔화 영업이익 충격 (rate_shock=0.0%, op_shock=−10.0%)
6. **`E10_R1`**: 복합 충격 (rate_shock=+0.5%p, op_shock=−10.0%)
7. **`E10_R2`**: 복합 충격 (rate_shock=+1.0%p, op_shock=−10.0%)
8. **`E10_R3`**: **[기준 시나리오]** 복합 최대 충격 (rate_shock=+2.25%p, op_shock=−10.0%)

### 6.2. Screening 판정 규칙 (`v_screening`)
- **`P1` (최우선 관리)**: 기준 시나리오 Stress ICR(`E10_R3`) < 1.0배
- **`P2` (관찰/선제 대응)**: P1 아님 AND (Stress ICR 1.0~1.5배 또는 `icr_drop_pct_R3` ≥ 35%) AND `fx_sensitivity_pct` ≥ 0.15%
- **`P3` (일반 관리)**: 나머지 ICR 산출 가능 기업
- **`산출제외`**: SNT모티브 등 무차입 기업 (ICR 산출 불가)
- **`참고`**: 현대자동차, 기아 (완성차 참고 기업)

---

## 7. 프로젝트 디렉토리 구조

```text
dockerSQL/
├── api_collector.py          # [단독 실행] OpenDART & ECOS API 수집 모듈
├── auto_credit_pipeline.py   # [단독 실행] 전체 파이프라인 올인원 실행기
├── requirements.txt          # Python 의존성 라이브러리 목록
├── .env.example              # 환경변수 템플릿
├── .gitignore                # Git 제외 설정
├── README.md                 # 본 프로젝트 문서
│
├── config/                   # 환경 설정 및 DB 커넥션 모듈
│   ├── __init__.py
│   └── db.py                 # PostgreSQL/Neon 연결 풀 및 이벤트 로깅
│
├── src/                      # 파이프라인 패키지
│   ├── collectors/           # OpenDART 및 ECOS 수집 모듈
│   ├── processors/           # finance_core, fx_processor, rate_stress 모듈
│   └── qa/                   # quality_audit 모듈
│
├── scripts/                  # CLI 실행 스크립트 모음
│   ├── 01_test_connection.py # 연결 상태 점검
│   ├── 02_collect_api_data.py# API 수집
│   ├── 03_transform_core.py  # 회계 표준화
│   ├── 04_build_marts.py     # 마트 빌드 & CSV 저장
│   ├── 05_run_qa_audit.py    # QA 감사
│   └── run_pipeline.py       # 마스터 실행기
│
├── sql/                      # DDL & 쿼리 스크립트
└── data/                     # 최종 산출물 CSV (v_screening, mart_rate_stress 등)
```

---

## 8. 설치 및 환경 설정 (Quick Start)

### 1) Python 환경 구성
```bash
python -m venv venv
# Windows
.\venv\Scripts\Activate.ps1
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2) 환경변수 파일 (`.env`) 설정
`.env.example`을 복사하여 `.env`를 생성하고 실제 키를 입력합니다:
```bash
cp .env.example .env
```
```env
DART_API_KEY=your_opendart_api_key_here
ECOS_API_KEY=your_ecos_api_key_here
DATABASE_URL=postgresql://neondb_owner:your_password@ep-round-recipe-b4nrp8vt-pooler.c-6.us-east-1.aws.neon.tech/dart_ecos?sslmode=require
```

---

## 9. 파이프라인 실행 가이드 (CLI)

### 📌 단독 스크립트 실행
- **API 수집만 실행할 때**:
  ```bash
  python api_collector.py
  ```
- **전체 파이프라인을 올인원으로 실행할 때**:
  ```bash
  python auto_credit_pipeline.py
  ```

### 📌 단계별 모듈러 실행
```bash
python scripts/01_test_connection.py   # 연결 점검
python scripts/02_collect_api_data.py  # API 데이터 수집
python scripts/03_transform_core.py    # 회계 표준화
python scripts/04_build_marts.py       # 마트 빌드
python scripts/05_run_qa_audit.py      # 품질 감사
```

---

## 10. 데이터 품질 감사 (QA Audit)

`python scripts/05_run_qa_audit.py` 실행 결과:

```text
======================================================================
 [QA] 데이터 엔지니어링 품질 및 무결성 전수 감사
======================================================================
1. 대상 10개사 재무 수집 여부: PASS (10/10개사 전수 수집 완료)
2. 자기자본(equity) 결측치: PASS (결측: 0건, 100% 복원 완료)
3. fx_risk_input 124행 적재: PASS (124행, 단위: 백만원, s_net 오차 0)
4. mart_rate_stress 400행 및 8대 시나리오: PASS (400행 × 23열, 소수점 보존)
5. v_screening 50행 검증: PASS (50행 × 19열 최신 규칙 준수)
----------------------------------------------------------------------
 [QA 최종 판정] ALL PASSED (100% 무결성 검증 완료)
======================================================================
```

---

## 11. Git 형상관리 및 협업 컨벤션

- **보안 원칙**: 실제 API Key와 DB 비밀번호가 담긴 `.env` 파일 및 임시 디버그 덤프(`*_debug.txt`, `*_dump.txt`)는 `.gitignore`에 의해 커밋에서 영구 배제됩니다.
- **브랜치 전략**:
  - `main`: 상시 배포 가능한 검증된 안정 버전
  - `feature/*`: 신규 수집원 또는 계산 지표 추가
  - `fix/*`: 계정 매핑 및 비즈니스 예외 수정
- **커밋 메시지 규칙**:
  - `feat`: 신규 기능/모듈 추가
  - `fix`: 버그 수정 (계정 오매핑, 결측치 보정 등)
  - `docs`: 문서 수정 (README.md 등)
  - `refactor`: 코드 리팩토링 및 모듈화

---

**데이터 엔지니어링 담당**: 김인애 (C)  
**문의 및 피드백**: GitHub Issue 또는 팀 채널
