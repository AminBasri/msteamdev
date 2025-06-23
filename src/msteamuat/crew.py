import os
import yaml
from threading import Timer
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from functools import wraps
import time
import logging

from crewai import Agent, Task, Crew
from msteamuat.llm import get_llm
from msteamuat.tools.alert_store import check_escalation_eligibility, _load_log

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/crewai/msteamuat/crew.log'),
        logging.StreamHandler()
    ]
)

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
                    logging.warning(f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}")
        return wrapper
    return decorator

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_agents():
    agent_def = load_yaml("src/msteamuat/config/agents.yaml")
    llm = get_llm()
    return {
        name: Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            verbose=True,
            llm=llm,
        )
        for name, cfg in agent_def.items()
    }

def load_tasks():
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

@retry()
def run_alert_pipeline(alert: dict):
    """Run the alert pipeline, scheduling escalation if needed."""
    occurred_at = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
    delay = (occurred_at + timedelta(minutes=delay_minutes)) - now
    seconds = max(0, delay.total_seconds())
    logging.info(f"⏱ Holding alert {int(seconds)} seconds before escalation decision")

    if check_resolution_status(alert, delay_minutes):
        logging.info(f"✅ Alert with incident #{alert.get('incident_number')} resolved within {delay_minutes} minutes")
        return f"Alert resolved within {delay_minutes} minutes, escalation canceled"

    Timer(seconds, run_escalation_pipeline, args=[alert]).start()
    return f"⏱ Alert scheduled for evaluation in {int(seconds)} seconds"

@retry()
def run_escalation_pipeline(alert: dict):
    """Run the escalation pipeline, deciding whether to escalate and notify."""
    logging.info("⏰ Escalation pipeline triggered")
    from msteamuat.tools.notify import send_notification

    delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
    if check_resolution_status(alert, delay_minutes):
        logging.info(f"✅ Alert with incident #{alert.get('incident_number')} resolved before escalation")
        return f"Alert resolved, escalation canceled"

    agents = load_agents()
    tasks_def = load_tasks()
    escalation_agent = agents.get("escalation_checker")
    communicator_agent = agents.get("communicator")

    if not escalation_agent or not communicator_agent:
        logging.error("Missing required agents")
        return "Missing required agents"

    eligible, reason = check_escalation_eligibility(alert)
    logging.info(f"🧪 Policy check: {eligible}, Reason: {reason}")

    context = (
        f"Alert Title: {alert['title']}\n"
        f"Severity: {alert['severity']}\n"
        f"Occurred At: {alert['timestamp']}\n"
        f"Metric: {alert['metric']}\n"
        f"Incident #: {alert.get('incident_number')}\n\n"
        f"Policy Result: {eligible} - {reason}\n"
        f"Should this alert be escalated to BAU?"
    )

    escalation_task = Task(
        description=tasks_def["evaluate_escalation"]["description"] + "\n\n" + context,
        expected_output=tasks_def["evaluate_escalation"]["expected_output"],
        agent=escalation_agent,
    )

    notification_task = Task(
        description=tasks_def["notify_bau"]["description"] + "\n\nAlert Details:\n" + context + "\n\nIf escalation is required, compose a message and prepare for email.",
        expected_output=tasks_def["notify_bau"]["expected_output"],
        agent=communicator_agent,
        context=[escalation_task],
    )

    crew = Crew(
        agents=[escalation_agent, communicator_agent],
        tasks=[escalation_task, notification_task],
        verbose=True,
    )

    try:
        logging.info("🧠 Kicking off AI crew for escalation and notification")
        result = crew.kickoff()
        comm_response = str(result.raw or "")
        logging.info(f"🤖 Crew execution completed with result:\n{comm_response}")

        escalation_keywords = ["yes", "escalate", "send", "notify", "proceed", "approved", "urgent", "critical"]
        found_keywords = [kw for kw in escalation_keywords if kw in comm_response.lower()]
        logging.info(f"🔍 Keywords found: {found_keywords}")

        should_send_email = len(found_keywords) > 0

        if should_send_email or eligible:
            try:
                send_notification(alert, reason)
                logging.info("✅ Email sent to BAU successfully")
            except Exception as email_error:
                logging.error(f"❌ Failed to send email: {email_error}")
                raise
        else:
            logging.info("ℹ️ Escalation not approved by AI and policy check failed")
            return "Escalation not approved, no email sent"

    except Exception as e:
        logging.error(f"💥 Crew execution failed: {e}")
        if eligible:
            logging.info("⚠️ Crew failed but policy indicates escalation needed")
            try:
                send_notification(alert, f"Crew execution failed but policy indicates escalation: {reason}")
                logging.info("✅ Fallback email sent successfully")
            except Exception as fallback_error:
                logging.error(f"❌ Fallback email failed: {fallback_error}")
                raise
        raise