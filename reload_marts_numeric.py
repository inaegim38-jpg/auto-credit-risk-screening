import psycopg2, os, pandas as pd, numpy as np
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()

p_rt = r'C:/Users/user/.gemini/antigravity/brain/33e2d7da-5a37-40c0-ab75-9d8f2ef6884b/.user_uploaded/media_1791449252875.csv'
p_fx = r'C:/Users/user/.gemini/antigravity/brain/33e2d7da-5a37-40c0-ab75-9d8f2ef6884b/.user_uploaded/media_1791449252905.csv'

df_rt = pd.read_csv(p_rt)
df_fx = pd.read_csv(p_fx)

# In mart_rate_stress, alter amount columns to NUMERIC
for col in ['operating_profit', 'operating_profit_stressed', 'interest_expense', 'short_term_debt', 'debt', 'add_interest_base', 'add_interest_conservative', 'icr_current', 'icr_stress_conservative', 'icr_drop']:
    cur.execute(f'ALTER TABLE mart_rate_stress ALTER COLUMN {col} TYPE NUMERIC;')

# In mart_fx_exposure, alter amount columns to NUMERIC
for col in ['impact_up_usd', 'impact_up_eur', 'impact_up_other', 'impact_up_total_only', 'impact_up_all', 'impact_fx_up10', 'impact_fx_down10', 'equity', 'operating_profit']:
    cur.execute(f'ALTER TABLE mart_fx_exposure ALTER COLUMN {col} TYPE NUMERIC;')

conn.commit()

# Now truncate and re-insert mart_rate_stress
cur.execute('TRUNCATE TABLE mart_rate_stress;')
rt_cols = df_rt.columns.tolist()
for idx, r in df_rt.iterrows():
    vals = []
    for c in rt_cols:
        val = r[c]
        if pd.isna(val):
            vals.append(None)
        elif c == 'corp_code':
            vals.append(str(val).zfill(8))
        elif c == 'risk_shift_yn':
            vals.append(bool(val))
        else:
            vals.append(val)
    placeholders = ', '.join(['%s'] * len(vals))
    col_names = ', '.join([f'"{c}"' if c == 'op_buffer_R3' else c for c in rt_cols])
    cur.execute(f'INSERT INTO mart_rate_stress ({col_names}) VALUES ({placeholders})', vals)

# Truncate and re-insert mart_fx_exposure
cur.execute('TRUNCATE TABLE mart_fx_exposure;')
fx_cols = df_fx.columns.tolist()
for idx, r in df_fx.iterrows():
    vals = []
    for c in fx_cols:
        val = r[c]
        if pd.isna(val):
            vals.append(None)
        elif c == 'corp_code':
            vals.append(str(val).zfill(8))
        elif c == 'stock_code':
            vals.append(str(val).zfill(6))
        else:
            vals.append(val)
    placeholders = ', '.join(['%s'] * len(vals))
    col_names = ', '.join(fx_cols)
    cur.execute(f'INSERT INTO mart_fx_exposure ({col_names}) VALUES ({placeholders})', vals)

conn.commit()
print('Successfully reloaded with arbitrary precision NUMERIC!')
