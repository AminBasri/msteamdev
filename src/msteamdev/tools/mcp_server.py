# src/msteamdev/tools/mcp_server.py

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from pdpyras import APISession  # Reverted to pdpyras
import os
import logging
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from fastapi.responses import JSONResponse

app = FastAPI(title="PagerDuty MCP Server")

from msteamdev.logging_setup import get_module_logger

# Configure centralized logger
logger = get_module_logger('mcp_server', log_filename='mcp_server.log', level=logging.INFO)

# Log startup to verify logging is working
logger.info("MCP Server module loaded - logging configured")

class IncidentRequest(BaseModel):
    incident_number: str
    from_email: str = os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")

def get_pagerduty_session():
    token = os.getenv("PAGERDUTY_API_TOKEN")
    if not token:
        logger.critical("PAGERDUTY_API_TOKEN environment variable is not set")
        raise HTTPException(status_code=500, detail="Missing PagerDuty API token")
    return APISession(token)  # Reverted to pdpyras.APISession

from msteamdev.tools.redis_client import cache_get, cache_set, cache_delete

def _is_placeholder_email(email: str | None) -> bool:
    if not email:
        return True
    lowered = email.strip().lower()
    return lowered in {"your_email@example.com", "test@example.com", "user@example.com"} or lowered.endswith("@example.com")

def _validate_pd_user_email(session: APISession, email: str) -> bool:
    try:
        # Search users by query and look for exact email match
        users = list(session.iter_all("users", params={"query": email}))
        for user in users:
            if str(user.get("email", "")).strip().lower() == email.strip().lower():
                return True
        return False
    except Exception:
        # On API error, be conservative and mark invalid so we can fallback
        return False

def _resolve_requester_email(session: APISession, provided_email: str | None) -> str:
    # Priority: provided_email (if valid) -> PAGERDUTY_FALLBACK_FROM_EMAIL -> SENDER_EMAIL
    fallback_chain = [
        os.getenv("PAGERDUTY_FALLBACK_FROM_EMAIL"),
        os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")
    ]

    # If provided email looks valid and is a PD user, use it
    if provided_email and not _is_placeholder_email(provided_email):
        if _validate_pd_user_email(session, provided_email):
            logger.info(f"Using provided PagerDuty requester email: {provided_email}")
            return provided_email
        else:
            logger.warning(f"Provided from_email is not a valid PagerDuty user: {provided_email}. Will try fallbacks.")

    # Try fallbacks in order
    for fb in fallback_chain:
        if fb and not _is_placeholder_email(fb) and _validate_pd_user_email(session, fb):
            logger.info(f"Using fallback PagerDuty requester email: {fb}")
            return fb

    # If all fail, raise with guidance
    raise HTTPException(status_code=500, detail=(
        "No valid PagerDuty requester email found. Set a valid PAGERDUTY_FALLBACK_FROM_EMAIL or SENDER_EMAIL environment variable to a PagerDuty user email."
    ))

def find_incident_by_number(session, incident_number: str):
    """
    Finds an incident by its number, using a cache to avoid redundant API calls.
    """
    cache_key = f"incident:{incident_number}"

    # 1. Check cache first
    cached_incident = cache_get(cache_key)
    if cached_incident:
        logger.info(f"Cache HIT for incident {incident_number}")
        return cached_incident

    # 2. If not in cache, fetch from API
    logger.info(f"Cache MISS for incident {incident_number}. Fetching from PagerDuty API.")
    try:
        for incident in session.iter_all("incidents"):
            if str(incident.get("incident_number")) == str(incident_number):
                logger.info(f"Found incident: {incident_number}")
                # 3. Save to cache with a 5-minute TTL (300 seconds)
                cache_set(cache_key, incident, ttl_seconds=300)
                return incident
        logger.warning(f"Incident {incident_number} not found")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch incidents: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch incidents: {str(e)}")

def find_incident_by_id(session, incident_id: str):
    """
    Finds an incident by its ID, using cache to avoid redundant API calls.
    """
    cache_key = f"incident_id:{incident_id}"

    # 1. Check cache first
    cached_incident = cache_get(cache_key)
    if cached_incident:
        logger.info(f"Cache HIT for incident ID {incident_id}")
        return cached_incident

    # 2. If not in cache, fetch from API
    logger.info(f"Cache MISS for incident ID {incident_id}. Fetching from PagerDuty API.")
    try:
        for incident in session.iter_all("incidents"):
            if incident.get("id") == incident_id:
                logger.info(f"Found incident by ID: {incident_id} -> #{incident.get('incident_number')}")
                # 3. Save to cache with a 5-minute TTL (300 seconds)
                cache_set(cache_key, incident, ttl_seconds=300)
                return incident
        logger.warning(f"Incident with ID {incident_id} not found")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch incident by ID: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch incident by ID: {str(e)}")

def get_tools_list():
    """Enhanced tools list including GetIncidentById"""
    return {
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
                "name": "GetIncidentById",
                "description": "Get incident details by incident ID (returns full incident data including incident number)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "incident_id": {
                            "type": "string", 
                            "description": "The PagerDuty incident ID (e.g., Q1ESFOEHYA4EUZ)"
                        }
                    },
                    "required": ["incident_id"],
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
            }
        ]
    }

# Add the new tool handler function
async def call_get_incident_by_id(req_id, args, max_retries=3):
    """Handle GetIncidentById tool calls"""
    for attempt in range(max_retries):
        try:
            loop = asyncio.get_running_loop()
            with ThreadPoolExecutor() as executor:
                def logic():
                    session = get_pagerduty_session()
                    incident = find_incident_by_id(session, args["incident_id"])
                    
                    if not incident:
                        raise HTTPException(status_code=404, detail="Incident not found")
                    
                    # Return comprehensive incident data
                    return {
                        "id": incident["id"],
                        "incident_number": incident["incident_number"], 
                        "status": incident["status"],
                        "title": incident.get("title", ""),
                        "summary": incident.get("summary", ""),
                        "description": incident.get("description", ""),
                        "urgency": incident.get("urgency", "unknown"),
                        "priority": incident.get("priority", {}).get("summary", "unknown") if incident.get("priority") else "unknown",
                        "service": incident.get("service", {}).get("summary", "unknown") if incident.get("service") else "unknown",
                        "created_at": incident.get("created_at", ""),
                        "last_status_change_at": incident.get("last_status_change_at", ""),
                        "html_url": incident.get("html_url", ""),
                        "assignments": incident.get("assignments", [])
                    }
                    
                result = await loop.run_in_executor(executor, logic)
                logger.info(f"Retrieved incident by ID: {args['incident_id']} -> #{result['incident_number']}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": json.dumps(result)}]}
                }
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed for GetIncidentById: {str(e)}")
            if attempt == max_retries - 1:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": f"Failed after {max_retries} attempts: {str(e)}"}
                }
            await asyncio.sleep(1)

@app.post("/mcp")
async def mcp_handler(request: Request):
    try:
        body = await request.json()
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id", None)

        logger.info(f"MCP Request received: method={method}, id={req_id}, params={params}")

        if method == "initialize":
            logger.info("Processing initialize request")
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
                "result": None
            }
        elif method == "tools/list":
            logger.info("Processing tools/list request")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": get_tools_list()
            }
        elif method == "tools/call":
            tool = params.get("name")
            args = params.get("arguments", {})
            logger.info(f"Processing tools/call request: tool={tool}, args={args}")
            
            if tool == "GetIncidentStatus":
                return await call_get_incident_status(req_id, args)
            elif tool == "GetIncidentById":
                return await call_get_incident_by_id(req_id, args)
            elif tool == "AcknowledgeIncident":
                return await call_acknowledge_incident(req_id, args)
            else:
                logger.warning(f"Unknown tool requested: {tool}")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool}"}
                }
        else:
            logger.warning(f"Unknown method requested: {method}")
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

@app.get("/health")
async def health_check():
    return JSONResponse(content={"name": "pagerduty-mcp-server","status": "healthy","timestamp": datetime.utcnow().isoformat(), "version": "1.0.0"})  # 200 OK

async def call_acknowledge_incident(req_id, args):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as executor:
        try:
            def logic():
                logger.info(f"AcknowledgeIncident args received: {args}")
                session = get_pagerduty_session()
                email = _resolve_requester_email(session, args.get("from_email"))
                incident = find_incident_by_number(session, args["incident_number"])
                if not incident:
                    raise HTTPException(status_code=404, detail="Incident not found")
                if incident["status"] == "resolved":
                    logger.info(f"Incident {incident['incident_number']} is already resolved. No action taken.")
                    return {
                        "status": "already_resolved",
                        "incident_number": incident['incident_number'],
                        "message": "Incident is already resolved. No further action taken."
                    }
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
                # Invalidate the cache after updating the incident
                cache_delete(f"incident:{args['incident_number']}")

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

if __name__ == "__main__":
    import uvicorn
    # Add startup logging to verify our logger is working
    logger.info("Starting MCP Server on port 7006")
    logger.info("Logging configured for mcp_server.log")
    
    # Start uvicorn with our custom logging configuration
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=7006, 
        log_level="info",
        log_config=None  # Disable uvicorn's default logging config
    )