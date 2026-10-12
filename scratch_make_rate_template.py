"""
rate_sensitivity_input_template.csv 생성 스크립트
이자율 민감도 공시가 있는 6개사 × 3개년(2021~2023)
공시 없는 4개사는 별도 '공시 없음' 비고 행 포함 (참고 시트 개념)
"""
import csv
import os

# 이자율 민감도 공시 있는 6개사
HAS_DISCLOSURE = [
    ('00561866', '에스엘',     True),
    ('01036446', '서연이화',   True),
    ('00173078', '명신산업',   True),
    ('00164788', '현대모비스', True),
    ('00164742', '현대자동차', False),
    ('00106641', '기아',       False),
]

# 공시 없는 4개사 (참고: 입력 불필요, note='공시 없음'으로 명시)
NO_DISCLOSURE = [
    ('00166315', '화신',       True),
    ('00398792', 'SNT모티브',  True),
    ('01042775', 'HL만도',     True),
    ('00132992', '성우하이텍', True),
]

YEARS    = [2021, 2022, 2023]
BASIS    = 'CFS'
SHOCK    = 1    # 공시 확인값 1%p

FIELDNAMES = [
    'corp_code', 'company_name', 'in_sample', 'has_disclosure',
    'fiscal_year', 'basis',
    'shock_pctp',
    'impact_up', 'impact_down', 'impact_target',
    'source_doc', 'note',
]

os.makedirs('data', exist_ok=True)
outpath = os.path.join('data', 'rate_sensitivity_input_template.csv')

with open(outpath, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()

    # ── 공시 있는 6개사: 입력 필요 행
    for corp_code, company_name, in_sample in HAS_DISCLOSURE:
        for year in YEARS:
            writer.writerow({
                'corp_code':     corp_code,
                'company_name':  company_name,
                'in_sample':     'TRUE' if in_sample else 'FALSE',
                'has_disclosure':'TRUE',
                'fiscal_year':   year,
                'basis':         BASIS,
                'shock_pctp':    SHOCK,        # 확인값
                'impact_up':     '',           # 입력 필요
                'impact_down':   '',           # 입력 필요 (공시 있으면)
                'impact_target': '',           # 입력 필요: pretax_income / interest_expense
                'source_doc':    '',           # 입력 필요: 보고서명·주석번호·페이지
                'note':          '미입력',
            })

    # ── 공시 없는 4개사: 참고 행 (DB 삽입 불필요, 확인용)
    for corp_code, company_name, in_sample in NO_DISCLOSURE:
        for year in YEARS:
            writer.writerow({
                'corp_code':     corp_code,
                'company_name':  company_name,
                'in_sample':     'TRUE' if in_sample else 'FALSE',
                'has_disclosure':'FALSE',
                'fiscal_year':   year,
                'basis':         BASIS,
                'shock_pctp':    '',
                'impact_up':     '',
                'impact_down':   '',
                'impact_target': '',
                'source_doc':    '',
                'note':          '공시 없음',
            })

print(f"[OK] {outpath} created")

with open(outpath, 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))

has_rows = [r for r in rows if r['has_disclosure']=='TRUE']
no_rows  = [r for r in rows if r['has_disclosure']=='FALSE']
print(f"   Total rows: {len(rows)}")
print(f"   Disclosure YES (6 cos): {len(has_rows)} rows - input required")
print(f"   Disclosure NO  (4 cos): {len(no_rows)} rows - note='no disclosure'")
