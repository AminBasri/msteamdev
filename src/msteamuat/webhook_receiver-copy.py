# src/msteam/webhook_receiver.py

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from msteam.crew import run_alert_pipeline
import json, os, re
import logging

app = FastAPI()
LOG_PATH = "src/msteam/alert_log.json"

def extract_severity_from_title(title: str) -> str:
    match = re.search(r"\b(Critical|Warning)\b", title, re.IGNORECASE)
    return match.group(1).lower() if match else "info"

#def extract_severity_from_metric(metric: str) -> str:
#    match = re.search(r"\b(CPU|Memory|Disk)\b", metric, re.IGNORECASE)
#    return match.group(1).lower() if match else "info"

@app.post("/pagerduty")
async def receive_alert(request: Request):
    try:
        payload = await request.json()

        # Detect and extract from array or object
        if isinstance(payload, list):
            logging.info("Payload is a list")
            # Extract event from the first item in the array, following the new structure
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

        alert = {
            "severity": extract_severity_from_title(title),
            "metric": title,
            "status": data.get("status", "unknown"),
            "timestamp": event.get("occurred_at", "unknown"),
            "incident_number": data.get("number", "unknown"),
            "title": title
        }

    except Exception as e:
        logging.error(f"Payload parsing error: {e}")
        return JSONResponse(
            content={"status": "error", "message": f"Bad format: {str(e)}"},
            status_code=400
        )

    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(alert) + "\n")
    except Exception as e:
        logging.error(f"Failed to log alert: {e}")
        return JSONResponse(
            content={"status": "error", "message": f"Failed to save alert: {str(e)}"},
            status_code=500
        )

    try:
        result = run_alert_pipeline(alert)
    except Exception as e:
        logging.error(f"Pipeline execution failed: {e}")
        return JSONResponse(
            content={"status": "error", "message": f"Processing error: {str(e)}"},
            status_code=500
        )

    return JSONResponse(content={"status": "received", "result": result})