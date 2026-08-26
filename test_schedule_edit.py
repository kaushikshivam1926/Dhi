import urllib.request
import json

data = {
    "trigger_type": "cron",
    "cron_hour": 10,
    "cron_minute": 30,
    "job_id": "test_edit_123"
}

req = urllib.request.Request("http://127.0.0.1:8080/api/schedule/podcast", data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print(e)
