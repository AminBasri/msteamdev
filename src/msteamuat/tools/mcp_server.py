from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import pdpyras
import os

app = FastAPI()

@app.get("/sse")
async def sse_endpoint():
    async def stream():
        yield "data: {\"tools\": [\"GetIncidentStatus\", \"AcknowledgeIncident\", \"GetRelatedAlerts\"]}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream")

@app.post("/mcp/GetIncidentStatus")
async def get_incident_status(data: dict):
    session = pdpyras.APISession(os.getenv("PAGERDUTY_API_TOKEN"))
    incident_id = data.get("incident_number")
    response = session.get(f"/incidents/{incident_id}")
    return {"status": response.json()["incident"]["status"]}

@app.post("/mcp/AcknowledgeIncident")
async def acknowledge_incident(data: dict):
    session = pdpyras.APISession(os.getenv("PAGERDUTY_API_TOKEN"))
    incident_id = data.get("incident_number")
    session.rput(
        f"/incidents/{incident_id}",
        json={"incident": {"type": "incident_reference", "status": "acknowledged"}},
        headers={"From": os.getenv("SENDER_EMAIL")}
    )
    return {"result": f"Incident {incident_id} acknowledged"}