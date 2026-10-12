import pandas as pd

df = pd.read_csv('data/corp_code_list.csv', dtype=str, encoding='utf-8-sig')
df['corp_code'] = df['corp_code'].str.zfill(8)

# 10개사 stock_code → corp_code 조회
targets = {
    '115390': ('에스엘',      True),
    '200880': ('서연이화',    True),
    '010690': ('화신',        True),
    '009900': ('명신산업',    True),
    '064960': ('SNT모티브',   True),
    '204320': ('HL만도',      True),
    '015750': ('성우하이텍',  True),
    '012330': ('현대모비스',  True),
    '005380': ('현대자동차',  False),
    '000270': ('기아',        False),
}

results = {}
for sc, (name, in_sample) in targets.items():
    row = df[df['stock_code'] == sc]
    if len(row) == 0:
        print(f'NOT FOUND: {name} ({sc})')
        results[sc] = None
    else:
        r = row.iloc[0]
        cc = r['corp_code']
        cn = r['corp_name']
        print(f"{name:12s} | stock={sc} | corp_code={cc} | corp_name={cn} | in_sample={in_sample}")
        results[sc] = cc
