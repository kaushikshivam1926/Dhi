import json

def simulate_request(data):
    job_id_param = data.get('job_id')
    print("job_id_param extracted:", job_id_param)

data = json.loads('{"trigger_type": "cron", "cron_hour": 10, "cron_minute": 30, "job_id": "test_edit_123"}')
simulate_request(data)
