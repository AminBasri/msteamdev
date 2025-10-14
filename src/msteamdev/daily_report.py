import os
import json
import logging
import smtplib
import requests
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from crewai import Agent, Task, Crew
from msteamdev.crew import load_agents, load_yaml
from msteamdev.tools.alert_store import load_log_sync, _load_log as _load_log_sync

def check_resolution_status_sync(alert: dict, delay_minutes: int) -> bool:
    """Synchronous version of check_resolution_status."""
    alerts = _load_log_sync()
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

# Use the sync version
check_resolution_status = check_resolution_status_sync
from msteamdev.tools.intelligent_policy import intelligent_escalation_policy
from msteamdev.tools.knowledge_base import find_similar_incidents
from msteamdev.tools.enhanced_tools import (
    read_alert_log_enhanced,
    get_alert_trends
)
from msteamdev.models import (
    ShiftReportOutput,
    AlertDetail,
    AlertMatchCriteria,
    GetMatchingAlertsInput,
    AlertMatchCriteria,
    GetMatchingAlertsInput
)
from pydantic import BaseModel
import pytz
import re

from msteamdev.logging_setup import get_module_logger

# Centralized named logger for this module
logger = get_module_logger('report', log_filename='report.log', level=logging.INFO)

LOG_PATH = "src/msteamdev/alert_log.json"
LOCAL_TZ = pytz.timezone('Asia/Singapore')

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
        "alias": "CrewAI Shift Reporting System",
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

def format_rocketchat_webhook_report(subject: str, body: str) -> str:
    """Format shift report for Rocket.Chat webhook."""
    # Remove email-specific greeting and signoff, adapt for Rocket.Chat
    body_lines = body.split("\n")
    filtered_body = [line for line in body_lines if not line.startswith("Dear NOC Team") and not line.startswith("Best regards") and not line.startswith("CrewAI") and not line.startswith("Managed Service Team")]
    return f"**{subject}**\n\n" + "\n".join(filtered_body)

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
    """Send the shift report email and Rocket.Chat webhook message to the NOC team."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    recipients = [email.strip() for email in os.getenv("REPORT_EMAIL", "").split(",") if email.strip()]
    sender_name = os.getenv("SENDER_NAME", "CrewAI Reporting System")
    sender_email = os.getenv("REPORT_EMAIL", smtp_username)

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

    # Send to Rocket.Chat webhook
    rocketchat_message = format_rocketchat_webhook_report(subject, body)
    if send_rocketchat_webhook_message(rocketchat_message):
        logger.info("Shift report sent to Rocket.Chat webhook successfully")
    else:
        logger.warning("Failed to send shift report to Rocket.Chat webhook, but email was sent")

def run(shift_type=None, shift_start=None, shift_end=None):
    """Run the shift report task to summarize and email alert activity."""
    now = datetime.now(LOCAL_TZ)
    if shift_type == "weekly":
        pass
    elif shift_type is None:
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
    elif shift_type == "evening":  # evening shift
        shift_start = now.replace(hour=13, minute=0, second=0, microsecond=0)
        shift_end = now.replace(hour=22, minute=0, second=0, microsecond=0)

    # If current time is before shift_start, use previous day's window
    if shift_type != "weekly" and now < shift_start:
        shift_start -= timedelta(days=1)
        shift_end -= timedelta(days=1)

    # Convert to UTC for comparison with log timestamps
    shift_start_utc = shift_start.astimezone(timezone.utc)
    shift_end_utc = shift_end.astimezone(timezone.utc)

    alerts = load_alerts(shift_start_utc, shift_end_utc)

    agents = load_agents()
    tasks_def = load_yaml("src/msteamdev/config/tasks_enhanced.yaml")
    
    reporter_agent = agents.get("reporter")
    if not reporter_agent:
        logger.error("Missing reporter agent")
        return

    report_task_def = tasks_def.get("shift_report")
    if not report_task_def:
        logger.error("Missing shift_report task definition")
        return

    # Prepare alert data using enhanced tools
    delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
    
    # Initialize lists for active and resolved incidents
    active_incidents = []
    resolved_incidents = []
    
    # Get enhanced data with fallback to basic processing
    try:
        # For now, overall service health is not directly derived from CrewAI internal health.
        # It will be generated by the agent based on alert data and trends.
        overall_service_health_summary = "Summary of overall service health will be provided by the agent."

        for alert in alerts:
            # Use enhanced escalation eligibility check
            escalation_result = json.loads(intelligent_escalation_policy.run(json.dumps(alert)))
            
            was_resolved = check_resolution_status(alert, delay_minutes)
            escalation_status = "Escalated" if escalation_result["eligible"] and not was_resolved else "Not Escalated"
            
            # Get pattern analysis for this type of alert
            pattern_analysis = json.loads(find_similar_incidents._run(
                alert_title=alert.get("title"),
                alert_severity=alert.get("severity"),
                alert_metric=alert.get("metric")
            ))
            
            # Convert alert timestamp to local timezone
            alert_timestamp_utc = datetime.fromisoformat(alert.get('timestamp', 'N/A').replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
            alert_timestamp_local = alert_timestamp_utc.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
            
            # Infer category and priority (simplified for now, can be enhanced with more tools)
            category = "Unknown"
            priority = "P3" # Default to P3 (Medium)
            if "cpu" in alert.get("metric", "").lower() or "memory" in alert.get("metric", "").lower():
                category = "Performance"
            elif "down" in alert.get("title", "").lower() or "unavailable" in alert.get("title", "").lower():
                category = "Availability"
            
            if alert.get("severity", "").lower() == "critical":
                priority = "P1"
            elif alert.get("severity", "").lower() == "high":
                priority = "P2"
            elif alert.get("severity", "").lower() == "warning":
                priority = "P3"
            else:
                priority = "P4" # Low
            
            # Infer suspected root cause and problem ID (simplified for now)
            suspected_root_cause = pattern_analysis.get("resolution_patterns", "No clear pattern identified.")
            problem_id = pattern_analysis.get("problem_id", "N/A") # Assuming problem_id might come from pattern analysis

            # Enhanced reason with pattern analysis
            enhanced_reason = (f"{escalation_result['reason']}\n" 
                             f"Pattern Analysis: {pattern_analysis.get('total_matches', 0)} similar alerts found")

            alert_detail = AlertDetail(
                incident_number=int(alert.get('incident_number', 0)),
                title=alert.get('title', 'Unknown'),
                severity=alert.get('severity', 'Unknown').upper(),
                metric=alert.get('metric', 'Unknown'),
                status=alert.get('status', 'Unknown'),
                timestamp=alert_timestamp_local,
                escalation_status=escalation_status,
                escalation_reason=enhanced_reason if not was_resolved else 'Resolved within delay period',
                category=category,
                priority=priority,
                suspected_root_cause=suspected_root_cause,
                problem_id=problem_id
            )
            
            if alert_detail.status.lower() in ["triggered", "acknowledged"]:
                active_incidents.append(alert_detail)
            elif alert_detail.status.lower() == "resolved":
                resolved_incidents.append(alert_detail)

    except Exception as e:
        logger.error(f"Failed to process alerts with enhanced tools: {e}")
        # Fallback to basic alert processing
        overall_service_health_summary = "Overall Service Health: Unknown (Failed to retrieve system health)"
        for alert in alerts:
            try:
                # Basic alert processing
                policy_result_str = intelligent_escalation_policy.run(json.dumps(alert))
                policy_result_dict = json.loads(policy_result_str)
                eligible = policy_result_dict.get("eligible", False)
                reason = policy_result_dict.get("reason", "")
                was_resolved = check_resolution_status(alert, delay_minutes)
                escalation_status = "Escalated" if eligible and not was_resolved else "Not Escalated"
                
                alert_timestamp_utc = datetime.fromisoformat(alert.get('timestamp', 'N/A').replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                alert_timestamp_local = alert_timestamp_utc.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')

                # Infer category and priority for fallback
                category = "Unknown"
                priority = "P3"
                if "cpu" in alert.get("metric", "").lower() or "memory" in alert.get("metric", "").lower():
                    category = "Performance"
                elif "down" in alert.get("title", "").lower() or "unavailable" in alert.get("title", "").lower():
                    category = "Availability"
                
                if alert.get("severity", "").lower() == "critical":
                    priority = "P1"
                elif alert.get("severity", "").lower() == "high":
                    priority = "P2"
                elif alert.get("severity", "").lower() == "warning":
                    priority = "P3"
                else:
                    priority = "P4"

                alert_detail = AlertDetail(
                    incident_number=int(alert.get('incident_number', 0)),
                    title=alert.get('title', 'Unknown'),
                    severity=alert.get('severity', 'Unknown').upper(),
                    metric=alert.get('metric', 'Unknown'),
                    status=alert.get('status', 'Unknown'),
                    timestamp=alert_timestamp_local,
                    escalation_status=escalation_status,
                    escalation_reason=reason if not was_resolved else 'Resolved within delay period',
                    category=category,
                    priority=priority,
                    suspected_root_cause="Fallback: Pattern analysis unavailable.",
                    problem_id="N/A"
                )
                
                if alert_detail.status.lower() in ["triggered", "acknowledged"]:
                    active_incidents.append(alert_detail)
                elif alert_detail.status.lower() == "resolved":
                    resolved_incidents.append(alert_detail)

            except Exception as inner_e:
                logger.error(f"Failed to process alert {alert.get('incident_number')}: {inner_e}")

    # Get enhanced alert trends and metrics
    try:
        trends_data = json.loads(get_alert_trends.run(hours=int((shift_end_utc - shift_start_utc).total_seconds() / 3600)))
        alert_count = trends_data["total_alerts"]
        severity_dist = trends_data["severity_distribution"]
        critical_count = severity_dist.get("critical", 0)
        warning_count = severity_dist.get("warning", 0)
        resolved_count = sum(1 for a in alerts if a.get("status") == "resolved")
        
        # Use enhanced escalation eligibility check
        escalated_count = sum(1 for a in alerts if 
                             json.loads(intelligent_escalation_policy.run(json.dumps(a)))["eligible"] and 
                             not check_resolution_status(a, delay_minutes))
    except Exception as e:
        logger.error(f"Failed to get enhanced metrics, falling back to basic counting: {e}")
        # Fallback to basic counting
        alert_count = len(alerts)
        critical_count = sum(1 for a in alerts if a.get("severity") == "critical")
        warning_count = sum(1 for a in alerts if a.get("severity") == "warning")
        resolved_count = sum(1 for a in alerts if a.get("status") == "resolved")
        escalated_count = sum(1 for a in alerts if 
                             json.loads(intelligent_escalation_policy.run(json.dumps(a)))["eligible"] and 
                             not check_resolution_status(a, delay_minutes))

    # Format shift period for the agent
    shift_start_local = shift_start.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    shift_end_local = shift_end.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')

    # Prepare the alert details string dynamically
    # Convert Pydantic models to dictionaries for JSON serialization
    active_incidents_dicts = [alert.model_dump() for alert in active_incidents]
    active_incidents_data = json.dumps(active_incidents_dicts, indent=2) if active_incidents_dicts else 'No active incidents to handover.'

    resolved_incidents_dicts = [alert.model_dump() for alert in resolved_incidents]
    resolved_incidents_data = json.dumps(resolved_incidents_dicts, indent=2) if resolved_incidents_dicts else 'No incidents resolved during this shift.'

    # Define the task for the reporter agent using the YAML template
    report_task = Task(
        description=report_task_def["description"].format(
            shift_start=shift_start_local,
            shift_end=shift_end_local,
            shift_type=shift_type.capitalize(),
            overall_service_health=overall_service_health_summary,
            total_alerts=alert_count,
            critical_alerts=critical_count,
            warning_alerts=warning_count,
            resolved_alerts=resolved_count,
            escalated_alerts=escalated_count,
            active_incidents_data=active_incidents_data,
            resolved_incidents_data=resolved_incidents_data
        ),
        expected_output=report_task_def["expected_output"],
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
            
            if active_incidents or resolved_incidents:
                body += "ACTIVE INCIDENTS TO HANDOVER:\n"
                if active_incidents:
                    for alert in active_incidents:
                        body += (
                            f"- Incident: {alert.incident_number}\n"
                            f"  Title: {alert.title}\n"
                            f"  Severity: {alert.severity}\n"
                            f"  Status: {alert.status}\n"
                            f"  Timestamp: {alert.timestamp}\n"
                            f"  Escalation: {alert.escalation_status}\n"
                            f"  Reason: {alert.escalation_reason}\n"
                            f"  Category: {alert.category}\n"
                            f"  Priority: {alert.priority}\n"
                            f"  Suspected Root Cause: {alert.suspected_root_cause}\n"
                            f"  Problem ID: {alert.problem_id}\n\n"
                        )
                else:
                    body += "No active incidents to handover.\n\n"

                body += "RESOLVED INCIDENTS DURING SHIFT:\n"
                if resolved_incidents:
                    for alert in resolved_incidents:
                        body += (
                            f"- Incident: {alert.incident_number}\n"
                            f"  Title: {alert.title}\n"
                            f"  Severity: {alert.severity}\n"
                            f"  Status: {alert.status}\n"
                            f"  Timestamp: {alert.timestamp}\n"
                            f"  Escalation: {alert.escalation_status}\n"
                            f"  Reason: {alert.escalation_reason}\n"
                            f"  Category: {alert.category}\n"
                            f"  Priority: {alert.priority}\n"
                            f"  Suspected Root Cause: {alert.suspected_root_cause}\n"
                            f"  Problem ID: {alert.problem_id}\n\n"
                        )
                else:
                    body += "No incidents resolved during this shift.\n\n"
            else:
                body += "No alerts were recorded during this shift period.\n\n"
                
            body += (
                f"Overall Service Health: {overall_service_health}\n\n"
                f"Please review any unresolved incidents and contact the managed service team for any issues or concerns.\n\n"
                f"Best regards,\n"
                f"CrewAI Shift Reporting System"
            )
            
            logger.warning("Using fallback report due to structured output extraction failure")

        # Send the email and Rocket.Chat webhook message
        send_report_email(subject, body)
        logger.info("Shift report emailed to NOC team and sent to Rocket.Chat webhook successfully")
        
        # Log success details
        logger.info(f"Report sent - Subject: {subject}")
        logger.info(f"Report sent - Body length: {len(body)} characters")
        
    except Exception as e:
        logger.error(f"Report generation or notification failed: {e}")
        raise

def run_weekly_report():
    """Run the weekly report task."""
    now = datetime.now(LOCAL_TZ)
    # Go back to the last Monday
    start_of_last_week = now - timedelta(days=now.weekday() + 7)
    end_of_last_week = start_of_last_week + timedelta(days=6)

    shift_start = start_of_last_week.replace(hour=0, minute=0, second=0, microsecond=0)
    shift_end = end_of_last_week.replace(hour=23, minute=59, second=59, microsecond=0)

    run(shift_type="weekly", shift_start=shift_start, shift_end=shift_end)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--shift", choices=["morning", "evening", "weekly"], 
                       help="Shift type to generate report for")
    args = parser.parse_args()
    if args.shift == "weekly":
        run_weekly_report()
    else:
        run(args.shift)