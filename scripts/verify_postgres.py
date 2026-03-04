"""Quick verification: list all tables in carebank_db."""

import sys
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="carebank",
    password="Jefino 1537",
    dbname="carebank_db",
)
cur = conn.cursor()
cur.execute(
    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
)
tables = [r[0] for r in cur.fetchall()]
print("Tables in carebank_db:", tables)
sys.stdout.flush()
cur.close()
conn.close()
