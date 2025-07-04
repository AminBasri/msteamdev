from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import pdpyras
import os
import logging
import json
import asyncio

# Configure logging
logging.basicConfig(
    filename="/home/crewai/msteamuat/mcp_server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

app = FastAPI()

# Pydantic models for request validation
class IncidentRequest(BaseModel):
    incident_number: str
    from_email: str = os.getenv("SENDER_EMAIL", "noc@example.com")

class RelatedAlertsRequest(BaseModel):
    service_id: str
    start_time: str  # ISO 8601 format
    end_time: str    # ISO 8601 format

# Initialize PagerDuty API session
def get_pagerduty_session():
    api_token = os.getenv("PAGERDUTY_API_TOKEN")
    if not api_token:
        logging.error("Missing PAGERDUTY_API_TOKEN")
        raise HTTPException(status_code=500, detail="Missing PagerDuty API token")
    return pdpyras.APISession(api_token)

@app.get("/sse")
async def sse_endpoint():
    async def stream():
        tools = {
            "tools": [
                "GetIncidentStatus",
                "AcknowledgeIncident",
                "GetRelatedAlerts"
            ]
        }
        yield f"data: {json.dumps(tools)}\n\n"
        # Keep connection alive with periodic pings
        while True:
            yield "data: {\"event\": \"ping\"}\n\n"
            await asyncio.sleep(30)
    logging.info("Serving /sse endpoint")
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/mcp/GetIncidentStatus")
async def get_incident_status(data: IncidentRequest):
    try:
        session = get_pagerduty_session()
        response = session.get(f"/incidents/{data.incident_number}")
        if response.status_code != 200:
            logging.error(f"Failed to get status for incident {data.incident_number}: {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Failed to get incident status")
        status = response.json()["incident"]["status"]
        logging.info(f"Retrieved status for incident {data.incident_number}: {status}")
        return {"status": status}
    except Exception as e:
        logging.error(f"Error in GetIncidentStatus: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mcp/AcknowledgeIncident")
async def acknowledge_incident(data: IncidentRequest):
    try:
        session = get_pagerduty_session()
        response = session.rput(
            f"/incidents/{data.incident_number}",
            json={"incident": {"type": "incident_reference", "status": "acknowledged"}},
            headers={"From": data.from_email}
        )
        if response.status_code != 200:
            logging.error(f"Failed to acknowledge incident {data.incident_number}: {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Failed to acknowledge incident")
        logging.info(f"Acknowledged incident {data.incident_number}")
        return {"result": f"Incident {data.incident_number} acknowledged"}
    except Exception as e:
        logging.error(f"Error in AcknowledgeIncident: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mcp/GetRelatedAlerts")
async def get_related_alerts(data: RelatedAlertsRequest):
    try:
        session = get_pagerduty_session()
        response = session.get(
            "/incidents",
            params={
                "service_ids[]": data.service_id,
                "since": data.start_time,
                "until": data.end_time
            }
        )
        if response.status_code != 200:
            logging.error(f"Failed to get related alerts for service {data.service_id}: {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Failed to get related alerts")
        incidents = response.json()["incidents"]
        alerts = [
            {
                "incident_number": inc["id"],
                "title": inc["title"],
                "status": inc["status"],
                "created_at": inc["created_at"]
            }
            for inc in incidents
        ]
        logging.info(f"Retrieved {len(alerts)} related alerts for service {data.service_id}")
        return {"content": [{"text": json.dumps(alerts)}]}
    except Exception as e:
        logging.error(f"Error in GetRelatedAlerts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)