from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

resp = client.post('/api/auth/register', json={'email':'debug@test.local','password':'Password123!','full_name':'Debug User'})
print('register', resp.status_code, resp.text)
if resp.status_code!=201:
    raise SystemExit(1)

payload = resp.json()
headers={'Authorization':f"Bearer {payload['access_token']}"}

r1 = client.post('/api/chat', headers=headers, json={'message':'transfer 5000 to savings'})
print('first', r1.status_code, r1.json())

r2 = client.post('/api/chat', headers=headers, json={'message':'yes'})
print('second', r2.status_code, r2.json())
