# test_mcp_connection.py

import requests
import json

MCP_URL = "http://localhost:6006/mcp"

headers = {"Content-Type": "application/json"}
payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
}

try:
    print(f"📡 Sending POST to {MCP_URL}")
    response = requests.post(MCP_URL, headers=headers, json=payload, timeout=5)
    print(f"✅ Response Code: {response.status_code}")
    print("🔁 Response Body:", json.dumps(response.json(), indent=2))
except requests.exceptions.RequestException as e:
    print(f"❌ MCP connection failed: {e}")
