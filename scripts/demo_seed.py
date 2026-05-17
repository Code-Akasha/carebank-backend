#!/usr/bin/env python3
"""
CareBank Demo Seed Script
==========================
Creates demo users with 3 months of transaction history, service accounts,
and pre-configured recurring payments. Runs against a LIVE backend + banking proxy.

Usage:
    python scripts/demo_seed.py [--backend-url http://localhost:8000] [--provider-url http://localhost:8001]

What it creates:
  ┌──────────────────────────────────────────────────────────────────┐
  │ DEMO USERS (3 health profiles)                                   │
  ├──────────────┬─────────────────┬──────────┬──────────────────────┤
  │ Name          │ Email           │ Persona  │ Health Profile       │
  ├──────────────┼─────────────────┼──────────┼──────────────────────┤
  │ Rajesh Kumar │ rajesh@demo.com │ Saver    │ Good (80+)           │
  │ Priya Sharma │ priya@demo.com  │ Balanced │ Fair (50-65)         │
  │ Amit Verma   │ amit@demo.com   │ Spender  │ Poor (25-40)         │
  └──────────────┴─────────────────┴──────────┴──────────────────────┘
  ┌──────────────────────────────────────────────────────────────────┐
  │ SERVICE ACCOUNTS (for auto-pay demo)                             │
  ├──────────────────┬───────────────────┬────────────────────────────┤
  │ Name             │ Email             │ Type                       │
  ├──────────────────┼───────────────────┼────────────────────────────┤
  │ DishTV Services  │ dishtv@demo.com   │ Business - DTH provider    │
  │ Indane Gas       │ indane@demo.com   │ Business - Gas agency      │
  │ City Rentals     │ rent@demo.com     │ Business - Property mgmt   │
  └──────────────────┴───────────────────┴────────────────────────────┘
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from pathlib import Path

import httpx
import jwt

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.database import SessionLocal
from app.models.user import User

# ── Config ────────────────────────────────────────────────────────────────
DEMO_PASSWORD = "Demo@2026!"
PROVIDER_SECRET = "supersecret123"
BACKEND_URL = "http://localhost:8000"
PROVIDER_URL = "http://localhost:8001"
DAYS_HISTORY = 90  # 3 months

# ── Demo Users ────────────────────────────────────────────────────────────
DEMO_USERS = [
    {
        "email": "rajesh@demo.com",
        "password": DEMO_PASSWORD,
        "full_name": "Rajesh Kumar",
        "role": "user",
        "persona": "Saver",
        "salary": 75000,
        "initial_balance": 185000.0,
    },
    {
        "email": "priya@demo.com",
        "password": DEMO_PASSWORD,
        "full_name": "Priya Sharma",
        "role": "user",
        "persona": "Balanced",
        "salary": 55000,
        "initial_balance": 45000.0,
    },
    {
        "email": "amit@demo.com",
        "password": DEMO_PASSWORD,
        "full_name": "Amit Verma",
        "role": "user",
        "persona": "Spender",
        "salary": 48000,
        "initial_balance": 12000.0,
    },
]

SERVICE_ACCOUNTS = [
    {
        "email": "dishtv@demo.com",
        "password": DEMO_PASSWORD,
        "full_name": "DishTV Services",
        "role": "user",
        "persona": None,
        "salary": 0,
        "initial_balance": 50000.0,
    },
    {
        "email": "indane@demo.com",
        "password": DEMO_PASSWORD,
        "full_name": "Indane Gas Agency",
        "role": "user",
        "persona": None,
        "salary": 0,
        "initial_balance": 75000.0,
    },
    {
        "email": "rent@demo.com",
        "password": DEMO_PASSWORD,
        "full_name": "City Rentals Property Management",
        "role": "user",
        "persona": None,
        "salary": 0,
        "initial_balance": 100000.0,
    },
]

ADMIN = {
    "email": "admin@carebank.demo",
    "password": "AdminCare2026!",
    "full_name": "CareBank Admin",
}

# ── Merchant catalogue ────────────────────────────────────────────────────
CATEGORY_MERCHANTS: dict[str, list[str]] = {
    "groceries": ["DMart", "Big Bazaar", "Reliance Fresh", "BigBasket", "Zepto"],
    "dining": ["Swiggy", "Zomato", "Blinkit", "McDonald's India", "Burger King IN"],
    "transport": ["Uber", "Ola", "Indian Oil", "HP Petrol", "Metro Rail"],
    "shopping": ["Amazon India", "Flipkart", "Myntra", "Meesho", "Nykaa"],
    "utilities": ["TNEB", "BESCOM", "Jio Fiber", "Airtel Broadband", "Tata Power"],
    "health": ["Apollo Pharmacy", "MedPlus", "1mg", "Practo", "PharmEasy"],
    "entertainment": ["Netflix", "Hotstar", "Amazon Prime", "Spotify", "BookMyShow"],
}

# Recurring merchants for demo
RECURRING_MERCHANTS = [
    {
        "merchant": "DishTV Services",
        "category": "utilities",
        "amount": 350,
        "label": "Dish TV",
    },
    {
        "merchant": "Indane Gas Agency",
        "category": "utilities",
        "amount": 950,
        "label": "Gas Cylinder",
    },
    {
        "merchant": "Jio Fiber",
        "category": "utilities",
        "amount": 799,
        "label": "Internet",
    },
    {
        "merchant": "TNEB",
        "category": "utilities",
        "amount": 1200,
        "label": "Electricity",
    },
]

PERSONAS: dict[str, dict] = {
    "Saver": {
        "salary_range": (55000, 90000),
        "balance_buffer": (0.40, 0.65),
        "category_weights": {
            "groceries": 0.30,
            "dining": 0.08,
            "transport": 0.12,
            "shopping": 0.08,
            "utilities": 0.15,
            "health": 0.12,
            "entertainment": 0.05,
        },
        "daily_txn_range": (1, 2),
        "weekend_multiplier": 1.3,
    },
    "Spender": {
        "salary_range": (40000, 70000),
        "balance_buffer": (0.10, 0.30),
        "category_weights": {
            "groceries": 0.15,
            "dining": 0.25,
            "transport": 0.12,
            "shopping": 0.22,
            "utilities": 0.10,
            "health": 0.06,
            "entertainment": 0.10,
        },
        "daily_txn_range": (2, 5),
        "weekend_multiplier": 2.0,
    },
    "Balanced": {
        "salary_range": (45000, 80000),
        "balance_buffer": (0.20, 0.45),
        "category_weights": {
            "groceries": 0.22,
            "dining": 0.15,
            "transport": 0.13,
            "shopping": 0.15,
            "utilities": 0.15,
            "health": 0.10,
            "entertainment": 0.10,
        },
        "daily_txn_range": (1, 4),
        "weekend_multiplier": 1.6,
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────


def _format_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _provider_token(user_id: str, role: str = "admin") -> str:
    payload = {
        "user_id": user_id,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, PROVIDER_SECRET, algorithm="HS256")


def _generate_transactions(
    user_id: str,
    persona_name: str,
    salary: int,
    days: int = 90,
) -> list[dict[str, Any]]:
    """Generate deterministic transaction history for a demo user."""
    # Seed from user_id
    h = sum(ord(c) * (i + 1) for i, c in enumerate(user_id))
    rng = random.Random(h)

    persona = PERSONAS[persona_name]
    cats = list(persona["category_weights"].keys())
    weights = [persona["category_weights"][c] for c in cats]

    now = datetime.now(timezone.utc)
    transactions: list[dict[str, Any]] = []
    txn_id = 0

    # Gather unique months in the window
    unique_months: set[tuple[int, int]] = set()
    for day_offset in range(days - 1, -1, -1):
        d = (now - timedelta(days=day_offset)).date()
        unique_months.add((d.year, d.month))

    # Salary on 1st of each month
    for year, month in sorted(unique_months):
        salary_date = datetime(year, month, 1, 9, 0, 0, tzinfo=timezone.utc)
        if salary_date <= now and salary > 0:
            txn_id += 1
            transactions.append(
                {
                    "id": txn_id,
                    "user_id": user_id,
                    "amount": float(salary),
                    "merchant": "Salary Credit",
                    "category": "income",
                    "date": _format_iso(salary_date),
                    "description": "Monthly salary — NEFT credit",
                }
            )

    # Recurring bills on 5th, 10th, 15th
    bill_schedule = [
        (5, "DishTV Services", "utilities", 350, "Monthly DTH subscription"),
        (10, "Jio Fiber", "utilities", 799, "Broadband internet"),
        (15, "TNEB", "utilities", 1200, "Electricity bill"),
    ]
    for year, month in sorted(unique_months):
        for day, merchant, cat, amt, desc in bill_schedule:
            try:
                bill_date = datetime(year, month, day, 11, 0, 0, tzinfo=timezone.utc)
            except ValueError:
                continue
            if bill_date > now:
                continue
            variance = rng.uniform(0.95, 1.05)
            txn_id += 1
            transactions.append(
                {
                    "id": txn_id,
                    "user_id": user_id,
                    "amount": -round(amt * variance, 2),
                    "merchant": merchant,
                    "category": cat,
                    "date": _format_iso(bill_date),
                    "description": desc,
                }
            )

    # Daily variable spending
    for day_offset in range(days - 1, -1, -1):
        date_val = now - timedelta(days=day_offset)
        weekday = date_val.weekday()
        is_weekend = weekday >= 5

        base_min, base_max = persona["daily_txn_range"]
        txn_count = rng.randint(base_min, base_max)
        if is_weekend:
            txn_count = int(txn_count * persona["weekend_multiplier"])

        for _ in range(txn_count):
            cat = rng.choices(cats, weights=weights, k=1)[0]
            merchant = rng.choice(CATEGORY_MERCHANTS.get(cat, ["Local Store"]))

            if cat == "utilities":
                continue  # bills cover utilities
            elif cat in ("dining", "entertainment") and is_weekend:
                amount = round(rng.uniform(300, 1500), 2)
            elif cat == "shopping":
                amount = round(rng.uniform(500, 4000), 2)
            elif cat == "groceries":
                amount = round(rng.uniform(200, 1200), 2)
            elif cat == "health":
                amount = round(rng.uniform(100, 800), 2)
            else:
                amount = round(rng.uniform(100, 600), 2)

            if day_offset <= 7 and cat in ("shopping",):
                amount = round(amount * 1.4, 2)

            hour = rng.randint(8, 22)
            minute = rng.randint(0, 59)
            txn_dt = date_val.replace(hour=hour, minute=minute, second=0, microsecond=0)

            txn_id += 1
            transactions.append(
                {
                    "id": txn_id,
                    "user_id": user_id,
                    "amount": -amount,
                    "merchant": merchant,
                    "category": cat,
                    "date": _format_iso(txn_dt),
                    "description": f"{cat.title()} — {merchant}",
                }
            )

    return transactions


# ── Main ────────────────────────────────────────────────────────────────────


def register_user(
    client: httpx.Client, email: str, password: str, full_name: str
) -> dict | None:
    """Register a user via the backend API. Returns token info or None."""
    resp = client.post(
        f"{BACKEND_URL}/api/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    if resp.status_code == 201:
        token_info = resp.json()
        headers = {"Authorization": f"Bearer {token_info.get('access_token')}"}
        client.get(f"{BACKEND_URL}/api/payment-settings/", headers=headers)
        return token_info
    elif resp.status_code == 409:
        # Already exists — login instead
        resp = client.post(
            f"{BACKEND_URL}/api/auth/login",
            json={"email": email, "password": password},
        )
        if resp.status_code == 200:
            token_info = resp.json()
            headers = {"Authorization": f"Bearer {token_info.get('access_token')}"}
            client.get(f"{BACKEND_URL}/api/payment-settings/", headers=headers)
            return token_info
        print(f"  ⚠️  Login failed for {email}: {resp.text}")
        return None
    else:
        print(f"  ❌ Register failed for {email}: {resp.status_code} {resp.text}")
        return None


def promote_user_role(email: str, role: str) -> bool:
    """Update an existing backend user role directly for demo seeding."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return False
        if user.role != role:
            user.role = role
            db.commit()
            db.refresh(user)
        return True
    finally:
        db.close()


def inject_provider_profile(
    client: httpx.Client,
    user_id: str,
    full_name: str,
    initial_balance: float,
    transactions: list[dict],
    token: str,
) -> bool:
    """Inject a profile + transactions into the banking proxy."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "user_id": user_id,
        "current_balance": initial_balance,
        "available_balance": initial_balance,
        "transactions": [
            {
                "user_id": user_id,
                "amount": float(t["amount"]),
                "merchant": t["merchant"],
                "category": t["category"],
                "description": t["description"],
                "date": t["date"],
            }
            for t in transactions
        ],
    }
    resp = client.post(
        f"{PROVIDER_URL}/profiles",
        headers=headers,
        json=payload,
    )
    if resp.status_code in (200, 201):
        return True
    print(
        f"  ⚠️  Banking proxy profile injection failed for {user_id}: {resp.status_code} {resp.text}"
    )
    return False


def setup_recurring_payment(
    client: httpx.Client,
    backend_token: str,
    user_id: str,
    beneficiary_user_id: str,
    beneficiary_name: str,
    amount: float,
    day_of_month: int,
    description: str,
) -> bool:
    """Set up a recurring payment rule via the backend API."""
    headers = {"Authorization": f"Bearer {backend_token}"}

    # Step 1: Create beneficiary in mockbank via backend
    account_num = f"5{random.randint(10000000, 99999999)}"
    ifsc = f"CARE0{random.randint(100000, 999999)}"
    beneficiary_resp = client.post(
        f"{BACKEND_URL}/api/beneficiaries/",
        headers=headers,
        json={
            "name": beneficiary_name,
            "payment_rail": "imps",
            "account_number": account_num,
            "ifsc": ifsc,
        },
    )
    beneficiary_id = None
    if beneficiary_resp.status_code in (200, 201):
        data = beneficiary_resp.json()
        raw_id = data.get("id") or data.get("beneficiary_id")
        if raw_id is not None:
            try:
                beneficiary_id = int(raw_id)
            except ValueError:
                import re

                match = re.search(r"\d+", str(raw_id))
                if match:
                    beneficiary_id = int(match.group())
    elif beneficiary_resp.status_code == 409:
        pass  # already exists

    if not beneficiary_id:
        # Try to find existing
        list_resp = client.get(f"{BACKEND_URL}/api/beneficiaries/", headers=headers)
        if list_resp.status_code == 200:
            for b in list_resp.json():
                if b.get("name") == beneficiary_name:
                    raw_id = b.get("id")
                    if raw_id is not None:
                        try:
                            beneficiary_id = int(raw_id)
                        except ValueError:
                            import re

                            match = re.search(r"\d+", str(raw_id))
                            if match:
                                beneficiary_id = int(match.group())
                    break

    if not beneficiary_id:
        print(f"  ⚠️  Could not find/create beneficiary: {beneficiary_name}")
        return False

    # Step 2: Create recurring payment rule
    rule_resp = client.post(
        f"{BACKEND_URL}/api/recurring-payments/",
        headers=headers,
        json={
            "beneficiary_id": beneficiary_id,
            "amount": amount,
            "description": description,
            "frequency": "monthly",
            "day_config": {"day_of_month": day_of_month},
            "requires_approval": False,
        },
    )
    if rule_resp.status_code in (200, 201):
        return True
    if rule_resp.status_code == 409:
        return True
    print(
        f"  ⚠️  Recurring rule creation failed: {rule_resp.status_code} {rule_resp.text}"
    )
    return False


def main():
    global BACKEND_URL, PROVIDER_URL, PROVIDER_SECRET
    parser = argparse.ArgumentParser(description="CareBank Demo Seed Script")
    parser.add_argument("--backend-url", default=BACKEND_URL)
    parser.add_argument("--provider-url", default=PROVIDER_URL)
    parser.add_argument(
        "--skip-transactions",
        action="store_true",
        help="Skip generating transaction history",
    )
    parser.add_argument(
        "--skip-recurring",
        action="store_true",
        help="Skip setting up recurring payments",
    )
    args = parser.parse_args()

    BACKEND_URL = args.backend_url.rstrip("/")
    PROVIDER_URL = args.provider_url.rstrip("/")

    print("=" * 65)
    print("  CareBank Demo Seed Script")
    print(f"  Backend:  {BACKEND_URL}")
    print(f"  Banking Proxy: {PROVIDER_URL}")
    print("=" * 65)

    client = httpx.Client(timeout=30.0)
    provider_admin_token = _provider_token("admin", role="admin")

    # ── 1. Register Admin ──────────────────────────────────────────────
    print("\n── 1. Registering Admin ──")
    result = register_user(
        client, ADMIN["email"], ADMIN["password"], ADMIN["full_name"]
    )
    if result:
        promote_user_role(ADMIN["email"], "admin")
        print(f"  ✅ Admin: {ADMIN['email']} (ID: {result.get('user_id', 'N/A')})")

    # ── 2. Register Service Accounts ───────────────────────────────────
    print("\n── 2. Registering Service Accounts ──")
    service_ids: dict[str, str] = {}
    for svc in SERVICE_ACCOUNTS:
        result = register_user(client, svc["email"], svc["password"], svc["full_name"])
        if result:
            uid = result["user_id"]
            service_ids[svc["email"]] = uid
            # Inject balance into proxy
            inject_provider_profile(
                client,
                uid,
                svc["full_name"],
                svc["initial_balance"],
                [],
                provider_admin_token,
            )
            print(f"  ✅ {svc['full_name']}: {svc['email']} (ID: {uid})")
        else:
            print(f"  ❌ Failed: {svc['email']}")

    # ── 3. Register Demo Users ─────────────────────────────────────────
    print("\n── 3. Registering Demo Users (with transaction history) ──")
    demo_tokens: dict[str, dict] = {}
    for user in DEMO_USERS:
        result = register_user(
            client, user["email"], user["password"], user["full_name"]
        )
        if not result:
            continue

        uid = result["user_id"]
        token = result["access_token"]
        demo_tokens[user["email"]] = {
            "user_id": uid,
            "token": token,
            "full_name": user["full_name"],
            "persona": user["persona"],
        }

        if not args.skip_transactions:
            # Generate rich transaction history
            txns = _generate_transactions(
                uid, user["persona"], user["salary"], days=DAYS_HISTORY
            )
            print(f"  📊 Generated {len(txns)} transactions for {user['full_name']}")

            # Inject into proxy
            ok = inject_provider_profile(
                client,
                uid,
                user["full_name"],
                user["initial_balance"],
                txns,
                provider_admin_token,
            )
            if ok:
                print(
                    f"  ✅ {user['full_name']}: {user['email']} (ID: {uid}, {len(txns)} txns)"
                )
            else:
                print(f"  ⚠️  {user['full_name']}: registered but txns injection failed")
        else:
            print(f"  ✅ {user['full_name']}: {user['email']} (ID: {uid}) [no txns]")

    # ── 4. Setup Recurring Payments ────────────────────────────────────
    if not args.skip_recurring and demo_tokens:
        print("\n── 4. Setting up Recurring Payments ──")
        # Rajesh -> DishTV + Jio Fiber
        rajesh = demo_tokens.get("rajesh@demo.com", {})
        dishtv_id = service_ids.get("dishtv@demo.com", "")
        indane_id = service_ids.get("indane@demo.com", "")
        rent_id = service_ids.get("rent@demo.com", "")

        if rajesh and dishtv_id:
            ok = setup_recurring_payment(
                client,
                rajesh["token"],
                rajesh["user_id"],
                dishtv_id,
                "DishTV Services",
                350,
                5,
                "Monthly DTH subscription",
            )
            print(f"  {'✅' if ok else '❌'} Rajesh → DishTV (₹350/month on 5th)")

            if rent_id:
                ok = setup_recurring_payment(
                    client,
                    rajesh["token"],
                    rajesh["user_id"],
                    rent_id,
                    "City Rentals",
                    12000,
                    1,
                    "Monthly rent payment",
                )
                print(f"  {'✅' if ok else '❌'} Rajesh → Rent (₹12,000/month on 1st)")

        # Priya -> Indane Gas
        priya = demo_tokens.get("priya@demo.com", {})
        if priya and indane_id:
            ok = setup_recurring_payment(
                client,
                priya["token"],
                priya["user_id"],
                indane_id,
                "Indane Gas Agency",
                950,
                10,
                "Monthly gas cylinder",
            )
            print(f"  {'✅' if ok else '❌'} Priya → Indane Gas (₹950/month on 10th)")

        # Amit -> DishTV
        amit = demo_tokens.get("amit@demo.com", {})
        if amit and dishtv_id:
            ok = setup_recurring_payment(
                client,
                amit["token"],
                amit["user_id"],
                dishtv_id,
                "DishTV Services",
                350,
                5,
                "Monthly DTH subscription",
            )
            print(f"  {'✅' if ok else '❌'} Amit → DishTV (₹350/month on 5th)")

    # ── 5. Print Summary ───────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  🎉 DEMO SETUP COMPLETE")
    print("=" * 65)
    print(f"""
  ┌─────────────────────────────────────────────────────────────┐
  │ DEMO CREDENTIALS                                            │
  ├──────────────┬──────────────────┬───────────────┬────────────┤
  │ Name         │ Email            │ Password      │ Health     │
  ├──────────────┼──────────────────┼───────────────┼────────────┤
  │ Rajesh Kumar │ rajesh@demo.com  │ {DEMO_PASSWORD}     │ GOOD (80+) │
  │ Priya Sharma │ priya@demo.com   │ {DEMO_PASSWORD}     │ FAIR (50+) │
  │ Amit Verma   │ amit@demo.com    │ {DEMO_PASSWORD}     │ POOR (30+) │
  ├──────────────┼──────────────────┼───────────────┼────────────┤
  │ Admin        │ admin@carebank   │ AdminCare2026!│ —          │
  │              │ .demo            │               │            │
  └──────────────┴──────────────────┴───────────────┴────────────┘

  Service Accounts (for auto-pay):
  - DishTV Services:  dishtv@demo.com  / {DEMO_PASSWORD}
  - Indane Gas:       indane@demo.com  / {DEMO_PASSWORD}
  - City Rentals:     rent@demo.com    / {DEMO_PASSWORD}

  Recurring Payments Configured:
  - Rajesh → DishTV (₹350 on 5th), Rent (₹12,000 on 1st)
  - Priya → Indane Gas (₹950 on 10th)
  - Amit → DishTV (₹350 on 5th)

  Endpoints:
  - Backend API:     {BACKEND_URL}
  - Swagger Docs:    {BACKEND_URL}/docs
    - Banking Proxy:   {PROVIDER_URL}
  - Frontend:        http://localhost:5173

  To show the demo:
  1. Open http://localhost:5173 in browser
  2. Login as rajesh@demo.com / {DEMO_PASSWORD}
  3. Show: Dashboard → Health Score → Transactions
  4. Show: Chat → "schedule my Dish TV payment for the 5th"
  5. Show: Admin panel → admin@carebank.demo / AdminCare2026!
  6. Show: Auto-pay → Recurring Payments page
""")

    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
