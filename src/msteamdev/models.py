# src/msteamdev/models.py

import os
from typing import Annotated, List, Optional
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

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
    category: Optional[str] = None
    priority: Optional[str] = None
    suspected_root_cause: Optional[str] = None
    problem_id: Optional[str] = None
    # Timing fields for KPIs
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    first_response_at: Optional[str] = None
    last_update_at: Optional[str] = None
    sla_breach_at: Optional[str] = None

class AlertMatchCriteria(
    BaseModel
):
    """Schema for matching alerts.
    At least one field must be provided.
    """
    title: Optional[str] = Field(default=None, description="Title to match.")
    severity: Optional[str] = Field(default=None, description="Severity to match.")
    metric: Optional[str] = Field(default=None, description="Metric to match.")
    status: Optional[str] = Field(default=None, description="Status to match.")

class GetMatchingAlertsInput(
    BaseModel
):
    """Input for GetMatchingAlerts tool."""
    alert: AlertMatchCriteria = Field(..., description="The alert criteria to match against.")

class SimpleRecommendedActions(BaseModel):
    actions: List[str] = Field(..., min_length=1, max_length=3, description="List of recommended actions")

    def format_for_email(self) -> str:
        return "\n".join([f"- {action}" for action in self.actions])

class ReportMetadata(BaseModel):
    """Only essential ITIL-relevant metadata"""
    generation_timestamp: str = Field(..., description="Timestamp when the report was generated (UTC).")
    alert_count: int = Field(default=0, description="Total number of alerts in the report period")
    critical_alerts: int = Field(default=0, description="Number of critical alerts")
    sla_breaches: int = Field(default=0, description="Number of SLA breaches")
    mttr_minutes: float = Field(default=0.0, description="Mean Time To Resolve in minutes")

class ShiftReportOutput(
    BaseModel
):
    subject: str
    body: str
    metadata: Optional[ReportMetadata] = Field(None, description="Metadata about the report generation and data quality.")

class EmailContent(
    BaseModel
):
    subject: str
    body: str

# Enhanced models for new task structure
class TriageAssessment(BaseModel):
    """Assessment from triage agent."""
    priority_score: int = Field(..., ge=1, le=5, description="Priority score 1-5")
    alert_category: str = Field(..., description="Alert category (infrastructure, application, etc.)")
    business_impact: str = Field(..., description="Business impact assessment")
    pattern_analysis: str = Field(..., description="Pattern analysis results")
    recommended_next_actions: List[str] = Field(..., description="Next recommended actions")
    confidence_level: int = Field(..., ge=1, le=10, description="Confidence in assessment")

class TechnicalAction(BaseModel):
    """Individual technical action."""
    description: str = Field(..., description="Action description")
    priority_level: int = Field(..., ge=1, le=5, description="Priority level")
    estimated_time_minutes: int = Field(..., description="Estimated time to complete in minutes")
    required_tools: List[str] = Field(default=[], description="Required tools/access")
    success_criteria: str = Field(..., description="Success criteria")

class RecommendedActions(
    BaseModel
):
    actions: List[TechnicalAction] = Field(..., min_length=2, max_length=4, description="List of technical actions")
    
    def format_for_email(self) -> str:
        formatted = []
        for i, action in enumerate(self.actions, 1):
            formatted.append(f"{i}. {action.description}")
            formatted.append(f"   • Priority: {action.priority_level}/5")
            formatted.append(f"   • Est. Time: {action.estimated_time_minutes} min")
            if action.required_tools:
                formatted.append(f"   • Tools needed: {', '.join(action.required_tools)}")
            formatted.append(f"   • Success criteria: {action.success_criteria}")
            formatted.append("")
        return "\n".join(formatted)

class EscalationDecision(BaseModel):
    """Escalation decision from escalation checker."""
    decision: str = Field(..., pattern="^(ESCALATE|SUPPRESS)$", description="Escalation decision")
    confidence_level: int = Field(..., ge=1, le=10, description="Confidence level 1-10")
    detailed_reasoning: str = Field(..., description="Detailed reasoning for decision")
    risk_assessment: str = Field(..., description="Risk assessment if not escalated")
    escalation_target: Optional[str] = Field(None, description="Recommended escalation target")
    business_hours_factor: bool = Field(..., description="Whether business hours were considered")
    suppression_window_checked: bool = Field(..., description="Whether suppression window was checked")

class ShiftHandoverProtocol(BaseModel):
    """Ensures complete knowledge transfer for shift handover."""
    required_sections: List[str] = Field(
        default=[
            "EXECUTIVE SUMMARY",
            "KEY PERFORMANCE INDICATORS",
            "ACTIVE INCIDENTS (HANDOVER)",
            "RESOLVED INCIDENTS (DURING SHIFT)",
            "RISK ASSESSMENT",
            "HANDOVER INFORMATION",
            "DATA QUALITY INDICATORS"
        ],
        description="List of required sections for a complete handover report."
    )

    def validate_completeness(self, report_body: str) -> tuple[bool, List[str]]:
        """Verify all required sections are present in the report body."""
        missing = []
        report_body_upper = report_body.upper()
        for section in self.required_sections:
            if section not in report_body_upper:
                missing.append(section)
        return len(missing) == 0, missing

class IncidentManagementResult(BaseModel):
    """Result from PagerDuty incident management."""
    incident_id: str = Field(..., description="PagerDuty incident ID")
    current_status: str = Field(..., description="Current incident status")
    acknowledgment_performed: bool = Field(..., description="Whether acknowledgment was performed")
    acknowledgment_result: Optional[str] = Field(None, description="Result of acknowledgment if performed")
    api_interactions: List[str] = Field(default=[], description="Summary of API interactions")
    errors: List[str] = Field(default=[], description="Any errors encountered")
    next_actions: List[str] = Field(default=[], description="Recommended next actions")
    cache_updated: bool = Field(..., description="Whether cache was updated")