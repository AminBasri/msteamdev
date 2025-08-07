import json
from datetime import datetime, timedelta
import logging
import os
from crewai.tools import tool

LOG_FILE = "src/msteamuat/alert_log.json"
ESCALATION_LOG_FILE = "src/msteamuat/escalation_log.json"

@tool("ReadAlertLog")
def read_alert_log() -> str:
    """
    Read the entire alert log and return it as a string.
    """
    try:
        with open(LOG_FILE, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Alert log not found."

@tool("ReadEscalationLog")
def read_escalation_log() -> str:
    """
    Read the entire escalation log and return it as a string.
    """
    try:
        with open(ESCALATION_LOG_FILE, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "Escalation log not found."

def _load_log():
    """Load alerts from alert_log.json."""
    logging.info("Loading alert log from file: %s", LOG_FILE)
    try:
        with open(LOG_FILE, "r") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def _load_escalation_log():
    """Load escalation events from escalation_log.json."""
    logging.info("Loading escalation log from file: %s", ESCALATION_LOG_FILE)
    try:
        with open(ESCALATION_LOG_FILE, "r") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def _save_log(data):
    """Save alert to alert_log.json, avoiding duplicates."""
    alerts = _load_log()
    if not any(
        a.get('incident_number') == data['incident_number'] and
        a.get('title') == data['title'] and
        a.get('status') == data['status'] and
        a.get('timestamp') == data['timestamp']
        for a in alerts
    ):
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(data) + "\n")

def _save_escalation_log(data):
    """Save escalation event to escalation_log.json, avoiding duplicates."""
    escalations = _load_escalation_log()
    if not any(
        e.get('incident_number') == data['incident_number'] and
        e.get('timestamp') == data['timestamp']
        for e in escalations
    ):
        with open(ESCALATION_LOG_FILE, "a") as f:
            f.write(json.dumps(data) + "\n")

def count_weekdays(start_date, end_date):
    """Count the number of weekdays (Monday to Friday) between two dates (inclusive)."""
    current_date = start_date
    weekday_count = 0
    while current_date <= end_date:
        if current_date.weekday() < 5:  # 0-4 are Monday to Friday
            weekday_count += 1
        current_date += timedelta(days=1)
    return weekday_count

def check_escalation_eligibility(current_alert):
    """Determine if the alert should be escalated based on weekday span and cooldown after escalation."""
    alerts = _load_log()
    escalations = _load_escalation_log()

    # Define current time and threshold
    current_time = datetime.fromisoformat(current_alert["timestamp"].replace("Z", "+00:00"))
    threshold = 5 if current_alert["severity"] == "warning" else 3

    # Check for recent escalations within threshold
    recent_escalations = [
        escalation
        for escalation in escalations
        if (escalation["title"] == current_alert["title"] and
            escalation["severity"] == current_alert["severity"] and
            escalation.get("escalated", False) and
            0 <= (current_time - datetime.fromisoformat(escalation["timestamp"].replace("Z", "+00:00"))).days <= threshold)
    ]
    if recent_escalations:
        recent_lines = [
            f"    - Incident {e['incident_number']}: Escalated on {e['timestamp']} "
            f"({(current_time - datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))).days} day(s) ago)"
            for e in recent_escalations
        ]
        recent_summary = "\n".join(recent_lines)
        _save_log(current_alert)
        return False, (
            f"🚫 Alert suppressed:\n"
            f"- Title: {current_alert['title']}\n"
            f"- Severity: {current_alert['severity']}\n"
            f"- Incident: {current_alert['incident_number']}\n"
            f"- Current Timestamp: {current_alert['timestamp']}\n"
            f"- Suppression threshold: {threshold} weekdays\n"
            f"- Recent escalation(s) within {threshold} days:\n{recent_summary}\n"
            f"- Decision: Do NOT escalate due to recent escalation."
        )

    # Find matching triggered alerts (excluding current alert)
    matching_alerts = [
        alert
        for alert in alerts
        if (alert["title"] == current_alert["title"] and
            alert["severity"] == current_alert["severity"] and
            alert["status"] == "triggered" and
            alert["incident_number"] != current_alert["incident_number"])
    ]
    if current_alert["status"] == "triggered":
        matching_alerts.append(current_alert)

    if matching_alerts:
        matching_alerts.sort(key=lambda x: x["timestamp"])
        earliest_alert = matching_alerts[0]
        latest_alert = matching_alerts[-1]
        earliest_time = datetime.fromisoformat(earliest_alert["timestamp"].replace("Z", "+00:00"))
        latest_time = datetime.fromisoformat(latest_alert["timestamp"].replace("Z", "+00:00"))
        span_days = count_weekdays(earliest_time, latest_time)

        history_lines = [
            f"    - Incident {a['incident_number']}: Triggered on {a['timestamp']} "
            f"({(current_time - datetime.fromisoformat(a['timestamp'].replace('Z', '+00:00'))).days} day(s) ago)"
            for a in matching_alerts
        ]
        history_summary = "\n".join(history_lines)

        if span_days > threshold:
            # Save escalation event with the reason
            reason_for_escalation = (
                f"🔺 Escalation allowed:\n"
                f"- Title: {current_alert['title']}\n"
                f"- Severity: {current_alert['severity']}\n"
                f"- Incident: {current_alert['incident_number']}\n"
                f"- Current Timestamp: {current_alert['timestamp']}\n"
                f"- Suppression threshold: {threshold} weekdays\n"
                f"- Matching alerts span: {span_days} weekdays (from {earliest_alert['timestamp']} to {latest_alert['timestamp']})\n"
                f"- Note: Ages below are in total days, while span is in weekdays.\n"
                f"- Matching alert(s):\n{history_summary}\n"
                f"- Decision: Escalate."
            )
            escalation_entry = {
                "incident_number": current_alert["incident_number"],
                "title": current_alert["title"],
                "severity": current_alert["severity"],
                "timestamp": current_alert["timestamp"],
                "escalated": True,
                "reason": reason_for_escalation
            }
            _save_log(current_alert)
            _save_escalation_log(escalation_entry)
            return True, reason_for_escalation
        else:
            _save_log(current_alert)
            return False, (
                f"🚫 Alert suppressed:\n"
                f"- Title: {current_alert['title']}\n"
                f"- Severity: {current_alert['severity']}\n"
                f"- Incident: {current_alert['incident_number']}\n"
                f"- Current Timestamp: {current_alert['timestamp']}\n"
                f"- Suppression threshold: {threshold} weekdays\n"
                f"- Matching alerts span: {span_days} weekdays (from {earliest_alert['timestamp']} to {latest_alert['timestamp']})\n"
                f"- Note: Ages below are in total days, while span is in weekdays.\n"
                f"- Matching alert(s):\n{history_summary}\n"
                f"- Decision: Do NOT escalate."
            )
    else:
        _save_log(current_alert)
        return True, (
            f"🔺 Escalation allowed:\n"
            f"- Title: {current_alert['title']}\n"
            f"- Severity: {current_alert['severity']}\n"
            f"- Incident: {current_alert['incident_number']}\n"
            f"- Current Timestamp: {current_alert['timestamp']}\n"
            f"- Suppression threshold: {threshold} weekdays\n"
            f"- No matching triggered alerts found.\n"
            f"- Decision: Escalate."
        )

@tool("GetMatchingAlerts")
def get_matching_alerts(title: str, severity: str, hours: int = 24) -> list:
    """
    Get matching alerts from the log file within a specified time window.

    Args:
        title (str): The title of the alert to match.
        severity (str): The severity of the alert to match.
        hours (int): The number of hours to look back for matching alerts.

    Returns:
        list: A list of matching alerts.
    """
    alerts = _load_log()
    matching_alerts = []
    now = datetime.now()

    for alert in alerts:
        alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)
        if (
            alert["title"] == title and
            alert["severity"] == severity and
            now - alert_time < timedelta(hours=hours)
        ):
            matching_alerts.append(alert)

    return matching_alerts