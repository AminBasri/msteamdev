import os
import smtplib
import logging
import re
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import Dict, Tuple
import pytz
from datetime import datetime, timezone
from crewai import Agent, Task, Crew
from msteamuat.crew import load_agents, load_yaml
from msteamuat.models import RecommendedActions, EmailContent
from functools import wraps
import time
import openlit

openlit.init()

# Create a named logger for this module
logger = logging.getLogger('notify')
logger.setLevel(logging.INFO)

# Avoid propagating logs to the root logger
logger.propagate = False

# Clear any existing handlers to avoid conflicts
logger.handlers.clear()

# Add FileHandler for notify.log
file_handler = logging.FileHandler('/home/crewai/msteamuat/log/notify.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

LOCAL_TZ = pytz.timezone('Asia/Singapore')

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

def validate_smtp_config() -> tuple[bool, str]:
    """Validate SMTP configuration."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    recipients = os.getenv("ALERT_EMAIL_RECIPIENTS", "")

    missing_configs = []
    if not smtp_host:
        missing_configs.append("SMTP_HOST")
    if not smtp_user:
        missing_configs.append("SMTP_USERNAME")
    if not smtp_pass:
        missing_configs.append("SMTP_PASSWORD")
    if not recipients.strip():
        missing_configs.append("ALERT_EMAIL_RECIPIENTS")

    if missing_configs:
        return False, f"Missing environment variables: {', '.join(missing_configs)}"

    try:
        smtp_port = int(smtp_port)
        if smtp_port <= 0 or smtp_port > 65535:
            return False, f"Invalid SMTP_PORT: {smtp_port}"
    except ValueError:
        return False, f"SMTP_PORT must be a number, got: {smtp_port}"

    return True, "SMTP configuration is valid"

def validate_rocketchat_webhook() -> tuple[bool, str]:
    """Validate Rocket.Chat webhook configuration."""
    webhook_url = os.getenv("ROCKETCHAT_WEBHOOK_URL")
    webhook_token = os.getenv("ROCKETCHAT_WEBHOOK_TOKEN")

    if not webhook_url or not webhook_token:
        return False, "Missing ROCKETCHAT_WEBHOOK_URL or ROCKETCHAT_WEBHOOK_TOKEN environment variables"
    return True, "Rocket.Chat webhook configuration is valid"

def send_rocketchat_webhook_message(message: str) -> bool:
    """Send a message to Rocket.Chat using the webhook."""
    is_valid, config_message = validate_rocketchat_webhook()
    if not is_valid:
        logger.error(f"Rocket.Chat webhook validation failed: {config_message}")
        return False

    webhook_url = os.getenv("ROCKETCHAT_WEBHOOK_URL")
    webhook_token = os.getenv("ROCKETCHAT_WEBHOOK_TOKEN")

    payload = {
        "alias": "CrewAI Alert System",
        "text": message
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            logger.info("Rocket.Chat webhook message sent successfully")
            return True
        else:
            logger.error(f"Rocket.Chat webhook failed: HTTP {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Rocket.Chat webhook message: {e}")
        return False

@retry()
def generate_recommended_actions(alert: Dict) -> RecommendedActions:
    """Generate context-specific recommended actions using CrewAI."""
    try:
        incident_number = alert.get('incident_number', 'N/A')
        agents = load_agents()
        tasks_def = load_yaml("src/msteamuat/config/tasks.yaml")
        action_recommender = agents.get("action_recommender")
        if not action_recommender:
            logger.error("Missing action_recommender agent")
            return RecommendedActions(actions=[
                f"Investigate {alert.get('metric', 'system')} usage",
                "Check running processes and services",
                "Document findings and resolution steps"
            ])

        task = Task(
            description=tasks_def["recommend_actions"]["description"].format(
                title=alert.get('title', 'Unknown'),
                severity=alert.get('severity', 'Unknown').upper(),
                metric=alert.get('metric', 'Unknown'),
                incident_number=incident_number
            ),
            expected_output=tasks_def["recommend_actions"]["expected_output"],
            agent=action_recommender,
            output_pydantic=RecommendedActions
        )
        crew = Crew(agents=[action_recommender], tasks=[task], verbose=True)
        with openlit.start_trace(name=f"Recommended_Actions_{incident_number}") as trace:
            result = crew.kickoff()
            trace.set_metadata({
                "incident_number": incident_number,
                "agent": "action_recommender"
            })
        return result.tasks_output[0].pydantic
    except Exception as e:
        logger.error(f"Failed to generate recommended actions for incident {alert.get('incident_number', 'N/A')}: {e}")
        return RecommendedActions(actions=[
            f"Investigate {alert.get('metric', 'system')} usage",
            "Check running processes and services",
            "Document findings and resolution steps"
        ])

@retry()
def generate_email_content(alert: Dict, reason: str) -> Tuple[str, str]:
    """Generate email subject and body using structured output."""
    try:
        incident_number = alert.get('incident_number', 'N/A')
        # Generate recommended actions first
        recommended_actions = generate_recommended_actions(alert)
        actions_text = recommended_actions.format_for_email()

        agents = load_agents()
        tasks_def = load_yaml("src/msteamuat/config/tasks.yaml")
        communicator_agent = agents.get("communicator")
        if not communicator_agent:
            logger.error("Missing communicator agent")
            return format_alert_email(alert, reason, actions_text)

        task = Task(
            description=tasks_def["notify_bau"]["description"].format(
                title=alert.get('title', 'Unknown'),
                severity=alert.get('severity', 'Unknown').upper(),
                metric=alert.get('metric', 'Unknown'),
                incident_number=incident_number,
                reason=reason,
                recommended_actions=actions_text
            ),
            expected_output=tasks_def["notify_bau"]["expected_output"],
            agent=communicator_agent,
            output_pydantic=EmailContent
        )
        crew = Crew(agents=[communicator_agent], tasks=[task], verbose=True)
        with openlit.start_trace(name=f"Email_Content_{incident_number}") as trace:
            result = crew.kickoff()
            trace.set_metadata({
                "incident_number": incident_number,
                "agent": "communicator"
            })
        
        # Access structured output directly
        if result.pydantic:
            email_content = result.pydantic
            return email_content.subject, email_content.body
        else:
            logger.warning("No structured output available, falling back to raw parsing")
            return format_alert_email(alert, reason, actions_text)
            
    except Exception as e:
        logger.error(f"Failed to generate email content for incident {alert.get('incident_number', 'N/A')}: {e}")
        return format_alert_email(alert, reason, actions_text)

def format_alert_email(alert: Dict, reason: str, recommended_actions: str) -> tuple[str, str]:
    """Generate fallback email content with recommended actions."""
    alert_timestamp_utc = datetime.fromisoformat(alert.get('timestamp', 'N/A').replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    alert_timestamp_local = alert_timestamp_utc.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    subject = f"{alert['title']} - {alert['severity'].capitalize()} Alert"
    body = (
        f"Dear Team,\n\n"
        f"A {alert['severity'].capitalize()} alert has been triggered:\n\n"
        f"- Incident Number: {alert.get('incident_number', 'N/A')}\n"
        f"- Severity: {alert['severity'].capitalize()}\n"
        f"- Metric: {alert.get('metric', 'Unknown')}\n"
        f"- Timestamp: {alert_timestamp_local} (+08)\n"
        f"- Reason: {reason}\n"
        f"- Recommended Actions:\n{recommended_actions}\n\n"
        f"Please investigate immediately to prevent disruptions.\n\n"
        f"Best regards,\n"
        f"CrewAI Alert Management System\n"
        f"Managed Service Team"
    )
    return subject, body

def format_rocketchat_webhook_message(alert: Dict, reason: str, recommended_actions: str) -> str:
    """Format alert message for Rocket.Chat webhook."""
    alert_timestamp_utc = datetime.fromisoformat(alert.get('timestamp', 'N/A').replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    alert_timestamp_local = alert_timestamp_utc.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    return (
        f"**{alert['title']} - {alert['severity'].capitalize()} Alert**\n\n"
        f"- Incident Number: {alert.get('incident_number', 'N/A')}\n"
        f"- Severity: {alert['severity'].capitalize()}\n"
        f"- Metric: {alert.get('metric', 'Unknown')}\n"
        f"- Timestamp: {alert_timestamp_local} (+08)\n"
        f"- Reason: {reason}\n"
        f"- Recommended Actions:\n{recommended_actions}\n\n"
        f"Please investigate immediately to prevent disruptions."
    )

def send_notification(alert: Dict, reason: str) -> str:
    """Send email and Rocket.Chat webhook notification for alert escalation."""
    logger.info(f"Starting notification for incident #{alert.get('incident_number', 'N/A')}")
    try:
        # Validate SMTP configuration
        is_valid_smtp, smtp_message = validate_smtp_config()
        if not is_valid_smtp:
            logger.error(f"SMTP configuration validation failed: {smtp_message}")
            raise ValueError(f"SMTP configuration error: {smtp_message}")

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        recipients = [email.strip() for email in os.getenv("ALERT_EMAIL_RECIPIENTS", "").split(",") if email.strip()]
        sender_name = os.getenv("SENDER_NAME", "CrewAI Escalation Alert System")
        sender_email = os.getenv("ALERT_EMAIL_RECIPIENTS", smtp_user)

        logger.info(f"SMTP Config - Host: {smtp_host}, Port: {smtp_port}, User: {smtp_user}")
        logger.info(f"Recipients: {len(recipients)} addresses")

        # Generate email content
        recommended_actions = generate_recommended_actions(alert)
        actions_text = recommended_actions.format_for_email()
        subject, body = generate_email_content(alert, reason)

        # Send email
        msg = MIMEMultipart()
        msg["From"] = formataddr((str(Header(sender_name, 'utf-8')), sender_email))
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, recipients, msg.as_string())
                logger.info(f"Email notification sent successfully to {len(recipients)} recipients")
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed")
            raise
        except smtplib.SMTPException as se:
            logger.error(f"SMTP error: {se}")
            raise

        # Send Rocket.Chat webhook notification
        rocketchat_message = format_rocketchat_webhook_message(alert, reason, actions_text)
        if send_rocketchat_webhook_message(rocketchat_message):
            logger.info(f"Rocket.Chat webhook notification sent successfully for incident #{alert.get('incident_number', 'N/A')}")
        else:
            logger.warning("Rocket.Chat webhook notification failed, but email was sent")

        return f"Notifications sent successfully: email to {len(recipients)} recipients, Rocket.Chat webhook message sent"
    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
        raise
    except Exception as e:
        logger.error(f"Failed to send notifications: {e}")
        raise

def test_smtp_connection() -> bool:
    """Test SMTP connection without sending an email."""
    try:
        is_valid, config_message = validate_smtp_config()
        if not is_valid:
            logger.error(f"Invalid configuration: {config_message}")
            return False

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")

        logger.info(f"Testing SMTP connection to {smtp_host}:{smtp_port}")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            logger.info("SMTP connection test successful")
            return True
    except Exception as e:
        logger.error(f"SMTP connection test failed: {e}")
        return False

def test_rocketchat_webhook() -> bool:
    """Test Rocket.Chat webhook connection with a test message."""
    try:
        is_valid, config_message = validate_rocketchat_webhook()
        if not is_valid:
            logger.error(f"Invalid Rocket.Chat webhook configuration: {config_message}")
            return False

        test_message = "This is a test message from CrewAI Alert System"
        return send_rocketchat_webhook_message(test_message)
    except Exception as e:
        logger.error(f"Rocket.Chat webhook test failed: {e}")
        return False

if __name__ == "__main__":
    test_smtp_connection()
    test_rocketchat_webhook()