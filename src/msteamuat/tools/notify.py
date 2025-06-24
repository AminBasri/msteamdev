import os
import smtplib
import logging
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import Dict, Tuple
import pytz
from datetime import datetime
from crewai import Agent, Task, Crew
from msteamuat.crew import load_agents, load_yaml
from msteamuat.tools.custom_tool import RecommendedActions, EmailContent
from functools import wraps
import time

# Create a named logger for this module
logger = logging.getLogger('notify')
logger.setLevel(logging.INFO)

# Avoid propagating logs to the root logger
logger.propagate = False

# Clear any existing handlers to avoid conflicts
logger.handlers.clear()

# Add FileHandler for notify.log
file_handler = logging.FileHandler('/home/crewai/msteamuat/notify.log')
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

@retry()
def generate_recommended_actions(alert: Dict) -> RecommendedActions:
    """Generate context-specific recommended actions using CrewAI."""
    try:
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
                incident_number=alert.get('incident_number', 'N/A')
            ),
            expected_output=tasks_def["recommend_actions"]["expected_output"],
            agent=action_recommender,
            output_pydantic=RecommendedActions
        )
        crew = Crew(agents=[action_recommender], tasks=[task], verbose=True)
        result = crew.kickoff()
        return result.tasks_output[0].pydantic
    except Exception as e:
        logger.error(f"Failed to generate recommended actions: {e}")
        return RecommendedActions(actions=[
            f"Investigate {alert.get('metric', 'system')} usage",
            "Check running processes and services",
            "Document findings and resolution steps"
        ])

@retry()
def generate_email_content(alert: Dict, reason: str) -> Tuple[str, str]:
    """Generate email subject and body using structured output."""
    try:
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
                incident_number=alert.get('incident_number', 'N/A'),
                reason=reason,
                recommended_actions=actions_text
            ),
            expected_output=tasks_def["notify_bau"]["expected_output"],
            agent=communicator_agent,
            output_pydantic=EmailContent
        )
        crew = Crew(agents=[communicator_agent], tasks=[task], verbose=True)
        result = crew.kickoff()
        
        # Access structured output directly
        if result.pydantic:
            email_content = result.pydantic
            return email_content.subject, email_content.body
        else:
            logger.warning("No structured output available, falling back to raw parsing")
            return format_alert_email(alert, reason, actions_text)
            
    except Exception as e:
        logger.error(f"Failed to generate email content: {e}")
        return format_alert_email(alert, reason, actions_text)

def format_alert_email(alert: Dict, reason: str, recommended_actions: str) -> tuple[str, str]:
    """Generate fallback email content with recommended actions."""
    subject = f"{alert['title']} - {alert['severity'].capitalize()} Alert"
    body = (
        f"Dear Team,\n\n"
        f"A {alert['severity'].capitalize()} alert has been triggered:\n\n"
        f"- Incident Number: {alert.get('incident_number', 'N/A')}\n"
        f"- Severity: {alert['severity'].capitalize()}\n"
        f"- Metric: {alert.get('metric', 'Unknown')}\n"
        f"- Reason: {reason}\n"
        f"- Recommended Actions:\n{recommended_actions}\n\n"
        f"Please investigate immediately to prevent disruptions.\n\n"
        f"Best regards,\n"
        f"CrewAI Alert Management System\n"
        f"Managed Service Team"
    )
    return subject, body

def send_notification(alert: Dict, reason: str) -> str:
    """Send email notification for alert escalation."""
    logger.info(f"Starting email notification for incident #{alert.get('incident_number', 'N/A')}")
    try:
        is_valid, config_message = validate_smtp_config()
        if not is_valid:
            logger.error(f"SMTP configuration validation failed: {config_message}")
            raise ValueError(f"SMTP configuration error: {config_message}")

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        recipients = [email.strip() for email in os.getenv("ALERT_EMAIL_RECIPIENTS", "").split(",")
                      if email.strip()]
        sender_name = os.getenv("SENDER_NAME", "CrewAI Escalation Alert System")
        sender_email = os.getenv("SENDER_EMAIL", smtp_user)

        logger.info(f"SMTP Config - Host: {smtp_host}, Port: {smtp_port}, User: {smtp_user}")
        logger.info(f"Recipients: {len(recipients)} addresses")

        subject, body = generate_email_content(alert, reason)
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
                success_message = f"Email notification sent successfully to {len(recipients)} recipients"
                logger.info(success_message)
                return success_message
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed")
            raise
        except smtplib.SMTPException as se:
            logger.error(f"SMTP error: {se}")
            raise
    except ValueError as ve:
        logger.error(f"Configuration error: {ve}")
        raise
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}")
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

if __name__ == "__main__":
    test_smtp_connection()