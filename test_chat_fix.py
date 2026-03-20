#!/usr/bin/env python3
"""Test script for the multi-intent chat fix."""

import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
CHAT_URL = f"{BASE_URL}/api/chat"

# Step 1: Login and get token
print("[1] Logging in...")
try:
    login_resp = requests.post(
        LOGIN_URL,
        json={"email": "admin@carebank.com", "password": "Admin1234!"},
        timeout=5,
    )
    if login_resp.status_code != 200:
        print(f"❌ Login failed: {login_resp.status_code}")
        print(login_resp.text)
        sys.exit(1)
    
    tokens = login_resp.json()
    access_token = tokens.get("access_token")
    user_id = tokens.get("user_id")
    print(f"✅ Logged in as user_id: {user_id}")
    print(f"   Token: {access_token[:20]}...")
except Exception as e:
    print(f"❌ Login error: {e}")
    sys.exit(1)

# Step 2: Test the multi-intent chat query
print("\n[2] Testing multi-intent queries...")
headers = {"Authorization": f"Bearer {access_token}"}

test_messages = [
    ("what is my balance how can i improve my savings", 30),  # Long timeout for Ollama
    ("what's my current balance and how can I save more", 15),
    ("balance check and savings advice please", 15),
]

for msg, timeout in test_messages:
    print(f"\n  Query: '{msg}'")
    print(f"  (timeout: {timeout}s)")
    try:
        chat_resp = requests.post(
            CHAT_URL,
            json={"message": msg},
            headers=headers,
            timeout=timeout,
        )
        if chat_resp.status_code != 200:
            print(f"  ❌ Chat failed: {chat_resp.status_code}")
            print(f"     {chat_resp.text[:200]}")
            continue
        
        result = chat_resp.json()
        intent = result.get("intent", "unknown")
        agent_used = result.get("agent_used", "unknown")
        response = result.get("response", "")
        
        print(f"  ✅ Intent: {intent}")
        print(f"     Agent: {agent_used}")
        print(f"     Response: {response[:150]}...")
        
        # Check if response includes both balance and savings info
        has_balance = "balance" in response.lower()
        has_savings = "save" in response.lower() or "savings" in response.lower()
        
        print(f"     Has balance info: {has_balance}")
        print(f"     Has savings info: {has_savings}")
        
        if not (has_balance and has_savings):
            print(f"     ⚠️  Expected both balance AND savings advice!")
    except requests.exceptions.Timeout:
        print(f"  ❌ Request timeout after {timeout}s")
    except Exception as e:
        print(f"  ❌ Chat error: {e}")

print("\n[3] Test complete!")

