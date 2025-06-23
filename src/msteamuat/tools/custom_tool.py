from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import List

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
    actions: List[str] = Field(..., min_items=1, max_items=3, description="List of recommended actions")

    def format_for_email(self) -> str:
        """Format the recommended actions as a string for inclusion in email content."""
        return "\n".join([f"- {action}" for action in self.actions])

class ShiftReportOutput(BaseModel):
    subject: str
    body: str

class EmailContent(BaseModel):
    subject: str
    body: str