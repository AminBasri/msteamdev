from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from msteamuat.crew import run_alert_pipeline
from crewai_tools import MCPServerAdapter
import json
import os
import re
import logging
from datetime import datetime
import hmac
import hashlib
from typing import List

app = FastAPI()
LOG_PATH = "src/msteamuat/alert_log.json"

# Configuration flags for filtering
FILTER_ENABLED = True
ALLOWED_STATUSES = ["triggered", "resolved"]

# Configure logging
logging.basicConfig(
    filename="/home/crewai/msteamuat/crew.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Initialize MCP tools
def get_mcp_tools() -> List:
    """Load MCP tools from the configured MCP server."""
    server_params = {
        "url": os.getenv("MCP_SERVER_URL", "http://10.10.6.243:5000/sse"),
        "transport": os.getenv("MCP_TRANSPORT", "sse")
    }
    try:
        with MCPServerAdapter(server_params) as mcp_tools:
            tools = list(mcp_tools)
            logging.info(f"MCP tools loaded: {[tool.name for tool in tools]}")
            return tools
    except Exception as e:
        logging.error(f"Failed to load MCP tools: {str(e)}")
        return []

def extract_severity_from_title(title: str) -> str:
    """Extract severity level from alert title."""
    match = re.search(r"\b(Critical|Warning|High|Medium|Low)\b", title, re.IGNORECASE)
    return match.group(1).lower() if match else "info"

def extract_metric_from_title(title: str) -> str:
    """Extract metric type from alert title."""
    infrastructure_patterns = [
        r"\b(CPU|Memory|Disk|Storage|Network|Bandwidth)\b",
        r"\b(Load|Latency|Response\s*Time|Throughput)\b",
        r"\b(Database|DB|MySQL|PostgreSQL|Redis)\b",
        r"\b(Apache|Nginx|HTTP|HTTPS|SSL)\b",
        r"\b(Docker|Container|Kubernetes|K8s)\b"
    ]
    application_patterns = [
        r"\b(Error\s*Rate|Exception|Crash|Failure)\b",
        r"\b(Queue|Job|Task|Worker)\b",
        r"\b(API|Service|Endpoint|Health\s*Check)\b",
        r"\b(Login|Authentication|Session)\b",
        r"\b(Payment|Transaction|Order)\b"
    ]
    business_patterns = [
        r"\b(Revenue|Sales|Conversion|User\s*Registration)\b",
        r"\b(Traffic|Visitor|Page\s*View|Click)\b"
    ]
    all_patterns = infrastructure_patterns + application_patterns + business_patterns
    
    for pattern in all_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            metric = match.group(1).lower().replace(" ", "_")
            return metric
    
    fallback_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", title)
    if fallback_match:
        return fallback_match.group(1).lower().replace(" ", "_")
    
    return "unknown"

def validate_timestamp(timestamp: str) -> bool:
    """Validate timestamp format."""
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

def should_process_alert(status: str) -> bool:
    """Determine if alert should be processed based on filtering configuration."""
    if not FILTER_ENABLED:
        return True
    return status.lower() in [s.lower() for s in ALLOWED_STATUSES]

def validate_pagerduty_signature(request: Request, payload: bytes) -> bool:
    """Validate PagerDuty webhook signature."""
    webhook_secret = os.getenv("PAGERDUTY_WEBHOOK_SECRET")
    if not webhook_secret:
        logging.error("Missing PAGERDUTY_WEBHOOK_SECRET in .env")
        return False

    signature = request.headers.get("X-PagerDuty-Signature")
    if not signature:
        logging.error("Missing X-PagerDuty-Signature header")
        return False

    # PagerDuty uses HMAC-SHA256
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    signatures = signature.split(",")
    for sig in signatures:
        if sig.startswith("v1="):
            if hmac.compare_digest(sig[3:], expected_signature):
                return True
    logging.error(f"Invalid PagerDuty signature: {signature}")
    return False

@app.post("/pagerduty")
async def receive_alert(request: Request):
    try:
        # Validate PagerDuty webhook signature
        raw_payload = await request.body()
        if not validate_pagerduty_signature(request, raw_payload):
            raise HTTPException(status_code=403, detail="Invalid PagerDuty webhook signature")

        payload = json.loads(raw_payload)
        if isinstance(payload, list):
            logging.info("Payload is a list")
            item = payload[0]
            event = item.get("body", {}).get("event")
        else:
            logging.info("Payload is a dict")
            event = payload.get("event")

        if not event:
            raise ValueError("Missing 'event' field in payload")

        data = event.get("data")
        if not data:
            raise ValueError("Missing 'data' in event")

        title = data.get("title")
        if not title:
            raise ValueError("Missing 'title' in data")

        status = data.get("status", "unknown").lower()
        occurred_at = event.get("occurred_at", "unknown")
        if not validate_timestamp(occurred_at):
            raise ValueError("Invalid timestamp format in 'occurred_at'")

        if not should_process_alert(status):
            logging.info(f"Alert with status '{status}' filtered out. Allowed statuses: {ALLOWED_STATUSES}")
            return JSONResponse(
                content={"status": "filtered", "message": f"Alert status '{status}' not in allowed list"},
                status_code=200
            )

        alert = {
            "severity": extract_severity_from_title(title),
            "metric": extract_metric_from_title(title),
            "status": status,
            "timestamp": occurred_at,
            "incident_number": data.get("number", "unknown"),
            "title": title,
            "original_metric": title
        }

        logging.info(f"Processed alert: severity={alert['severity']}, metric={alert['metric']}, status={alert['status']}")

        # Save alert to log
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(alert) + "\n")

        # Load MCP tools and pass to pipeline
        mcp_tools = get_mcp_tools()
        result = run_alert_pipeline(alert, mcp_tools)
        return JSONResponse(content={"status": "received", "result": result})

    except ValueError as ve:
        logging.error(f"Payload parsing error: {ve}")
        return JSONResponse(
            content={"status": "error", "message": f"Bad format: {str(ve)}"},
            status_code=400
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        logging.error(f"Processing error: {e}")
        return JSONResponse(
            content={"status": "error", "message": f"Processing error: {str(e)}"},
            status_code=500
        )

@app.get("/config")
async def get_config():
    """Get current filtering configuration."""
    return JSONResponse(content={
        "filter_enabled": FILTER_ENABLED,
        "allowed_statuses": ALLOWED_STATUSES
    })

@app.post("/config")
async def update_config(request: Request):
    """Update filtering configuration."""
    global FILTER_ENABLED, ALLOWED_STATUSES
    try:
        config = await request.json()
        if "filter_enabled" in config:
            FILTER_ENABLED = config["filter_enabled"]
        if "allowed_statuses" in config:
            ALLOWED_STATUSES = config["allowed_statuses"]
        logging.info(f"Configuration updated: filter_enabled={FILTER_ENABLED}, allowed_statuses={ALLOWED_STATUSES}")
        return JSONResponse(content={
            "status": "updated",
            "filter_enabled": FILTER_ENABLED,
            "allowed_statuses": ALLOWED_STATUSES
        })
    except Exception as e:
        logging.error(f"Configuration update failed: {e}")
        return JSONResponse(
            content={"status": "error", "message": f"Config update failed: {str(e)}"},
            status_code=400
        )