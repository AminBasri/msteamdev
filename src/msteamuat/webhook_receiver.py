from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from msteamuat.crew import run_alert_pipeline
import json
import os
import re
import logging
from datetime import datetime

app = FastAPI()
LOG_PATH = "src/msteamuat/alert_log.json"

# Configuration flags for filtering
FILTER_ENABLED = True
ALLOWED_STATUSES = ["triggered", "resolved"]

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

@app.post("/pagerduty")
async def receive_alert(request: Request):
    try:
        payload = await request.json()
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

        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(alert) + "\n")

        result = run_alert_pipeline(alert)
        return JSONResponse(content={"status": "received", "result": result})

    except ValueError as ve:
        logging.error(f"Payload parsing error: {ve}")
        return JSONResponse(
            content={"status": "error", "message": f"Bad format: {str(ve)}"},
            status_code=400
        )
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