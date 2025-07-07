import os
import json
from datetime import datetime, timedelta, timezone

LOG_FILE = "src/msteamuat/alert_log.json"

def _load_log():
    """Load alert log from file, returning an empty list if file doesn't exist."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r") as f:
        return [json.loads(line.strip()) for line in f if line.strip()]

def _save_log(data):
    """Save alert to log, avoiding duplicates based on incident_number, title, status, and timestamp."""
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

def check_escalation_eligibility(current_alert):
    """Determine if the alert should be escalated or suppressed, with full context history."""
    alerts = _load_log()

    # Save current alert after checking
    _save_log(current_alert)

    # Define current time and threshold
    current_time = datetime.fromisoformat(current_alert["timestamp"].replace("Z", "+00:00"))
    threshold = 5 if current_alert["severity"] == "warning" else 3

    # Find previous 'triggered' alerts with same title and severity
    matching_alerts = []
    for alert in alerts:
        if (alert["title"] == current_alert["title"] and
            alert["severity"] == current_alert["severity"] and
            alert["status"] == "triggered"):
            past_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
            days_diff = (current_time - past_time).days
            if 0 <= days_diff < threshold:
                matching_alerts.append((alert, days_diff))

    # Format history context
    matching_alerts.sort(key=lambda x: x[0]["timestamp"], reverse=True)
    history_lines = [
        f"    - Incident {a['incident_number']}: Triggered on {a['timestamp']} ({d} day(s) ago)"
        for a, d in matching_alerts
    ]
    history_summary = "\n".join(history_lines) if history_lines else "    - No recent matching alerts found."

    # Decision logic
    if matching_alerts:
        return False, (
            f"🚫 Alert suppressed:\n"
            f"- Title: {current_alert['title']}\n"
            f"- Severity: {current_alert['severity']}\n"
            f"- Incident: {current_alert['incident_number']}\n"
            f"- Current Timestamp: {current_alert['timestamp']}\n"
            f"- Suppression threshold: {threshold} days\n"
            f"- Matching alert(s) seen within threshold:\n{history_summary}\n"
            f"- Decision: Do NOT escalate."
        )
    else:
        return True, (
            f"🔺 Escalation allowed:\n"
            f"- Title: {current_alert['title']}\n"
            f"- Severity: {current_alert['severity']}\n"
            f"- Incident: {current_alert['incident_number']}\n"
            f"- Current Timestamp: {current_alert['timestamp']}\n"
            f"- Suppression threshold: {threshold} days\n"
            f"- No matching alerts found within threshold window.\n"
            f"- Decision: Escalate."
        )