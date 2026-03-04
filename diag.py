import requests

BASE = "http://127.0.0.1:8000"


def test(method, path, **kw):
    try:
        r = getattr(requests, method)(BASE + path, timeout=30, **kw)
        status = r.status_code
        body = r.text[:150] if status >= 400 else ""
        print("[" + str(status) + "] " + method.upper() + " " + path + " " + body)
        return r
    except Exception as e:
        print("[ERR] " + method.upper() + " " + path + " -> " + str(e))
        return None


admin_r = test(
    "post",
    "/api/auth/login",
    json={"email": "admin@carebank.com", "password": "Admin1234!"},
)
user_r = test(
    "post",
    "/api/auth/login",
    json={"email": "jefino@carebank.com", "password": "Pass1234!"},
)

if admin_r and admin_r.status_code == 200:
    at = admin_r.json()["access_token"]
    ah = {"Authorization": "Bearer " + at}
    print("--- Admin Endpoints ---")
    test("get", "/api/balances/", headers=ah)
    r = test("get", "/api/accounts/", headers=ah)
    if r and r.status_code == 200:
        accs = r.json()
        sample = list(accs[0].keys()) if accs else []
        print("  accounts: " + str(len(accs)) + " items, keys: " + str(sample))
    test("get", "/api/transactions/?limit=5", headers=ah)
    test("get", "/api/health-score/", headers=ah)
    test("get", "/api/products/", headers=ah)
    ur = test("get", "/api/admin/users", headers=ah)
    if ur and ur.status_code == 200:
        d = ur.json()
        print(
            "  admin/users total: "
            + str(d.get("total"))
            + " keys: "
            + str(list(d.keys()))
        )
    test("get", "/api/admin/agent-logs", headers=ah)
    test("get", "/api/admin/simulation/status", headers=ah)
else:
    print("ADMIN STILL FAILING!")

if user_r and user_r.status_code == 200:
    ut = user_r.json()["access_token"]
    uh = {"Authorization": "Bearer " + ut}
    print("--- User Endpoints ---")
    br = test("get", "/api/balances/", headers=uh)
    if br and br.status_code == 200:
        print("  Balance data: " + str(br.json()))
    test("get", "/api/accounts/", headers=uh)
    txr = test("get", "/api/transactions/?limit=5", headers=uh)
    if txr and txr.status_code == 200:
        d = txr.json()
        print(
            "  Transactions: total="
            + str(d.get("total"))
            + " count="
            + str(len(d.get("transactions", [])))
        )
    test("get", "/api/health-score/", headers=uh)
    sr = test(
        "post",
        "/api/simulate",
        json={"user_id": "user_001", "expense_amount": 5000, "category": "food"},
        headers=uh,
    )
    if sr and sr.status_code == 200:
        d = sr.json()
        impact = d.get("impact", {})
        print(
            "  Simulate: risk="
            + str(impact.get("risk_level"))
            + " retained="
            + str(impact.get("retained_percentage"))
        )
    print("--- AI Chat Test ---")
    cr = test(
        "post",
        "/api/chat",
        json={
            "message": "What is my balance?",
            "user_id": "user_001",
            "thread_id": "user_001",
        },
        headers=uh,
    )
    if cr and cr.status_code == 200:
        resp = cr.json().get("response", "")
        print("  Chat response: " + resp[:300])
    else:
        body = cr.text[:200] if cr else "no response"
        print("  Chat failed: " + body)
