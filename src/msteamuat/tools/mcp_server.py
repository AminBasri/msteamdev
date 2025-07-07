from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import pdpyras
import os
import logging
import json
import asyncio

app = FastAPI()

# Logging
logging.basicConfig(
    filename="/home/crewai/msteamuat/mcp_server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Request models
class IncidentRequest(BaseModel):
    incident_number: str
    from_email: str = os.getenv("SENDER_EMAIL", "noc@example.com")

class RelatedAlertsRequest(BaseModel):
    service_id: str
    start_time: str  # ISO 8601 format
    end_time: str    # ISO 8601 format

# PagerDuty API
def get_pagerduty_session():
    api_token = os.getenv("PAGERDUTY_API_TOKEN")
    if not api_token:
        logging.error("Missing PAGERDUTY_API_TOKEN")
        raise HTTPException(status_code=500, detail="Missing PagerDuty API token")
    return pdpyras.APISession(api_token)

def find_incident_by_number(session, incident_number: str):
    try:
        for incident in session.iter_all("incidents"):
            if str(incident.get("incident_number")) == str(incident_number):
                return incident
        return None
    except Exception as e:
        logging.error(f"Error finding incident: {e}")
        raise HTTPException(status_code=500, detail="Failed to find incident by number")

# SSE tool list for CrewAI
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
        while True:
            yield "data: {\"event\": \"ping\"}\n\n"
            await asyncio.sleep(30)
    logging.info("Serving /sse endpoint")
    return StreamingResponse(stream(), media_type="text/event-stream")

# Get incident status
@app.post("/mcp/GetIncidentStatus")
async def get_incident_status(data: IncidentRequest):
    try:
        session = get_pagerduty_session()
        incident = find_incident_by_number(session, data.incident_number)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {
            "id": incident["id"],
            "incident_number": incident["incident_number"],
            "status": incident["status"]
        }
    except Exception as e:
        logging.error(f"Error in GetIncidentStatus: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Acknowledge incident
@app.post("/mcp/AcknowledgeIncident")
async def acknowledge_incident(data: IncidentRequest):
    try:
        session = get_pagerduty_session()
        incident = find_incident_by_number(session, data.incident_number)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        incident_id = incident["id"]
        incident_number = incident["incident_number"]

        # Perform the acknowledge operation
        result = session.rput(
            f"/incidents/{incident_id}",
            json={"incident": {"type": "incident_reference", "status": "acknowledged"}},
            headers={"From": data.from_email}
        )

        logging.info(f"Acknowledged incident {incident_number}")
        return {
            "result": f"Incident #{incident_number} acknowledged successfully",
            "id": incident_id,
            "incident_number": incident_number,
            "ack_response": result  # helpful for debugging or confirmation
        }

    except pdpyras.PDClientError as e:
        logging.error(f"PagerDuty API error: {e}")
        raise HTTPException(status_code=500, detail=f"PagerDuty API error: {e}")
    except Exception as e:
        logging.error(f"Error in AcknowledgeIncident: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Related alerts
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
                "id": inc["id"],
                "incident_number": inc["incident_number"],
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

# Run locally
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=6006)
