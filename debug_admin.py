import requests
import bcrypt
from sqlalchemy import create_engine, text
from app.core.config import get_settings

# Live test - admin login
r = requests.post(
    "http://127.0.0.1:8000/api/auth/login",
    json={"email": "admin@carebank.com", "password": "Admin1234!"},
    timeout=5,
)
print("Admin live login:", r.status_code, r.text[:150])

# Check DB directly with fresh engine
settings = get_settings()
engine2 = create_engine(settings.database_url)
with engine2.connect() as conn:
    rows = conn.execute(
        text("SELECT user_id, email, role, password_hash FROM users")
    ).all()
    for row in rows:
        uid, email, role, ph = row[0], row[1], row[2], row[3]
        ok = bcrypt.checkpw(b"Admin1234!", ph.encode())
        print(
            f"  {email} | role={role} | uid={uid} | hash={ph[:25]} | verify Admin1234!={ok}"
        )
