import json
import requests
import os

# از تلگرام message ها token و account ID رو داریم
CF_TOKEN = os.getenv("CF_TOKEN", "your-token-here")  # Cloudflare API Token
ACCOUNT_ID = "your-account-id"  # از Cloudflare dashboard
NAMESPACE_ID = "your-namespace-id"  # از worker bindings

IPS = [
    {"ip": "162.159.36.70", "port": 443, "latency": 5.6, "colo": "CDG"},
    {"ip": "104.25.121.0", "port": 443, "latency": 6.0, "colo": "CDG"},
    {"ip": "104.18.96.0", "port": 443, "latency": 6.5, "colo": "CDG"},
    {"ip": "172.66.163.0", "port": 80, "latency": 6.3, "colo": "CDG"},
    {"ip": "162.159.253.0", "port": 80, "latency": 6.8, "colo": "CDG"},
    {"ip": "104.16.133.0", "port": 80, "latency": 7.0, "colo": "CDG"},
]

headers = {"Authorization": f"Bearer {CF_TOKEN}"}
url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/storage/kv/namespaces/{NAMESPACE_ID}/values/ips"

resp = requests.put(url, json={"value": json.dumps(IPS)}, headers=headers)
print(resp.status_code, resp.text)
