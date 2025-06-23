import os
import smtplib
import logging
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import Dict
import pytz
from datetime import datetime
from crewai import Agent, Task, Crew
from pydantic import BaseModel, Field
from msteamuat.crew import load_agents, load_yaml

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/crewai/msteamuat/notify.log'),
        logging.StreamHandler()
    ]
)

LOCAL_TZ = pytz.timezone('Asia/Singapore')  # +08 time zone

# Pydantic model for recommended actions
class RecommendedActions(BaseModel):
    actions: list[str] = Field(..., min_items=1, max_items=3, description="List of recommended actions")

def validate_smtp_config() -> tuple[bool, str]:
    """Validate SMTP configuration and return status with message."""
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

def generate_recommended_actions(alert: Dict) -> RecommendedActions:
    """Generate context-specific recommended actions using CrewAI."""
    try:
        agents = load_agents()
        tasks_def = load_yaml("src/msteamuat/config/tasks.yaml")

        action_recommender = agents.get("action_recommender")
        if not action_recommender:
            logging.error("Missing action_recommender agent")
            return RecommendedActions(actions=[
                "Investigate the root cause immediately",
                "Check system health and performance metrics",
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
        logging.error(f"Failed to generate recommended actions: {e}")
        return RecommendedActions(actions=[
            "Investigate the root cause immediately",
            "Check system health and performance metrics",
            "Document findings and resolution steps"
        ])

def generate_email_content(alert: dict, reason: str) -> tuple[str, str]:
    """Generate email subject and body using the communicator agent."""
    try:
        agents = load_agents()
        tasks_def = load_yaml("src/msteamuat/config/tasks.yaml")

        communicator_agent = agents.get("communicator")
        if not communicator_agent:
            logging.error("Missing communicator agent")
            return "Default Subject", "Default Body"

        task = Task(
            description=tasks_def["compose_email"]["description"].format(
                title=alert.get('title', 'Unknown'),
                severity=alert.get('severity', 'Unknown').upper(),
                metric=alert.get('metric', 'Unknown'),
                incident_number=alert.get('incident_number', 'N/A'),
                reason=reason
            ),
            expected_output=tasks_def["compose_email"]["expected_output"],
            agent=communicator_agent
        )

        crew = Crew(agents=[communicator_agent], tasks=[task], verbose=True)
        result = crew.kickoff()

        # Extract the raw output and clean it
        raw_output = result.tasks_output[0].raw

        # Remove any extraneous formatting characters like backticks
        if raw_output.startswith("```json"):
            raw_output = raw_output[len("```json"):]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-len("```")]

        # Trim any leading or trailing whitespace
        raw_output = raw_output.strip()

        # Parse the cleaned JSON output
        result_data = json.loads(raw_output)
        subject = result_data.get("subject", "Default Subject")
        body = result_data.get("body", "Default Body")

        return subject, body
    except Exception as e:
        logging.error(f"Failed to generate email content: {e}")
        return "Default Subject", "Default Body"

def format_alert_email(alert: Dict, reason: str) -> tuple[str, str]:
    """Format the email subject and body based on alert details using the communicator agent."""
    return generate_email_content(alert, reason)

def send_notification(alert: dict, reason: str) -> str:
    """Send email notification for alert escalation."""
    logging.info(f"Starting email notification for incident #{alert.get('incident_number', 'N/A')}")

    try:
        # Validate configuration
        is_valid, config_message = validate_smtp_config()
        if not is_valid:
            logging.error(f"SMTP configuration validation failed: {config_message}")
            raise ValueError(f"SMTP configuration error: {config_message}")

        # Get configuration
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        recipients = [email.strip() for email in os.getenv("ALERT_EMAIL_RECIPIENTS", "").split(",") if email.strip()]
        sender_name = os.getenv("SENDER_NAME", "CrewAI Escalation Alert System")
        sender_email = os.getenv("SENDER_EMAIL", smtp_user)

        logging.info(f"SMTP Config - Host: {smtp_host}, Port: {smtp_port}, User: {smtp_user}")
        logging.info(f"Recipients: {len(recipients)} addresses")

        # Format email content using the communicator agent
        subject, body = format_alert_email(alert, reason)

        logging.debug(f"Email subject: {subject}")
        logging.debug(f"Email body length: {len(body)}")

        # Create email message
        msg = MIMEMultipart()
        msg["From"] = formataddr((str(Header(sender_name, 'utf-8')), sender_email))
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        # Send email
        logging.info("Connecting to SMTP server...")
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                logging.info("Connected to SMTP server, starting TLS...")
                server.starttls()
                logging.info("Authenticating with SMTP server...")
                server.login(smtp_user, smtp_pass)
                logging.info(f"Sending email to {len(recipients)} recipients...")
                server.sendmail(smtp_user, recipients, msg.as_string())
                success_message = f"Email notification sent successfully to {len(recipients)} recipients"
                logging.info(success_message)
                return success_message
        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP authentication failed: {str(e)}"
            logging.error(error_msg)
            raise Exception(error_msg)
        except smtplib.SMTPRecipientsRefused as e:
            error_msg = f"SMTP recipients refused: {str(e)}"
            logging.error(error_msg)
            raise Exception(error_msg)
        except smtplib.SMTPServerDisconnected as e:
            error_msg = f"SMTP server disconnected: {str(e)}"
            logging.error(error_msg)
            raise Exception(error_msg)
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error occurred: {str(e)}"
            logging.error(error_msg)
            raise Exception(error_msg)
    except ValueError as ve:
        logging.error(f"Configuration error: {str(ve)}")
        raise
    except Exception as e:
        error_msg = f"Failed to send email notification: {str(e)}"
        logging.error(error_msg, exc_info=True)
        raise Exception(error_msg)

def test_smtp_connection() -> bool:
    """Test SMTP connection without sending an email."""
    try:
        is_valid, config_message = validate_smtp_config()
        if not is_valid:
            print(f"Invalid configuration: {config_message}")
            return False

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")

        print(f"Testing SMTP connection to {smtp_host}:{smtp_port}...")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            print("SMTP connection test successful!")
            return True
    except Exception as e:
        print(f"SMTP connection test failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("Testing SMTP configuration...")
    test_smtp_connection()

    print("\n" + "="*50)
    print("TESTING CRITICAL ALERT")
    print("="*50)
    critical_alert = {
        "title": "Test Alert - High Disk Utilization",
        "severity": "CRITICAL",
        "timestamp": "2025-06-11T10:30:00Z",
        "metric": "disk.utilization",
        "incident_number": "CRIT-001"
    }
    subject, body = format_alert_email(critical_alert, "Critical alert")
    print(f"Critical alert subject: {subject}")
    print(f"Critical alert body preview:\n{body[:400]}...")

    print("\n" + "="*50)
    print("TESTING WARNING ALERT")
    print("="*50)
    warning_alert = {
        "title": "Test Alert - Memory Usage",
        "severity": "WARNING",
        "timestamp": "2025-06-11T10:45:00Z",
        "metric": "memory.utilization",
        "incident_number": "WARN-001"
    }
    subject, body = format_alert_email(warning_alert, "Warning alert")
    print(f"Warning alert subject: {subject}")
    print(f"Warning alert body preview:\n{body[:400]}...")

    print("\n" + "="*50)
    print("TESTING UNKNOWN SEVERITY (FALLBACK)")
    print("="*50)
    unknown_alert = {
        "title": "Test Alert - Unknown Issue",
        "severity": "MEDIUM",
        "timestamp": "2025-06-11T11:00:00Z",
        "metric": "unknown.metric",
        "incident_number": "UNK-001"
    }
    subject, body = format_alert_email(unknown_alert, "Unknown alert")
    print(f"Unknown severity subject: {subject}")
    print(f"Unknown severity body preview:\n{body[:400]}...")