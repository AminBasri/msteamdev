from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import random

app = FastAPI()

# Incident model
class Incident(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
    service: dict
    assigned_to: Optional[str] = None

# In-memory database
incidents: List[Incident] = []

# Helper function to generate a new incident ID
def generate_incident_id():
    return str(random.randint(1000, 9999))

# Create a new incident
@app.post("/incidents", response_model=Incident)
def create_incident(incident: Incident):
    incident.id = generate_incident_id()
    incident.created_at = datetime.now()
    incident.updated_at = datetime.now()
    incidents.append(incident)
    return incident

# Get a specific incident
@app.get("/incidents/{incident_id}", response_model=Incident)
def get_incident(incident_id: str):
    for incident in incidents:
        if incident.id == incident_id:
            return incident
    raise HTTPException(status_code=404, detail="Incident not found")

# Acknowledge an incident
@app.put("/incidents/{incident_id}/acknowledge", response_model=Incident)
def acknowledge_incident(incident_id: str):
    for incident in incidents:
        if incident.id == incident_id:
            incident.status = "acknowledged"
            incident.updated_at = datetime.now()
            incident.assigned_to = "current.user@example.com"  # Simulate assignment
            return incident
    raise HTTPException(status_code=404, detail="Incident not found")

# Resolve an incident
@app.put("/incidents/{incident_id}/resolve", response_model=Incident)
def resolve_incident(incident_id: str):
    for incident in incidents:
        if incident.id == incident_id:
            incident.status = "resolved"
            incident.updated_at = datetime.now()
            return incident
    raise HTTPException(status_code=404, detail="Incident not found")

# Get a list of incidents
@app.get("/incidents", response_model=List[Incident])
def get_incidents(status: Optional[str] = Query(None, description="Filter by incident status")):
    if status:
        return [incident for incident in incidents if incident.status == status]
    return incidents

# Sample data for testing
@app.on_event("startup")
def startup_event():
    incidents.append(Incident(
        id="1001",
        title="ALARM: [WARNING] High Memory Utilization",
        description="Users are experiencing 500 errors when accessing our main API endpoint.",
        priority="P2",
        status="new",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        service={"id": "P04F339", "summary": "Synergi CORE Prod"},
        assigned_to=None
    ))
    incidents.append(Incident(
        id="1002",
        title="Database Latency Spikes",
        description="Read queries are taking 2-3x longer than usual to complete.",
        priority="P1",
        status="acknowledged",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        service={"id": "P5T3R9S", "summary": "Database"},
        assigned_to="jane.doe@example.com"
    ))
    incidents.append(Incident(
        id="1003",
        title="Login Page Timeout",
        description="Users are unable to log in due to timeout errors on the auth service.",
        priority="P3",
        status="resolved",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        service={"id": "P8A2B4C", "summary": "Authentication"},
        assigned_to="john.smith@example.com"
    ))

# To run the application, use the command:
# uvicorn filename:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7006)