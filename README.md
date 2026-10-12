# 🚗 자동차부품 기업여신 다중위험 Screening 데이터 파이프라인

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PostgreSQL 18 / Neon](https://img.shields.io/badge/PostgreSQL-18%20(Neon%20DB)-336791.svg)](https://neon.tech/)
[![Data Pipeline QA](https://img.shields.io/badge/QA%20Audit-100%25%20PASSED-success.svg)]()

> **본 프로젝트는 자동차부품 주요 8개사 및 완성차 2개사(총 10개사, 2021~2025 FY)를 대상으로, 금리 인상 충격과 환율 변동 위험을 결합한 기업여신 다중위험 Screening 데이터 마트를 구축하는 엔터프라이즈 데이터 엔지니어링 파이프라인입니다.**

---

## 📌 목차 (Table of Contents)
1. [프로젝트 개요](#-프로젝트-개요)
2. [시스템 아키텍처 및 데이터 흐름](#-시스템-아키텍처-및-데이터-흐름)
3. [디렉토리 구조 (Repository Layout)](#-디렉토리-구조-repository-layout)
4. [핵심 데이터 엔지니어링 해결 과제](#-핵심-데이터-엔지니어링-해결-과제)
5. [사전 준비 및 환경 설정](#-사전-준비-및-환경-설정)
6. [파이프라인 실행 가이드 (CLI)](#-파이프라인-실행-가이드-cli)
7. [데이터 품질 감사 (QA Audit)](#-데이터-품질-감사-qa-audit)
8. [Git 형상관리 및 협업 컨벤션](#-git-형상관리-및-협업-컨벤션)

---

## 🎯 1. 프로젝트 개요

- **분석 대상**: 총 10개사 (5개년: 2021 ~ 2025)
  - **자동차부품 8개사**: 에스엘, 서연이화, 화신, 명신산업, SNT모티브, HL만도, 성우하이텍, 현대모비스
  - **완성차 참고 2개사**: 현대자동차, 기아 (완성차는 벤치마크 참고군으로 순위 산정 시 분리)
- **핵심 목표**:
  1. **OpenDART** 재무제표 API 및 **한국은행 ECOS** 기준금리·환율 API 자동 수집 파이프라인 구축.
  2. 회계 계정 표준화(`finance_standard`)를 통한 자본총계 결측치 복원, 무차입/유동성사채 정합성 보장.
  3. **8대 스트레스 시나리오**(CURRENT, R1~R3, E10, E10_R1~R3) 기반의 `mart_rate_stress`(400행) 산출.
  4. 124개 공시 통화(USD, EUR, OTHER, TOTAL) 통합 순노출 기반의 `mart_fx_exposure`(50행) 산출.
  5. 최종 19개 지표의 통합 여신 스크리닝 뷰 `v_screening`(50행) 및 Power BI 연동 최적화.

---

## 🏗️ 2. 시스템 아키텍처 및 데이터 흐름

```mermaid
flowchart TD
    subgraph External_API ["외부 공공 API"]
        DART["OpenDART API\n(fnlttSinglAcntAll / corpCode)"]
        ECOS["한국은행 ECOS API\n(722Y001 기준금리 / 731Y001 환율)"]
        NOTE["사업보고서 주석\n(외환·이자율 위험 공시)"]
    end

    subgraph RAW_Layer ["RAW Layer (원본 보존)"]
        F_RAW[("public.finance_raw\n(재무 원본 원단위)")]
        E_RATE[("public.ecos_rate\n(일별 기준금리)")]
        E_FX[("public.ecos_fx\n(일별 주요환율)")]
        FX_IN[("public.fx_risk_input\n(124행 / 백만원 단위)")]
    end

    subgraph CORE_Layer ["CORE Layer (정제 및 표준화)"]
        MAP[("account_mapping_master\n(계정 매핑 마스터)")]
        F_STD[("public.finance_standard\n(4대 지표 표준화 / 자본총계 복원)")]
    end

    subgraph MART_Layer ["MART & VIEW Layer (분석 및 서빙)"]
        M_RATE[("public.mart_rate_stress\n(400행 × 23열 / 소수점 무손실 NUMERIC)")]
        M_FX[("public.mart_fx_exposure\n(50행 × 37열 / s_net_1pct 통합 노출)")]
        V_SCR[("public.v_screening\n(50행 × 19열 / 최신 Screening 규칙)")]
    end

    subgraph Serving ["BI & Application"]
        PBI["Power BI Dashboard\n(Screening 카드 / 산점도 / 민감도 분석)"]
        CSV_OUT["data/*.csv Export\n(팀 공유 및 검산용)"]
    end

    DART --> F_RAW
    ECOS --> E_RATE
    ECOS --> E_FX
    NOTE --> FX_IN

    F_RAW & MAP --> F_STD
    F_STD & E_RATE --> M_RATE
    F_STD & FX_IN & E_FX --> M_FX
    M_RATE & M_FX --> V_SCR

    V_SCR & M_RATE & M_FX --> PBI
    V_SCR & M_RATE & M_FX --> CSV_OUT
```

---

## 📁 3. 디렉토리 구조 (Repository Layout)

```text
dockerSQL/
├── .env.example               # 환경변수 템플릿 (보안: 실제 키 유출 방지)
├── .gitignore                 # Git 추적 제외 목록 (.env, 로그, 대용량 파일 등)
├── requirements.txt           # Python 필수 의존성 패키지
├── docker-compose.yml         # 로컬 개발용 컨테이너 (PostgreSQL 17, CloudBeaver, n8n)
├── README.md                  # 프로젝트 설명 및 매뉴얼
│
├── config/                    # 공통 설정 및 DB 연결
│   ├── __init__.py
│   └── db.py                  # PostgreSQL/Neon 연결 풀 및 이벤트 로거
│
├── src/                       # 메인 모듈 패키지
│   ├── __init__.py
│   ├── collectors/            # API 데이터 수집 모듈
│   │   ├── __init__.py
│   │   ├── dart_collector.py  # OpenDART fnlttSinglAcntAll API 수집 (에스엘 00125521 매핑)
│   │   └── ecos_collector.py  # ECOS 기준금리 및 환율 수집
│   │
│   ├── processors/            # 데이터 정제 및 마트 변환 모듈
│   │   ├── __init__.py
│   │   ├── finance_core.py    # finance_standard 생성 (자본총계 복원, 무차입 등)
│   │   ├── fx_processor.py    # fx_risk_input(124행) 적재 및 mart_fx_exposure 산출
│   │   └── rate_stress.py     # 8개 시나리오별 mart_rate_stress(400행) 및 v_screening 생성
│   │
│   └── qa/                    # 품질 검증 및 감사 모듈
│       ├── __init__.py
│       └── quality_audit.py   # 5대 데이터 품질 및 멱등성 전수 감사
│
├── scripts/                   # CLI 실행 스크립트
│   ├── 01_test_connection.py  # DB 및 API 키 연결 테스트
│   ├── 02_collect_api_data.py # OpenDART 및 ECOS API 수집 실행
│   ├── 03_transform_core.py   # RAW -> finance_standard 표준화 가공
│   ├── 04_build_marts.py      # mart_* 테이블 및 v_screening 빌드
│   ├── 05_run_qa_audit.py     # 품질 감사 (QA Audit) 실행
│   └── run_pipeline.py        # [Master] 전체 파이프라인 원클릭 일괄 실행
│
├── sql/                       # DDL & Schema 스크립트 모음
│   ├── 00_complete_erd_v5_ddl.sql
│   ├── 01_raw_tables.sql
│   ├── 02_core_tables.sql
│   ├── 03_mart_tables.sql
│   └── step07_account_mapping_master.sql
│
└── data/                      # 최종 산출물 CSV 파일
    ├── v_screening.csv        # 50 × 19 (기준 시나리오 E10_R3)
    ├── mart_rate_stress.csv   # 400 × 23 (8대 시나리오)
    ├── mart_fx_exposure.csv   # 50 × 37 (외환 노출 세부)
    └── fx_risk_input.csv      # 124 × 12 (통화별 주석 원천)
```

---

## 💡 4. 핵심 데이터 엔지니어링 해결 과제

1. **에스엘(SL) DART 공시 코드 불일치 해결**:
   - OpenDART 상의 실제 유효 공시 제출 고유번호는 `00125521`(종목 005850)이나, 분석가 표준 관리는 `00148045`로 되어 있어 수집 누락이 발생했던 문제 해결.
   - API는 `00125521`로 전 연도 2,586건을 정상 수집하고, DB 적재 시 `00148045`로 자동 매핑 적재. 소멸법인(`00561866`)은 DB 전수 삭제.
2. **최신 자본총계(`equity`) 대규모 결측치 복원**:
   - 2023~2025년 최신 공시에서 자본총계 계정명이 `dart_TotalEquity`로 변경되거나 자본변동표(자본금) 항목이 오매핑되던 문제를 차단.
   - 재무상태표(`sj_div = 'BS'`) 강제 필터 및 회계 기본 항등식인 `자산총계 - 부채총계`를 적용하여 50개 기업-연도 전수 결측치 0건 달성.
3. **유동성사채 누락 및 SNT모티브 무차입 처리**:
   - 화신·HL만도의 단기사채 만기도래분(`dart_CurrentPortionOfBonds`)을 매핑 마스터에 편입하여 총차입금 누락 정상화.
   - SNT모티브(무차입 기업)는 `debt=0, interest=0, review_note='무차입'`으로 비즈니스 예외 처리.
   - 현금흐름표 이자비용 유출 음수 표기를 `ABS()`로 양수 통일.
4. **마트 금액의 소수점 무손실 임의 정밀도(`NUMERIC`) 저장**:
   - `mart_rate_stress` 금액 컬럼을 정수형에서 임의 정밀도 `NUMERIC`으로 전면 개편하여, SNT모티브 2021년 ICR(`2,824.573`) 등 소수점 단위 지표 재계산 오차 0 달성.
5. **환위험 공시 주석 124행 통화 분리 및 백만원 단위 통일**:
   - 공시 전체 합계에서 USD·EUR를 차감한 `OTHER` 통화 34행과 현대모비스 전체 합계 5행을 포함한 **총 124행**(USD 45, EUR 40, OTHER 34, TOTAL 5) 백만원 단위 적재.
   - 원천 표에서 재계산한 `s_net_1pct`와 마트 값 간의 오차 0 검증 완료.

---

## ⚙️ 5. 사전 준비 및 환경 설정

### 1) Python 환경 준비
```bash
python -m venv venv
# Windows PowerShell
.\venv\Scripts\Activate.ps1
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2) 환경변수 설정 (`.env`)
`.env.example` 파일을 복사하여 `.env`를 생성하고 실제 API 키와 DB 정보를 입력합니다:
```bash
cp .env.example .env
```
```env
DART_API_KEY=your_opendart_api_key
ECOS_API_KEY=your_ecos_api_key
DATABASE_URL=postgresql://neondb_owner:your_password@ep-round-recipe-b4nrp8vt-pooler.c-6.us-east-1.aws.neon.tech/dart_ecos?sslmode=require
```

---

## 🚀 6. 파이프라인 실행 가이드 (CLI)

### 📌 원클릭 전체 실행 (Master Runner)
전체 단계(연결 검증 → API 수집 → 표준화 → 마트 빌드 → QA 감사)를 한 번에 실행합니다:
```bash
python scripts/run_pipeline.py
```

### 📌 단계별 개별 실행
```bash
# 1단계: 연결 및 환경 테스트
python scripts/01_test_connection.py

# 2단계: OpenDART 및 ECOS API 데이터 수집
python scripts/02_collect_api_data.py

# 3단계: Core 계정 표준화 및 자본총계 복원
python scripts/03_transform_core.py

# 4단계: 분석 마트 (Rate Stress & FX Exposure & v_screening) 빌드 및 CSV 내보내기
python scripts/04_build_marts.py

# 5단계: 데이터 품질 및 정합성 전수 감사
python scripts/05_run_qa_audit.py
```

---

## 🔍 7. 데이터 품질 감사 (QA Audit)

`python scripts/05_run_qa_audit.py` 실행 시 다음 5대 규칙을 자동 전수 검증합니다:

| 검증 항목 | 검증 기준 | 결과 |
| :--- | :--- | :---: |
| **1. 10개사 전수 수집** | 10개 대상사 재무 데이터 정상 적재 여부 | **PASS (10/10)** |
| **2. 자기자본 결측치** | 50개 기업-연도 equity NULL = 0건 | **PASS (0건)** |
| **3. fx_risk_input 정합성** | 124행 전수 적재 및 백만원 단위 통일 | **PASS (124행)** |
| **4. mart_rate_stress 규모** | 8개 시나리오 기준 400행 및 소수점 정밀도 보존 | **PASS (400행)** |
| **5. v_screening 산출** | 최신 19개 스펙 기준 50행 뷰 정상 생성 | **PASS (50행)** |
| **종합 판정** | **전체 데이터 품질 100% 무결성** | **ALL PASSED** |

---

## 🐙 8. Git 형상관리 및 협업 컨벤션

### 📌 Git 초기화 및 GitHub 원격 저장소 연결
```bash
# 1. Git 저장소 초기화
git init

# 2. 파일 추가 및 첫 커밋 (보안: .env는 .gitignore에 의해 자동 제외됨)
git add .
git commit -m "feat: initial commit - enterprise auto credit risk screening pipeline"

# 3. GitHub 팀 원격 저장소 연결 및 푸시
git branch -M main
git remote add origin https://github.com/<팀-또는-사용자명>/<저장소명>.git
git push -u origin main
```

### 📌 브랜치 및 커밋 컨벤션 가이드
- **브랜치 전략**:
  - `main`: 상시 배포 가능한 검증된 안정 버전
  - `feature/collector`: API 수집 로직 개선
  - `feature/mart`: 분석 마트 및 지표 계산 로직 개선
  - `hotfix/mapping`: 계정 매핑 및 비즈니스 예외 수정
- **커밋 메시지 규칙**:
  - `feat`: 새로운 기능 또는 파이프라인 모듈 추가
  - `fix`: 버그 수정 (계정 오매핑, 결측치 보정 등)
  - `refactor`: 코드 구조 개선 및 모듈화
  - `docs`: 문서 수정 (README.md 등)
  - `test`: QA 감사 스크립트 및 테스트 코드 추가
