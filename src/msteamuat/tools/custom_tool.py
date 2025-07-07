# src/msteamuat/tools/custom_tool.py

import requests
import os
from typing import Annotated
from pydantic import BaseModel, Field
from typing import List
from crewai.tools import BaseTool

MCP_BASE_URL = os.getenv("MCP_SERVER_URL", "http://localhost:6006")

# --- Data models (can be reused by tasks/agents) ---
class AlertDetail(BaseModel):
    incident_number: int
    title: str
    severity: str
    metric: str
    status: str
    timestamp: str
    escalation_status: str
    escalation_reason: str

class RecommendedActions(BaseModel):
    actions: List[str] = Field(..., min_length=1, max_length=3, description="List of recommended actions")

    def format_for_email(self) -> str:
        return "\n".join([f"- {action}" for action in self.actions])

class ShiftReportOutput(BaseModel):
    subject: str
    body: str

class EmailContent(BaseModel):
    subject: str
    body: str

# --- CrewAI-compatible tools ---
class GetIncidentStatusTool(BaseTool):
    name: str = "GetIncidentStatus"
    description: str = "Fetch the status of an incident from the MCP API."

    def _run(self, data: dict) -> str:
        try:
            response = requests.post(f"{MCP_BASE_URL}/mcp/GetIncidentStatus", json=data)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Failed to get incident status: {str(e)}"

class AcknowledgeIncidentTool(BaseTool):
    name: str = "AcknowledgeIncident"
    description: str = "Acknowledge an incident via the MCP API."

    def _run(self, data: dict) -> str:
        try:
            response = requests.post(f"{MCP_BASE_URL}/mcp/AcknowledgeIncident", json=data)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Failed to acknowledge incident: {str(e)}"

class GetRelatedAlertsTool(BaseTool):
    name: str = "GetRelatedAlerts"
    description: str = "Retrieve related alerts from the MCP API using service_id and timeframe."

    def _run(self, data: dict) -> str:
        try:
            response = requests.post(f"{MCP_BASE_URL}/mcp/GetRelatedAlerts", json=data)
            response.raise_for_status()
            return response.text
        except Exception as e:
            return f"Failed to get related alerts: {str(e)}"
