# src/msteamuat/tools/mcp_server.py

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from pdpyras import APISession  # Reverted to pdpyras
import os
import logging
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

app = FastAPI(title="PagerDuty MCP Server")

# Configure logger
logger = logging.getLogger('mcp_server')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

# Add FileHandler for mcp_server.log
file_handler = logging.FileHandler('/home/crewai/msteamuat/log/mcp_server.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

class IncidentRequest(BaseModel):
    incident_number: str
    from_email: str = os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")

class RelatedAlertsRequest(BaseModel):
    service_id: str = os.getenv("PAGERDUTY_SERVICE_ID", "PIU29W4")
    start_time: str
    end_time: str

def get_pagerduty_session():
    token = os.getenv("PAGERDUTY_API_TOKEN")
    if not token:
        logger.critical("PAGERDUTY_API_TOKEN environment variable is not set")
        raise HTTPException(status_code=500, detail="Missing PagerDuty API token")
    return APISession(token)  # Reverted to pdpyras.APISession

def find_incident_by_number(session, incident_number: str):
    logger.debug(f"Searching for incident number: {incident_number}")
    try:
        for incident in session.iter_all("incidents"):
            logger.debug(f"Checking incident: {incident.get('incident_number')}")
            if str(incident.get("incident_number")) == str(incident_number):
                logger.info(f"Found incident: {incident_number}")
                return incident
        logger.warning(f"Incident {incident_number} not found")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch incidents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch incidents: {str(e)}")

@app.post("/mcp")
async def mcp_handler(request: Request):
    try:
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id", None)  # Allow None for notifications

        logger.debug(f"Received MCP request: method={method}, id={req_id}, params={params}")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pagerduty-mcp-server", "version": "1.0.0"}
                }
            }
        elif method == "notifications/initialized":
            logger.info("Received notifications/initialized")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": None  # Proper JSON-RPC response
            }
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "GetIncidentStatus",
                            "description": "Get the status of a PagerDuty incident by incident number",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "incident_number": {
                                        "type": "string",
                                        "description": "The incident number to check"
                                    }
                                },
                                "required": ["incident_number"],
                                "json_schema_extra": {}
                            }
                        },
                        {
                            "name": "AcknowledgeIncident",
                            "description": "Acknowledge a PagerDuty incident",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "incident_number": {"type": "string"},
                                    "from_email": {"type": "string"}
                                },
                                "required": ["incident_number"],
                                "json_schema_extra": {}
                            }
                        },
                        
                    ]
                }
            }
        elif method == "tools/call":
            tool = params.get("name")
            args = params.get("arguments", {})
            if tool == "GetIncidentStatus":
                return await call_get_incident_status(req_id, args)
            elif tool == "AcknowledgeIncident":
                return await call_acknowledge_incident(req_id, args)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool}"}
                }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown method: {method}"}
        }
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": "Parse error: Invalid JSON"}
        }
    except Exception as e:
        logger.exception(f"Failed to process MCP request: {str(e)}")
        return {
            "jsonrpc": "2.0",
            "id": req_id if 'req_id' in locals() else 1,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }

async def call_get_incident_status(req_id, args, max_retries=3):
    for attempt in range(max_retries):
        try:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor() as executor:
                def logic():
                    session = get_pagerduty_session()
                    incident = find_incident_by_number(session, args["incident_number"])
                    if not incident:
                        raise HTTPException(status_code=404, detail="Incident not found")
                    return {
                        "id": incident["id"],
                        "incident_number": incident["incident_number"],
                        "status": incident["status"]
                    }
                result = await loop.run_in_executor(executor, logic)
                logger.info(f"Fetching status for incident number: {args['incident_number']}, Status: {result['status']}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result)}]}
                }
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed for GetIncidentStatus: {str(e)}")
            if attempt == max_retries - 1:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": f"Failed after {max_retries} attempts: {str(e)}"}
                }
            await asyncio.sleep(1)

async def call_acknowledge_incident(req_id, args):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as executor:
        try:
            def logic():
                logger.info(f"AcknowledgeIncident args received: {args}")
                session = get_pagerduty_session()
                email = args.get("from_email") or os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")
                incident = find_incident_by_number(session, args["incident_number"])
                if not incident:
                    raise HTTPException(status_code=404, detail="Incident not found")
                if incident["status"] == "acknowledged":
                    logger.info(f"Incident {incident['incident_number']} already acknowledged")
                    return {
                        "status": "already_acknowledged",
                        "incident_number": incident['incident_number']
                    }
                session.rput(
                    f"/incidents/{incident['id']}",
                    json={"incident": {"type": "incident_reference", "status": "acknowledged"}},
                    headers={"From": email}
                )
                verified = find_incident_by_number(session, args["incident_number"])
                if verified["status"] != "acknowledged":
                    raise HTTPException(status_code=500, detail="Failed to acknowledge")
                logger.info(f"Incident {incident['incident_number']} acknowledged successfully")
                return {
                    "status": "acknowledged",
                    "incident_id": verified["id"],
                    "service_id": verified['service']['id'],
                    "acknowledged_at": verified['last_status_change_at']
                }
            result = await loop.run_in_executor(executor, logic)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result)}]}
            }
        except Exception as e:
            logger.error(f"Failed to acknowledge incident: {str(e)}")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Failed to acknowledge incident: {str(e)}"}
            }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=6006, log_level="info")