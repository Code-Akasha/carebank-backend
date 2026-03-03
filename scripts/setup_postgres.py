"""
One-shot script to create the carebank PostgreSQL user and database,
then initialise all SQLAlchemy tables via init_db().
Run from the project root:
    python scripts/setup_postgres.py
"""
import sys
import os
from dotenv import load_dotenv

# Make sure the project root is on sys.path so `app.*` imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH, override=False)

# ── 1. Bootstrap the database / user via the postgres superuser ─────────────
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

SUPERUSER_DSN = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "Jefino 1537",
    "dbname": "postgres",
}

CAREBANK_PASSWORD = os.environ.get("DB_PASSWORD", "Jefino 1537")
CAREBANK_USER = os.environ.get("DB_USER", "carebank")
CAREBANK_DB = os.environ.get("DB_NAME", "carebank_db")

print("Connecting to PostgreSQL as superuser …")
conn = psycopg2.connect(**SUPERUSER_DSN)
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

# Create role
cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (CAREBANK_USER,))
if cur.fetchone():
    cur.execute(f"ALTER USER {CAREBANK_USER} WITH PASSWORD %s", (CAREBANK_PASSWORD,))
    print(f"  Role '{CAREBANK_USER}' already exists – password refreshed.")
else:
    cur.execute(f"CREATE USER {CAREBANK_USER} WITH PASSWORD %s", (CAREBANK_PASSWORD,))
    print(f"  Role '{CAREBANK_USER}' created.")

# Create database
cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (CAREBANK_DB,))
if cur.fetchone():
    print(f"  Database '{CAREBANK_DB}' already exists.")
else:
    cur.execute(f"CREATE DATABASE {CAREBANK_DB} OWNER {CAREBANK_USER}")
    print(f"  Database '{CAREBANK_DB}' created.")

cur.execute(f"GRANT ALL PRIVILEGES ON DATABASE {CAREBANK_DB} TO {CAREBANK_USER}")
print(f"  Privileges granted to '{CAREBANK_USER}'.")

cur.close()
conn.close()

# ── 2. Grant schema privileges (needed for PostgreSQL 15+) ──────────────────
conn2 = psycopg2.connect(
    host="localhost", port=5432,
    user="postgres", password="Jefino 1537",
    dbname=CAREBANK_DB,
)
conn2.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur2 = conn2.cursor()
cur2.execute(f"GRANT ALL ON SCHEMA public TO {CAREBANK_USER}")
cur2.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {CAREBANK_USER}")
print("  Schema public privileges granted.")
cur2.close()
conn2.close()

# ── 3. Verify carebank user can connect ─────────────────────────────────────
print("Verifying carebank user connection …")
conn3 = psycopg2.connect(
    host="localhost", port=5432,
    user=CAREBANK_USER, password=CAREBANK_PASSWORD,
    dbname=CAREBANK_DB,
)
print("  Connection verified ✓")
conn3.close()

# ── 4. Create all SQLAlchemy tables ─────────────────────────────────────────
print("Creating / verifying SQLAlchemy tables …")
load_dotenv(ENV_PATH, override=False)

# Clear lru_cache so settings re-read the freshly loaded env
from app.core import config as _cfg
_cfg.get_settings.cache_clear()

from app.core.database import init_db
init_db()
print("  Tables created / verified ✓")

print("\nPostgreSQL setup complete!")
print(f"  DATABASE_URL = postgresql://{CAREBANK_USER}:***@localhost:5432/{CAREBANK_DB}")
