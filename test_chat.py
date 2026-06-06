import requests

url = "http://localhost:8000/api/v1/chat"
headers = {"Content-Type": "application/json", "X-User-ID": "test_user_1"}
data = {"message": "list my transactions", "context": []}

try:
    response = requests.post(url, headers=headers, json=data)
    print("STATUS:", response.status_code)
    print("RESPONSE:", response.json())
except Exception as e:
    print("ERROR:", e)
