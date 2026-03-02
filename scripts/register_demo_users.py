"""Standalone script to populate backend users by registering via the API.

Run this after the backend and banking API are both running:
    python scripts/register_demo_users.py

This script calls POST /api/auth/register for each demo user,
which creates both a backend User record and a banking API profile.
The backend framework itself contains NO hardcoded user data.
"""
from __future__ import annotations

import httpx
import sys

BASE_URL = "http://localhost:8000"

INDIAN_NAMES = [
    "Avni Singh", "Ritvik Sharma", "Aarav Verma", "Saanvi Gupta", "Vihaan Patel",
    "Diya Reddy", "Arjun Nair", "Ananya Joshi", "Ishaan Iyer", "Myra Menon",
    "Sai Desai", "Pari Rao", "Reyansh Pillai", "Anika Mishra", "Ayaan Chopra",
    "Navya Kapoor", "Krishna Malhotra", "Angel Bhat", "Shaurya Agarwal", "Riya Sinha",
    "Atharv Dutta", "Kiara Chauhan", "Advik Pandey", "Prisha Thakur", "Pranav Kumar",
    "Meera Sharma", "Advait Verma", "Trisha Gupta", "Dhruv Singh", "Kavya Patel",
    "Kabir Reddy", "Ishita Nair", "Ritvik Joshi", "Tanvi Iyer", "Aarush Menon",
    "Neha Desai", "Kayaan Rao", "Pooja Pillai", "Darsh Mishra", "Shreya Chopra",
    "Veer Kapoor", "Sahil Malhotra", "Arnav Bhat", "Rudra Agarwal", "Aadhya Sinha",
    "Vivaan Dutta", "Aditya Chauhan", "Sara Pandey", "Ira Thakur", "Aanya Kumar",
    "Rohit Sharma", "Priya Verma", "Amit Gupta", "Sunita Singh", "Raj Patel",
    "Anjali Reddy", "Vikram Nair", "Deepika Joshi", "Suresh Iyer", "Lakshmi Menon",
    "Mohan Desai", "Geeta Rao", "Arun Pillai", "Kavita Mishra", "Rahul Chopra",
    "Smita Kapoor", "Nikhil Malhotra", "Rekha Bhat", "Manish Agarwal", "Swati Sinha",
    "Ajay Dutta", "Nisha Chauhan", "Manoj Pandey", "Shilpa Thakur", "Vinod Kumar",
    "Pallavi Sharma", "Sumit Verma", "Divya Gupta", "Karan Singh", "Meena Patel",
    "Harish Reddy", "Jaya Nair", "Sanjay Joshi", "Uma Iyer", "Rajesh Menon",
    "Chitra Desai", "Prakash Rao", "Lata Pillai", "Ashok Mishra", "Bharti Chopra",
    "Ganesh Kapoor", "Radha Malhotra", "Sunil Bhat", "Pushpa Agarwal", "Dinesh Sinha",
    "Kamala Dutta", "Vijay Chauhan", "Savita Pandey", "Ramesh Thakur", "Anita Kumar",
]


def register_users(count: int = 100) -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # Register admin
    print("Registering admin...")
    r = client.post("/api/auth/register", json={
        "email": "admin@carebank.demo",
        "password": "AdminCare2026!",
        "full_name": "CareBank Admin",
    })
    if r.status_code == 201:
        print("  ✅ Admin registered")
    elif r.status_code == 409:
        print("  ⏭️  Admin already exists")
    else:
        print(f"  ❌ Admin failed: {r.status_code} {r.text}")

    # Register users
    success = 0
    skipped = 0
    for idx in range(1, count + 1):
        name = INDIAN_NAMES[idx - 1] if idx <= len(INDIAN_NAMES) else f"User {idx:03d}"
        email = f"user{idx:03d}@carebank.demo"
        password = f"CareBank{idx:03d}!"

        r = client.post("/api/auth/register", json={
            "email": email,
            "password": password,
            "full_name": name,
        })
        if r.status_code == 201:
            success += 1
        elif r.status_code == 409:
            skipped += 1
        else:
            print(f"  ❌ {email}: {r.status_code} {r.text}")

        if idx % 10 == 0:
            print(f"  Progress: {idx}/{count}")

    print(f"\n✅ Done: {success} registered, {skipped} already existed")


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    register_users(count)
