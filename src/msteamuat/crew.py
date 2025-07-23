# src/msteamuat/crew.py

import os
import sys
import yaml
from threading import Thread
from datetime import datetime, timedelta, timezone
from functools import wraps
import time
import logging
import asyncio
import json
import re
import requests
from crewai import Agent, Task, Crew
from msteamuat.llm import get_llm
from msteamuat.tools.alert_store import check_escalation_eligibility, _load_log, get_matching_alerts
from crewai.tools import tool
from pdpyras import APISession

# Configure logging
class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush() # Ensure each write is flushed
    def flush(self) :
        for f in self.files:
            f.flush()

# Create a log directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'log')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'crew.log')

# Create a log file and Tee object
log_file = open(log_file_path, 'a')
original_stdout = sys.stdout
original_stderr = sys.stderr
sys.stdout = Tee(original_stdout, log_file)
sys.stderr = Tee(original_stderr, log_file)

logger = logging.getLogger('crew')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

# Add FileHandler for crew.log
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler(original_stdout)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:6006/mcp")
from_email = os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")


# Tool Implementation using direct HTTP requests
@tool("GetIncidentStatus")
def get_incident_status(incident_number: str) -> str:
    """
    Get the status of a PagerDuty incident by incident number.
    Input should be the incident number as a string.
    """
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "GetIncidentStatus", "arguments": {"incident_number": incident_number}},
        "id": "1"
    }
    try:
        response = requests.post(MCP_SERVER_URL, json=jsonrpc_request, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"GetIncidentStatus tool failed: {e}")
        return f"Error calling MCP server: {e}"

@tool("AcknowledgeIncident")
def acknowledge_incident(incident_number: str, from_email: str) -> str:
    """
    Acknowledge a PagerDuty incident.
    Input should be the incident number and the email of the user acknowledging the incident.
    """
    valid_from_email = os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "AcknowledgeIncident", "arguments": {"incident_number": incident_number, "from_email": valid_from_email}},
        "id": "2"
    }
    try:
        response = requests.post(MCP_SERVER_URL, json=jsonrpc_request, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"AcknowledgeIncident tool failed: {e}")
        return f"Error calling MCP server: {e}"


def get_mcp_tools() -> list:
    """Load MCP tools."""
    logger.info("Loading MCP tools...")
    mcp_tools = [get_incident_status, acknowledge_incident, get_matching_alerts]
    logger.info("Successfully loaded MCP tools.")
    return mcp_tools

def retry(max_attempts=3, delay=2):
    """Retry decorator for CrewAI tasks, supporting both sync and async functions."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    await asyncio.sleep(delay * (2 ** attempt))
                    logger.warning(f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}")

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
                    logger.warning(f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}")

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

def get_pagerduty_session():
    token = os.getenv("PAGERDUTY_API_TOKEN")
    if not token:
        logger.critical("PAGERDUTY_API_TOKEN environment variable is not set")
        raise ValueError("Missing PagerDuty API token")
    return APISession(token)

def find_incident_by_number(session, incident_number: str):
    logger.debug(f"Searching for incident number: {incident_number}")
    try:
        for incident in session.iter_all("incidents"):
            if str(incident.get("incident_number")) == str(incident_number):
                logger.info(f"Found incident: {incident_number}")
                return incident
        logger.warning(f"Incident {incident_number} not found")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch incidents: {str(e)}")
        raise

def get_user_email_from_pagerduty(user_id: str) -> str | None:
    """Fetches a user's email from PagerDuty API given their user ID."""
    try:
        session = get_pagerduty_session()
        user = session.rget(f"/users/{user_id}")
        if user and user.get("email"):
            logger.info(f"Found email {user['email']} for user ID {user_id}")
            return user["email"]
        logger.warning(f"Email not found for user ID {user_id}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch email for user ID {user_id}: {str(e)}")
        return None

def load_yaml(path):
    """Load YAML configuration file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_agents(mcp_tools=None):
    """Load agents from YAML."""
    agent_def = load_yaml("src/msteamuat/config/agents.yaml")
    agents = {}
    for name, cfg in agent_def.items():
        llm = get_llm()
        tools = []
        if name == "pagerduty_manager" and mcp_tools:
            tools = mcp_tools
            logger.info("Assigned MCP tools to pagerduty_manager")

        agents[name] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            verbose=True,
            llm=llm,
            tools=tools
        )
    logger.debug(f"Loaded agents: {list(agents.keys())}")
    return agents

def load_tasks():
    """Load tasks from YAML."""
    return yaml.safe_load(open("src/msteamuat/config/tasks.yaml", "r"))

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

async def check_and_acknowledge_alert_task(alert: dict, mcp_tools: list, max_retries=3):
    """Check incident status after delay and acknowledge if triggered."""
    delay_minutes = int(os.getenv("ACKNOWLEDGMENT_DELAY_MINUTES", "1"))
    delay_seconds = delay_minutes * 60
    logger.info(f"Scheduling acknowledgment check for incident {alert['incident_number']} in {delay_seconds} seconds")
    await asyncio.sleep(delay_seconds)

    try:
        agents = load_agents(mcp_tools)
        pagerduty_manager = agents.get("pagerduty_manager")
        tasks_def = load_tasks()

        if not pagerduty_manager:
            logger.error("Missing pagerduty_manager agent")
            raise ValueError("Missing pagerduty_manager agent")
        
        if not mcp_tools:
            raise ValueError("MCP tools not available.")

        logger.debug(f"PagerDuty Manager Agent: role={pagerduty_manager.role}")

        task_description = tasks_def["check_and_acknowledge_alert"]["description"].format(
            incident_number=alert["incident_number"],
            from_email=alert.get("from_email", "noramin@infopro.com.my")
        )
        logger.debug(f"Task description: {task_description}")

        acknowledge_task = Task(
            description=task_description,
            expected_output=tasks_def["check_and_acknowledge_alert"]["expected_output"],
            agent=pagerduty_manager,
            tools=mcp_tools,
            async_execution=True
        )

        for attempt in range(max_retries):
            try:
                result = await asyncio.to_thread(pagerduty_manager.execute_task, acknowledge_task)
                
                logger.debug(f"Task output for incident {alert['incident_number']}: {result}")
                logger.info(f"Raw acknowledgment task result for incident {alert['incident_number']}: {result}")
                
                # The result is expected to be a string, not JSON.
                # We return it directly if it's a string, otherwise, we log an error.
                if isinstance(result, str):
                    # Attempt to find a JSON object within the string, if not, handle as plain text
                    try:
                        json_match = re.search(r'\{.*\}', result, re.DOTALL)
                        if json_match:
                            parsed_result = json.loads(json_match.group(0))
                            return parsed_result
                        else:
                            # If no JSON, return the raw string in a structured dict
                            return {"status": "success", "message": result}
                    except json.JSONDecodeError:
                        return {"status": "success", "message": result} # Return raw string if not JSON
                else:
                    logger.error(f"Task output is not a string for incident {alert['incident_number']}: {result}")
                    return {"status": "error", "message": "Task output is not a string", "raw_response": result}

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed for incident {alert['incident_number']}: {str(e)}")
                if attempt == max_retries - 1:
                    logger.error(f"Max retries reached for incident {alert['incident_number']}")
                    raise
                await asyncio.sleep(2 ** attempt)

    except Exception as e:
        logger.error(f"Acknowledgment task via MCP failed for incident {alert['incident_number']}: {str(e)}. Attempting direct PagerDuty API call.")
        try:
            session = get_pagerduty_session()
            incident = find_incident_by_number(session, alert["incident_number"])
            if not incident:
                logger.error(f"Incident {alert['incident_number']} not found via direct API")
                return {"status": "error", "message": f"Incident {alert['incident_number']} not found"}
            
            result_payload = {
                "incident_number": alert["incident_number"],
                "status": incident["status"],
                "acknowledgment": "skipped",
                "related_alerts": []
            }
            if incident["status"] == "triggered":
                session.rput(
                    f"/incidents/{incident['id']}",
                    json={"incident": {"type": "incident_reference", "status": "acknowledged"}},
                    headers={"From": alert.get("from_email", "noramin@infopro.com.my")}
                )
                verified = find_incident_by_number(session, alert["incident_number"])
                result_payload["acknowledgment"] = "success" if verified and verified["status"] == "acknowledged" else "failed"
            logger.info(f"Direct API result for incident {alert['incident_number']}: {result_payload}")
            return result_payload
        except Exception as api_e:
            logger.error(f"Direct PagerDuty API call also failed for incident {alert['incident_number']}: {str(api_e)}")
            return {"status": "error", "message": str(api_e)}


@retry()
async def run_escalation_pipeline(alert: dict, mcp_tools: list):
    """Run the escalation pipeline, deciding whether to escalate and notify."""
    incident_number = alert["incident_number"]
    logger.info(f"⏰ Escalation pipeline triggered for incident {incident_number}")
    from msteamuat.tools.notify import send_notification

    eligible = False
    reason = ""
    try:
        delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "3"))
        if check_resolution_status(alert, delay_minutes):
            logger.info(f"✅ Alert with incident #{incident_number} resolved before escalation")
            scheduled_escalations.discard(incident_number)
            return {"status": "resolved", "message": "Alert resolved, escalation canceled"}

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
            verbose=True,
            telemetry=False
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

async def _run_alert_pipeline_async(alert: dict, mcp_tools: list = None):
    """The core async pipeline logic."""
    mcp_tools = mcp_tools or get_mcp_tools()
    try:
        incident_number = alert["incident_number"]
        if incident_number in scheduled_escalations:
            logger.info(f"Alert {incident_number} already scheduled for escalation, skipping")
            return

        occurred_at = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "3"))
        delay = (occurred_at + timedelta(minutes=delay_minutes)) - now
        seconds = max(0, delay.total_seconds())
        
        logger.info(f"⏱ Holding alert {incident_number} for {int(seconds)} seconds before escalation decision")

        if alert["status"] == "triggered":
            asyncio.create_task(check_and_acknowledge_alert_task(alert, mcp_tools))
            logger.info(f"⏳ Scheduled acknowledgment check for incident {incident_number}")
        else:
            logger.info(f"✅ Alert #{incident_number} is already resolved. Skipping acknowledgment scheduling.")

        await asyncio.sleep(seconds)

        if check_resolution_status(alert, delay_minutes):
            logger.info(f"✅ Alert with incident #{incident_number} resolved within {delay_minutes} minutes")
            return

        scheduled_escalations.add(incident_number)
        await run_escalation_pipeline(alert, mcp_tools)

    except Exception as e:
        logger.error(f"Error in _run_alert_pipeline_async for incident {alert.get('incident_number', 'N/A')}: {str(e)}")

def _run_pipeline_in_background(alert: dict):
    """Helper to run the async pipeline in a new event loop in a new thread."""
    logger.info(f"Starting background processing for incident {alert.get('incident_number', 'N/A')}")
    asyncio.run(_run_alert_pipeline_async(alert))

def start_alert_pipeline(alert: dict):
    """
    Synchronous entry point to start the alert pipeline in a background thread.
    This should be called from the webhook receiver.
    """
    thread = Thread(target=_run_pipeline_in_background, args=(alert,))
    thread.daemon = True
    thread.start()
    logger.info(f"Webhook received. Handed off incident {alert.get('incident_number', 'N/A')} to background processor.")
    return {"status": "processing_started"}

# Track scheduled escalations to prevent duplicates
scheduled_escalations = set()

if __name__ == "__main__":
    alert = {
        "incident_number": "133",
        "title": "Test Alert",
        "severity": "critical",
        "timestamp": "2025-07-16T19:02:06Z",
        "metric": "Server Down",
        "status": "triggered",
        "from_email": "noramin@infopro.com.my"
    }
    print("Running pipeline directly for testing...")
    asyncio.run(_run_alert_pipeline_async(alert))
    print("Pipeline test run finished.")