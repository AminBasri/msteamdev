# src/msteamuat/crew.py

import os
import yaml
from threading import Timer
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from functools import wraps
import time
import logging
import asyncio
import json
import re
from crewai import Agent, Task, Crew
from msteamuat.llm import get_llm
from msteamuat.tools.alert_store import check_escalation_eligibility, _load_log
from crewai_tools import MCPServerAdapter
from src.msteamuat.tools.custom_tool import (
    GetIncidentStatusTool,
    AcknowledgeIncidentTool,
    GetRelatedAlertsTool
)


load_dotenv()

# Configure logging
logger = logging.getLogger('crew')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

# Add FileHandler for crew.log
file_handler = logging.FileHandler('/home/crewai/msteamuat/crew.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

# Track scheduled escalations to prevent duplicates
scheduled_escalations = set()

def retry(max_attempts=3, delay=2):
    """Retry decorator for CrewAI tasks."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
                    logger.warning(f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}")
        return wrapper
    return decorator

def load_yaml(path):
    """Load YAML configuration file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)

mcp_tools = [
    GetIncidentStatusTool(),
    AcknowledgeIncidentTool(),
    GetRelatedAlertsTool()
]

def load_agents(mcp_tools=None):
    """Load agents from YAML, ensuring valid BaseTool instances for pagerduty_manager."""
    agent_def = load_yaml("src/msteamuat/config/agents.yaml")
    llm = get_llm()
    agents = {}
    for name, cfg in agent_def.items():
        tools = cfg.get("tools", [])
        if name == "pagerduty_manager" and mcp_tools:
            # Filter valid BaseTool instances
            tools = mcp_tools
            logger.info(f"Assigned tools to pagerduty_manager: {[tool.name for tool in tools]}")
        agents[name] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            verbose=True,
            llm=llm,
            tools=tools
        )
    return agents

def load_tasks():
    """Load tasks from YAML."""
    return load_yaml("src/msteamuat/config/tasks.yaml")

def check_resolution_status(alert: dict, delay_minutes: int) -> bool:
    """Check if an alert with the same incident number has resolved status within the delay period."""
    alerts = _load_log()
    incident_number = alert.get("incident_number")
    current_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
    cutoff_time = current_time + timedelta(minutes=delay_minutes)

    for logged_alert in alerts:
        alert_time = datetime.fromisoformat(logged_alert["timestamp"].replace("Z", "+00:00"))
        if (logged_alert["incident_number"] == incident_number and 
            logged_alert["status"] == "resolved" and 
            current_time <= alert_time <= cutoff_time):
            return True
    return False

async def check_and_acknowledge_alert_task(alert: dict, mcp_tools: list):
    """Check incident status after delay and acknowledge if triggered."""
    delay_minutes = int(os.getenv("ACKNOWLEDGMENT_DELAY_MINUTES", "5"))
    delay_seconds = delay_minutes * 60
    logger.info(f"Scheduling acknowledgment check for incident {alert['incident_number']} in {delay_seconds} seconds")
    await asyncio.sleep(delay_seconds)

    pagerduty_manager = load_agents(mcp_tools).get("pagerduty_manager")
    tasks_def = load_tasks()
    
    if not pagerduty_manager:
        logger.error("Missing pagerduty_manager agent")
        return {"status": "error", "message": "Missing pagerduty_manager agent"}

    acknowledge_task = Task(
        description=tasks_def["check_and_acknowledge_alert"]["description"].format(
            incident_number=alert["incident_number"]
        ),
        expected_output=tasks_def["check_and_acknowledge_alert"]["expected_output"],
        agent=pagerduty_manager,
        tools=[tool for tool in mcp_tools if hasattr(tool, "name") and tool.name in [
            "GetIncidentStatus", "AcknowledgeIncident", "GetRelatedAlerts"
        ]]
    )

    try:
        result = pagerduty_manager.execute_task(acknowledge_task)
        logger.info(f"Acknowledgment task result for incident {alert['incident_number']}: {result}")

        # Sanitize result string for JSON parsing
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", result, re.DOTALL)
        if match:
            cleaned_result = match.group(1).strip()
            parsed_result = json.loads(cleaned_result)
        else:
            logger.error("❌ JSON block not found in agent response.")
            return {"status": "error", "message": "No valid JSON block found in agent result"}

        try:
            parsed_result = json.loads(cleaned_result)
            return parsed_result
        except json.JSONDecodeError as decode_error:
            logger.error(f"❌ Failed to parse JSON from agent response: {decode_error} — Cleaned Result: {cleaned_result}")
            return {"status": "error", "message": "Invalid JSON returned from agent"}
    except Exception as e:
        logger.error(f"Error in acknowledgment task for incident {alert['incident_number']}: {str(e)}")
        return {"status": "error", "message": str(e)}

@retry()
def run_alert_pipeline(alert: dict, mcp_tools: list):
    """Run the alert pipeline, scheduling acknowledgment and escalation if needed."""
    try:
        incident_number = alert["incident_number"]
        if incident_number in scheduled_escalations:
            logger.info(f"Alert {incident_number} already scheduled for escalation, skipping")
            return {"status": "skipped", "message": f"Alert {incident_number} already scheduled"}

        occurred_at = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
        delay = (occurred_at + timedelta(minutes=delay_minutes)) - now
        seconds = max(0, delay.total_seconds())
        logger.info(f"⏱ Holding alert {incident_number} for {int(seconds)} seconds before escalation decision")

        # Schedule 5-minute acknowledgment check
        asyncio.create_task(check_and_acknowledge_alert_task(alert, mcp_tools))

        # Check if alert resolved within escalation delay
        if check_resolution_status(alert, delay_minutes):
            logger.info(f"✅ Alert with incident #{incident_number} resolved within {delay_minutes} minutes")
            return {"status": "resolved", "message": f"Alert resolved within {delay_minutes} minutes, escalation canceled"}

        # Schedule escalation pipeline
        scheduled_escalations.add(incident_number)
        Timer(seconds, run_escalation_pipeline, args=[alert, mcp_tools]).start()
        return {
            "status": "scheduled",
            "message": f"Alert {incident_number} scheduled for evaluation in {int(seconds)} seconds",
            "acknowledgment_scheduled": True
        }

    except Exception as e:
        logger.error(f"Error in run_alert_pipeline for incident {alert['incident_number']}: {str(e)}")
        return {"status": "error", "message": str(e)}

@retry()
def run_escalation_pipeline(alert: dict, mcp_tools: list):
    """Run the escalation pipeline, deciding whether to escalate and notify."""
    incident_number = alert["incident_number"]
    logger.info(f"⏰ Escalation pipeline triggered for incident {incident_number}")
    from msteamuat.tools.notify import send_notification

    try:
        delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
        if check_resolution_status(alert, delay_minutes):
            logger.info(f"✅ Alert with incident #{incident_number} resolved before escalation")
            scheduled_escalations.discard(incident_number)
            return {"status": "resolved", "message": f"Alert resolved, escalation canceled"}

        agents = load_agents(mcp_tools)
        tasks_def = load_tasks()
        escalation_agent = agents.get("escalation_checker")
        communicator_agent = agents.get("communicator")

        if not escalation_agent or not communicator_agent:
            logger.error("Missing required agents")
            scheduled_escalations.discard(incident_number)
            return {"status": "error", "message": "Missing required agents"}

        eligible, reason = check_escalation_eligibility(alert)
        logger.info(f"🧪 Policy check for incident {incident_number}: {eligible}, Reason: {reason}")

        context = (
            f"Alert Title: {alert['title']}\n"
            f"Severity: {alert['severity']}\n"
            f"Occurred At: {alert['timestamp']}\n"
            f"Metric: {alert['metric']}\n"
            f"Incident #: {incident_number}\n\n"
            f"Policy Result: {eligible} - {reason}\n"
            f"Should this alert be escalated to BAU?"
        )

        escalation_task = Task(
            description=tasks_def["evaluate_escalation"]["description"] + "\n\n" + context,
            expected_output=tasks_def["evaluate_escalation"]["expected_output"],
            agent=escalation_agent
        )

        notification_task = Task(
            description=tasks_def["notify_bau"]["description"] + "\n\nAlert Details:\n" + context + "\n\nIf escalation is required, compose a message and prepare for email.",
            expected_output=tasks_def["notify_bau"]["expected_output"],
            agent=communicator_agent,
            context=[escalation_task]
        )

        crew = Crew(
            agents=[escalation_agent, communicator_agent],
            tasks=[escalation_task, notification_task],
            verbose=True
        )

        logger.info(f"🧠 Kicking off AI crew for escalation and notification of incident {incident_number}")
        result = crew.kickoff()
        comm_response = str(result.raw or "")
        logger.info(f"🤖 Crew execution completed with result: {comm_response}")

        escalation_keywords = ["yes", "escalate", "send", "notify", "proceed", "approved", "urgent", "critical"]
        found_keywords = [kw for kw in escalation_keywords if kw in comm_response.lower()]
        logger.info(f"🔍 Keywords found: {found_keywords}")

        should_send_email = len(found_keywords) > 0

        if should_send_email or eligible:
            try:
                send_notification(alert, reason)
                logger.info(f"✅ Email sent to BAU for incident {incident_number}")
                scheduled_escalations.discard(incident_number)
                return {"status": "escalated", "message": "Email sent to BAU successfully"}
            except Exception as email_error:
                logger.error(f"❌ Failed to send email for incident {incident_number}: {email_error}")
                scheduled_escalations.discard(incident_number)
                return {"status": "error", "message": f"Failed to send email: {str(email_error)}"}
        else:
            logger.info(f"ℹ️ Escalation not approved for incident {incident_number} by AI and policy check failed")
            scheduled_escalations.discard(incident_number)
            return {"status": "suppressed", "message": "Escalation not approved, no email sent"}

    except Exception as e:
        logger.error(f"💥 Crew execution failed for incident {incident_number}: {e}")
        if eligible:
            logger.info(f"⚠️ Crew failed but policy indicates escalation needed for incident {incident_number}")
            try:
                send_notification(alert, f"Crew execution failed but policy indicates escalation: {reason}")
                logger.info(f"✅ Fallback email sent for incident {incident_number}")
                scheduled_escalations.discard(incident_number)
                return {"status": "escalated", "message": "Fallback email sent successfully"}
            except Exception as fallback_error:
                logger.error(f"❌ Fallback email failed for incident {incident_number}: {fallback_error}")
                scheduled_escalations.discard(incident_number)
                return {"status": "error", "message": f"Fallback email failed: {str(fallback_error)}"}
        scheduled_escalations.discard(incident_number)
        return {"status": "error", "message": f"Crew execution failed: {str(e)}"}