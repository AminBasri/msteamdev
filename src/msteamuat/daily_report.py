import os
import json
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from crewai import Agent, Task, Crew
from msteamuat.crew import load_agents, load_yaml, check_resolution_status
from msteamuat.tools.alert_store import check_escalation_eligibility
from msteamuat.tools.custom_tool import ShiftReportOutput
from pydantic import BaseModel
import pytz

# Create a named logger for this module
logger = logging.getLogger('report')
logger.setLevel(logging.INFO)

# Avoid propagating logs to the root logger
logger.propagate = False

# Clear any existing handlers to avoid conflicts
logger.handlers.clear()

# Add FileHandler for report.log
file_handler = logging.FileHandler('/home/crewai/msteamuat/report.log')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

LOG_PATH = "src/msteamuat/alert_log.json"
LOCAL_TZ = pytz.timezone('Asia/Singapore')

def load_alerts(start_time: datetime, end_time: datetime):
    """Load alerts from the log within the specified time window, deduplicating by incident_number."""
    if not os.path.exists(LOG_PATH):
        logger.warning(f"Alert log not found at {LOG_PATH}")
        return []
    try:
        # Dictionary to store the latest alert for each incident_number
        alert_dict = {}
        with open(LOG_PATH, "r") as f:
            for line in f:
                alert = json.loads(line)
                alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                if start_time <= alert_time <= end_time:
                    incident_number = alert.get("incident_number")
                    if incident_number not in alert_dict or alert_time > datetime.fromisoformat(alert_dict[incident_number]["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc):
                        alert_dict[incident_number] = alert
        return list(alert_dict.values())
    except Exception as e:
        logger.error(f"Failed to load alerts: {e}")
        return []

def send_report_email(subject: str, body: str):
    """Send the shift report email to the NOC team."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    recipients = [email.strip() for email in os.getenv("ALERT_EMAIL_RECIPIENTS", "").split(",") if email.strip()]
    sender_name = os.getenv("SENDER_NAME", "CrewAI Reporting System")
    sender_email = os.getenv("SENDER_EMAIL", smtp_username)

    if not all([smtp_host, smtp_port, smtp_username, smtp_password, recipients]):
        logger.error("Missing SMTP configuration or recipients")
        raise ValueError("Incomplete SMTP configuration")

    msg = MIMEMultipart()
    msg['From'] = formataddr((str(Header(sender_name, 'utf-8')), sender_email))
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, recipients, msg.as_string())
            logger.info(f"Shift report emailed to {', '.join(recipients)}")
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed")
        raise
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"SMTP recipients refused: {e}")
        raise
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to send shift report email: {e}")
        raise

def run(shift_type=None):
    """Run the shift report task to summarize and email alert activity."""
    now = datetime.now(LOCAL_TZ)
    if shift_type is None:
        if 7 <= now.hour < 16:
            shift_type = "morning"
        elif 13 <= now.hour < 22:
            shift_type = "evening"
        else:
            shift_type = "morning"  # Default/fallback
    logger.info(f"Starting {shift_type} shift report generation")

    if shift_type == "morning":
        shift_start = now.replace(hour=7, minute=0, second=0, microsecond=0)
        shift_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    else:  # evening shift
        shift_start = now.replace(hour=13, minute=0, second=0, microsecond=0)
        shift_end = now.replace(hour=22, minute=0, second=0, microsecond=0)

    # If current time is before shift_start, use previous day's window
    if now < shift_start:
        shift_start -= timedelta(days=1)
        shift_end -= timedelta(days=1)

    # Convert to UTC for comparison with log timestamps
    shift_start_utc = shift_start.astimezone(timezone.utc)
    shift_end_utc = shift_end.astimezone(timezone.utc)

    alerts = load_alerts(shift_start_utc, shift_end_utc)

    agents = load_agents()
    tasks_def = load_yaml("src/msteamuat/config/tasks.yaml")
    
    reporter_agent = agents.get("reporter")
    if not reporter_agent:
        logger.error("Missing reporter agent")
        return

    # Prepare alert data for the agent
    delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
    alert_summary = []
    for alert in alerts:
        eligible, reason = check_escalation_eligibility(alert)
        was_resolved = check_resolution_status(alert, delay_minutes)
        escalation_status = "Escalated" if eligible and not was_resolved else "Not Escalated"
        
        # Convert alert timestamp to local timezone
        alert_timestamp_utc = datetime.fromisoformat(alert.get('timestamp', 'N/A').replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
        alert_timestamp_local = alert_timestamp_utc.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')

        alert_summary.append({
            "incident_number": alert.get('incident_number', 'N/A'),
            "title": alert.get('title', 'Unknown'),
            "severity": alert.get('severity', 'Unknown').upper(),
            "metric": alert.get('metric', 'Unknown'),
            "status": alert.get('status', 'Unknown'),
            "timestamp": alert_timestamp_local,
            "escalation_status": escalation_status,
            "escalation_reason": reason if not was_resolved else 'Resolved within delay period'
        })

    # Calculate counts for the agent
    alert_count = len(alerts)
    critical_count = sum(1 for a in alerts if a.get("severity") == "critical")
    warning_count = sum(1 for a in alerts if a.get("severity") == "warning")
    resolved_count = sum(1 for a in alerts if a.get("status") == "resolved")
    escalated_count = sum(1 for a in alerts if 
                         check_escalation_eligibility(a)[0] and 
                         not check_resolution_status(a, delay_minutes))

    # Format shift period for the agent
    shift_start_local = shift_start.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    shift_end_local = shift_end.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')

    # Define the task for the reporter agent to generate the email subject and body
    report_task = Task(
        description=(
            f"Generate a professional shift report email for the NOC team.\n\n"
            f"SHIFT INFORMATION:\n"
            f"- Shift period: {shift_start_local} to {shift_end_local} (+08)\n"
            f"- Shift type: {shift_type.capitalize()}\n\n"
            f"ALERT STATISTICS:\n"
            f"- Total Alerts: {alert_count}\n"
            f"- Critical Alerts: {critical_count}\n"
            f"- Warning Alerts: {warning_count}\n"
            f"- Resolved Alerts: {resolved_count}\n"
            f"- Escalated Alerts: {escalated_count}\n\n"
            f"ALERT DETAILS:\n"
            f"{json.dumps(alert_summary, indent=2) if alert_summary else 'No alerts recorded during this shift.'}\n\n"
            f"REQUIREMENTS:\n"
            f"1. Create a professional email subject that includes the shift period and type\n"
            f"2. Write a comprehensive email body that includes:\n"
            f"   - Professional greeting\n"
            f"   - Shift period and type\n"
            f"   - Summary statistics (total, critical, warning, resolved, escalated alerts)\n"
            f"   - Detailed alert information in a clear, readable format\n"
            f"   - Professional closing with instructions to review unresolved incidents\n"
            f"   - Note to contact the managed service team for issues\n"
            f"3. Use proper line breaks (\\n) for email formatting\n"
            f"4. Ensure have proper numbering or point with line breaks if using it\n"
            f"5. Keep the tone professional and informative\n"
            f"6. Signoff should be formatted as follows:\n"
            f"    Best regards\n"
            f"    CrewAI Reporting System\n"
            f"    Managed Service Team\n"
        ),
        expected_output=(
            "A structured shift report with email subject and body formatted for NOC team communication"
            "If alert details are have multiple lines, use \\n for line breaks"
        ),
        agent=reporter_agent,
        output_pydantic=ShiftReportOutput
    )

    crew = Crew(
        agents=[reporter_agent],
        tasks=[report_task],
        verbose=True
    )

    try:
        logger.info("Kicking off AI crew for shift report")
        result = crew.kickoff()
        
        # Debug logging
        logger.info(f"Crew result type: {type(result)}")
        logger.info(f"Crew result attributes: {[attr for attr in dir(result) if not attr.startswith('_')]}")
        
        # Extract the structured output using Pydantic
        try:
            subject = None
            body = None
            
            # Try to get Pydantic output first (preferred)
            if hasattr(result, 'pydantic') and result.pydantic:
                logger.info("Using Pydantic structured output")
                report_data = result.pydantic
                subject = report_data.subject
                body = report_data.body
                logger.info(f"Pydantic output - Subject: {subject[:50]}...")
                logger.info(f"Pydantic output - Body length: {len(body)}")
                
            # Fallback to JSON dict output
            elif hasattr(result, 'json_dict') and result.json_dict:
                logger.info("Using JSON dict output")
                subject = result.json_dict.get("subject")
                body = result.json_dict.get("body")
                logger.info(f"JSON dict output - Subject: {subject[:50] if subject else 'None'}...")
                logger.info(f"JSON dict output - Body length: {len(body) if body else 0}")
                
            # Last resort: try to parse raw output
            elif hasattr(result, 'raw') and result.raw:
                logger.info("Attempting to parse raw output")
                raw_output = result.raw.strip()
                logger.info(f"Raw output preview: {raw_output[:200]}...")
                
                # Try to find JSON in the raw output
                import re
                json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
                if json_match:
                    json_string = json_match.group()
                    try:
                        parsed_data = json.loads(json_string)
                        subject = parsed_data.get("subject")
                        body = parsed_data.get("body")
                        logger.info("Successfully parsed JSON from raw output")
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON from raw output: {e}")
                        
            # Validate that we have both subject and body
            if not subject or not body:
                raise ValueError(f"Missing required fields - Subject: {'✓' if subject else '✗'}, Body: {'✓' if body else '✗'}")
                
        except Exception as e:
            logger.error(f"Failed to extract structured output: {e}")
            
            # Fallback: Generate a basic report
            subject = f"📊 NOC {shift_type.capitalize()} Shift Report ({shift_start_local} - {shift_end_local} +08)"
            body = (
                f"Dear NOC Team,\n\n"
                f"This is the {shift_type} shift report for the period {shift_start_local} to {shift_end_local} (+08).\n\n"
                f"SHIFT SUMMARY:\n"
                f"- Total Alerts: {alert_count}\n"
                f"- Critical Alerts: {critical_count}\n"
                f"- Warning Alerts: {warning_count}\n"
                f"- Resolved Alerts: {resolved_count}\n"
                f"- Escalated Alerts: {escalated_count}\n\n"
            )
            
            if alert_summary:
                body += "ALERT DETAILS:\n"
                for alert in alert_summary:
                    body += (
                        f"- Incident: {alert['incident_number']}\n"
                        f"  Title: {alert['title']}\n"
                        f"  Severity: {alert['severity']}\n"
                        f"  Status: {alert['status']}\n"
                        f"  Timestamp: {alert['timestamp']}\n"
                        f"  Escalation: {alert['escalation_status']}\n"
                        f"  Reason: {alert['escalation_reason']}\n\n"
                    )
            else:
                body += "No alerts were recorded during this shift period.\n\n"
                
            body += (
                f"Please review any unresolved incidents and contact the managed service team for any issues or concerns.\n\n"
                f"Best regards,\n"
                f"CrewAI Shift Reporting System"
            )
            
            logger.warning("Using fallback report due to structured output extraction failure")

        # Send the email
        send_report_email(subject, body)
        logger.info("Shift report emailed to NOC team successfully")
        
        # Log success details
        logger.info(f"Report sent - Subject: {subject}")
        logger.info(f"Report sent - Body length: {len(body)} characters")
        
    except Exception as e:
        logger.error(f"Report generation or email failed: {e}")
        raise

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--shift", choices=["morning", "evening"], 
                       help="Shift type to generate report for")
    args = parser.parse_args()
    run(args.shift)