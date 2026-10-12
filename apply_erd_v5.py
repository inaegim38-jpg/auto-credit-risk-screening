import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "dart_ecos")
DB_USER = os.getenv("DB_USER", "neondb_owner")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require")

print(f"Connecting to NeonDB: {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} (sslmode={DB_SSLMODE})...")
conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    sslmode=DB_SSLMODE
)
conn.autocommit = True
cur = conn.cursor()

ddl_path = "sql/00_complete_erd_v5_ddl.sql"
print(f"Executing DDL from {ddl_path}...")
with open(ddl_path, "r", encoding="utf-8") as f:
    ddl_sql = f.read()

cur.execute(ddl_sql)
print("[OK] DDL executed successfully!")

cur.execute("""
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_type, table_name;
""")
rows = cur.fetchall()
print(f"\nCreated Tables & Views in 'public' ({len(rows)} items):")
for r in rows:
    print(f"  [{r[2]}] {r[0]}.{r[1]}")

cur.close()
conn.close()
