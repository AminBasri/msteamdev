# test_connection.py
import requests
import json

def test_streamable_http():
    url = "http://localhost:6006/mcp"
    
    # Test initialize
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        }
    }
    
    response = requests.post(url, json=init_request)
    print(f"Initialize response: {response.status_code}")
    print(f"Response: {response.json()}")
    
    # Test tools list
    tools_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    response = requests.post(url, json=tools_request)
    print(f"Tools list response: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    test_streamable_http()