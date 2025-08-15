# src/msteamdev/tools/custom_tool.py

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
