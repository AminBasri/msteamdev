# src/msteamuat/daily_report.py
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
from msteamuat.tools.custom_tool import ShiftReportOutput
from msteamuat.crew import load_agents, load_yaml, check_resolution_status
from msteamuat.tools.alert_store import check_escalation_eligibility
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/crewai/msteamuat/report.log'),
        logging.StreamHandler()
    ]
)

LOG_PATH = "src/msteamuat/alert_log.json"
LOCAL_TZ = pytz.timezone('Asia/Singapore')  # +08 time zone

def load_alerts(start_time: datetime, end_time: datetime):
    """Load alerts from the log within the specified time window, deduplicating by incident_number."""
    if not os.path.exists(LOG_PATH):
        logging.warning(f"Alert log not found at {LOG_PATH}")
        return []
    try:
        alert_dict = {}
        with open(LOG_PATH, "r") as f:
            for line in f:
                alert = json.loads(line)
                alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                if start_time <= alert_time <= end_time:
                    incident_number = alert.get("incident_number")
                    if incident_number not in alert_dict or alert_time > datetime.fromisoformat(
                            alert_dict[incident_number]["timestamp"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc):
                        alert_dict[incident_number] = alert
        return list(alert_dict.values())
    except Exception as e:
        logging.error(f"Failed to load alerts: {e}")
        return []

def _generate_html_body(text_body: str, alert_summary: list, summary_stats: dict) -> str:
    """Generate HTML version of the report."""
    return f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .header {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
        .summary {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .summary-item {{ margin: 5px 0; }}
        .critical {{ color: #e74c3c; font-weight: bold; }}
        .warning {{ color: #f39c12; font-weight: bold; }}
        .resolved {{ color: #2ecc71; }}
        .alert-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 0.9em;
        }}
        .alert-table th {{
            background-color: #2c3e50;
            color: white;
            padding: 12px 15px;
            text-align: left;
        }}
        .alert-table td {{
            padding: 10px 15px;
            border-bottom: 1px solid #ddd;
        }}
        .alert-table tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
        .footer {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #eee; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Shift Report - {summary_stats['shift_start']} to {summary_stats['shift_end']} (+08)</h1>
    </div>
    
    <div class="summary">
        <h2>Summary</h2>
        <div class="summary-item">Total Alerts: {summary_stats['alert_count']}</div>
        <div class="summary-item">Critical Alerts: <span class="critical">{summary_stats['critical_count']}</span></div>
        <div class="summary-item">Warning Alerts: <span class="warning">{summary_stats['warning_count']}</span></div>
        <div class="summary-item">Resolved Alerts: <span class="resolved">{summary_stats['resolved_count']}</span></div>
        <div class="summary-item">Escalated Alerts: {summary_stats['escalated_count']}</div>
    </div>
    
    <h2>Alert Details</h2>
    <table class="alert-table">
        <thead>
            <tr>
                <th>Incident #</th>
                <th>Title</th>
                <th>Severity</th>
                <th>Metric</th>
                <th>Status</th>
                <th>Time</th>
                <th>Escalation</th>
            </tr>
        </thead>
        <tbody>
            {"".join([
                f'<tr>'
                f'<td>{a["incident_number"]}</td>'
                f'<td>{a["title"]}</td>'
                f'<td class="{a["severity"].lower()}">{a["severity"]}</td>'
                f'<td>{a["metric"]}</td>'
                f'<td>{a["status"]}</td>'
                f'<td>{a["timestamp"]}</td>'
                f'<td>{a["escalation_status"]}<br><small>{a["escalation_reason"]}</small></td>'
                f'</tr>'
                for a in alert_summary
            ])}
        </tbody>
    </table>
    
    <div class="footer">
        <p>Please review any unresolved incidents and contact the platform team for issues.</p>
        <p>Best regards,<br>
        <strong>CrewAI Reporting System</strong><br>
        Managed Service Team</p>
    </div>
</body>
</html>
"""

def send_report_email(subject: str, body: str, html_body: str = None):
    """Send the shift report email to the NOC team with HTML support."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    recipients = [email.strip() for email in os.getenv("ALERT_EMAIL_RECIPIENTS", "").split(",") if email.strip()]
    sender_name = os.getenv("SENDER_NAME", "CrewAI Reporting System")
    sender_email = os.getenv("SENDER_EMAIL", smtp_username)

    if not all([smtp_host, smtp_port, smtp_username, smtp_password, recipients]):
        logging.error("Missing SMTP configuration or recipients")
        raise ValueError("Incomplete SMTP configuration")

    # Fix \r\n escape sequences
    body = body.replace("\\r\\n", "\n").replace("\\n", "\n")

    msg = MIMEMultipart('alternative')
    msg['From'] = formataddr((str(Header(sender_name, 'utf-8')), sender_email))
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject

    # Create both plain text and HTML versions
    part1 = MIMEText(body, 'plain', 'utf-8')
    part2 = MIMEText(html_body, 'html', 'utf-8')

    msg.attach(part1)
    msg.attach(part2)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, recipients, msg.as_string())
            logging.info(f"Shift report emailed to {', '.join(recipients)}")
    except Exception as e:
        logging.error(f"Failed to send shift report email: {e}")
        raise

def run(shift_type=None):
    now = datetime.now(LOCAL_TZ)
    if shift_type is None:
        if 7 <= now.hour < 16:
            shift_type = "morning"
        elif 16 <= now.hour < 22:
            shift_type = "evening"
        else:
            shift_type = "morning"
    logging.info(f"Starting {shift_type} shift report generation")

    if shift_type == "morning":
        shift_start = now.replace(hour=7, minute=0, second=0, microsecond=0)
        shift_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    else:
        shift_start = now.replace(hour=16, minute=0, second=0, microsecond=0)
        shift_end = now.replace(hour=22, minute=0, second=0, microsecond=0)

    if now < shift_start:
        shift_start -= timedelta(days=1)
        shift_end -= timedelta(days=1)

    shift_start_utc = shift_start.astimezone(timezone.utc)
    shift_end_utc = shift_end.astimezone(timezone.utc)

    alerts = load_alerts(shift_start_utc, shift_end_utc)
    agents = load_agents()
    tasks_def = load_yaml("src/msteamuat/config/tasks.yaml")
    reporter_agent = agents.get("reporter")

    if not reporter_agent:
        logging.error("Missing reporter agent")
        return

    delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
    alert_summary = []

    for alert in alerts:
        eligible, reason = check_escalation_eligibility(alert)
        was_resolved = check_resolution_status(alert, delay_minutes)
        escalation_status = "Escalated" if eligible and not was_resolved else "Not Escalated"

        alert_timestamp_utc = datetime.fromisoformat(alert.get('timestamp', 'N/A').replace("Z", "+00:00")).replace(
            tzinfo=timezone.utc)
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

    alert_count = len(alerts)
    critical_count = sum(1 for a in alerts if a.get("severity") == "critical")
    warning_count = sum(1 for a in alerts if a.get("severity") == "warning")
    resolved_count = sum(1 for a in alerts if a.get("status") == "resolved")
    escalated_count = sum(1 for a in alerts if check_escalation_eligibility(a)[0] and not check_resolution_status(a, delay_minutes))

    shift_start_local = shift_start.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')
    shift_end_local = shift_end.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')

    summary_stats = {
        'shift_start': shift_start_local,
        'shift_end': shift_end_local,
        'alert_count': alert_count,
        'critical_count': critical_count,
        'warning_count': warning_count,
        'resolved_count': resolved_count,
        'escalated_count': escalated_count
    }

    report_task = Task(
        description=(
            tasks_def["compose_email"]["description"] + "\n" +
            f"Title: ALARM: \"[WARNING] [INFOPRO-RFC] Synergi CORE Prod - High Memory Util...\" in Asia Pacific (Singapore)\n" +
            f"Severity: WARNING\n" +
            f"Metric: memory\n" +
            f"Incident Number: 694\n" +
            f"Reason: Suppressed: last seen 0 days ago (threshold: 5)"
        ),
        expected_output=tasks_def["compose_email"]["expected_output"],
        agent=reporter_agent,
        output_pydantic=ShiftReportOutput
    )

    crew = Crew(
        agents=[reporter_agent],
        tasks=[report_task],
        verbose=True
    )

    try:
        logging.info("Kicking off AI crew for shift report")
        result = crew.kickoff()

        if hasattr(result, 'tasks_output') and result.tasks_output:
            json_string = result.tasks_output[0].raw
        elif hasattr(result, 'raw'):
            json_string = result.raw
        else:
            raise ValueError("Unable to extract JSON string from CrewOutput")

        # Clean up markdown code blocks
        if json_string.strip().startswith("```"):
            json_string = "\n".join(json_string.strip().splitlines()[1:])
            if json_string.strip().endswith("```"):
                json_string = "\n".join(json_string.splitlines()[:-1])
            json_string = json_string.strip()

        report = json.loads(json_string)
        subject = report.get("subject")
        body = report.get("body").replace("\\r\\n", "\n")
        html_body = report.get("html_body", _generate_html_body(body, alert_summary, summary_stats))

    except Exception as e:
        logging.error(f"Failed to parse agent output: {e}")
        # Fallback logic
        subject = f"Shift Report - {shift_start_local} to {shift_end_local} (+08)"
        body = (
            f"Dear Team,\n"
            f"This is the shift report for {shift_start_local} to {shift_end_local} (+08).\n"
            f"Summary:\n"
            f"- Total Alerts: {alert_count}\n"
            f"- Critical Alerts: {critical_count}\n"
            f"- Warning Alerts: {warning_count}\n"
            f"- Resolved Alerts: {resolved_count}\n"
            f"- Escalated Alerts: {escalated_count}\n"
            f"Alert Details:\n"
            f"{json.dumps(alert_summary, indent=2)}\n"
            f"Please review any unresolved incidents and contact the platform team for issues.\n"
            f"Best regards,\n"
            f"CrewAI Reporting System\n"
            f"Managed Service Team"
        )
        html_body = _generate_html_body(body, alert_summary, summary_stats)
        logging.warning("Using fallback report due to parsing failure")

    try:
        send_report_email(subject, body, html_body)
        logging.info("Shift report emailed to NOC team successfully")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--shift", choices=["morning", "evening"],
                       help="Shift type to generate report for")
    args = parser.parse_args()
    run(args.shift)