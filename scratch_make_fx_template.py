"""
fx_risk_input_template.csv 생성 스크립트
10개사 × 3개년(2021~2023) × 주요통화(USD, EUR, JPY)
shock_pct는 확정값 채움, 나머지 입력칸은 공백(빈 문자열), note='미입력'
"""
import csv
import os

# 10개사 정보 (corp_code: corpCode.xml 조회 확인값)
COMPANIES = [
    # (corp_code, company_name, stock_code, shock_pct, in_sample)
    ('00561866', '에스엘',     '115390',  5,  True),
    ('01036446', '서연이화',   '200880', 10,  True),
    ('00166315', '화신',       '010690',  5,  True),
    ('00173078', '명신산업',   '009900', 10,  True),
    ('00398792', 'SNT모티브',  '064960', 10,  True),
    ('01042775', 'HL만도',     '204320', 10,  True),
    ('00132992', '성우하이텍', '015750', 10,  True),
    ('00164788', '현대모비스', '012330', 10,  True),
    ('00164742', '현대자동차', '005380',  5, False),
    ('00106641', '기아',       '000270', 10, False),
]

YEARS     = [2021, 2022, 2023]
CURRENCIES = ['USD', 'EUR', 'JPY']
BASIS     = 'CFS'  # 연결 기준 기본값

FIELDNAMES = [
    'corp_code', 'company_name', 'in_sample',
    'fiscal_year', 'currency', 'basis',
    'shock_pct',
    'impact_up', 'impact_down', 'impact_target',
    'source_doc', 'note', 'checked_at',
]

os.makedirs('data', exist_ok=True)
outpath = os.path.join('data', 'fx_risk_input_template.csv')

with open(outpath, 'w', newline='', encoding='utf-8-sig') as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()

    for corp_code, company_name, stock_code, shock_pct, in_sample in COMPANIES:
        for year in YEARS:
            for currency in CURRENCIES:
                writer.writerow({
                    'corp_code':     corp_code,
                    'company_name':  company_name,
                    'in_sample':     'TRUE' if in_sample else 'FALSE',
                    'fiscal_year':   year,
                    'currency':      currency,
                    'basis':         BASIS,
                    'shock_pct':     shock_pct,     # 확정값
                    'impact_up':     '',            # 입력 필요
                    'impact_down':   '',            # 입력 필요
                    'impact_target': '',            # 입력 필요: pretax_income / equity
                    'source_doc':    '',            # 입력 필요: 보고서명·주석번호·페이지
                    'note':          '미입력',
                    'checked_at':    '',
                })

print(f"[OK] {outpath} created")

# row count check
with open(outpath, 'r', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
print(f"   Total rows: {len(rows)}")
print(f"   = {len(COMPANIES)} companies x {len(YEARS)} years x {len(CURRENCIES)} currencies")
