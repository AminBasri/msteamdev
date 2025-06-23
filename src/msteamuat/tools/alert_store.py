# src/msteamuat/tools/alert_store.py

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
    # Create a unique key to check for exact duplicates
    unique_key = f"{data['incident_number']}_{data['title']}_{data['status']}_{data['timestamp']}"
    if not any(
        a.get('incident_number') == data['incident_number'] and
        a.get('title') == data['title'] and
        a.get('status') == data['status'] and
        a.get('timestamp') == data['timestamp']
        for a in alerts
    ):
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(data) + "\n")

def _last_alert(alerts, title, severity, current_timestamp):
    """Find the most recent previous alert matching title and severity."""
    current_time = datetime.fromisoformat(current_timestamp.replace("Z", "+00:00"))
    matching_alerts = []
    for alert in alerts:
        if (alert["title"] == title and 
            alert["severity"] == severity and 
            alert["status"] == "triggered"):
            alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
            if alert_time < current_time:
                matching_alerts.append((alert, alert_time))
    
    if not matching_alerts:
        return None
    
    return max(matching_alerts, key=lambda x: x[1])[0]

def check_escalation_eligibility(current_alert):
    """Check if an alert is eligible for escalation based on suppression rules."""
    alerts = _load_log()
    last = _last_alert(alerts, current_alert["title"], current_alert["severity"], current_alert["timestamp"])
    
    # Save current alert after checking
    _save_log(current_alert)
    
    # Check if the most recent entry for this incident is resolved
    recent_alerts = [a for a in alerts if a["incident_number"] == current_alert["incident_number"]]
    if recent_alerts:
        latest_alert = max(recent_alerts, key=lambda x: datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00")))
        if latest_alert["status"] == "resolved":
            return False, f"Incident #{current_alert['incident_number']} already resolved at {latest_alert['timestamp']}"
    
    if not last:
        return True, "First alert for this metric — allowed to escalate"

    current_time = datetime.fromisoformat(current_alert["timestamp"].replace("Z", "+00:00"))
    last_time = datetime.fromisoformat(last["timestamp"].replace("Z", "+00:00"))
    threshold = 5 if current_alert["severity"] == "warning" else 3
    days_diff = (current_time - last_time).days
    
    if days_diff >= threshold:
        return True, f"Last seen {days_diff} days ago (threshold: {threshold})"
    else:
        return False, f"Suppressed: last seen {days_diff} days ago (threshold: {threshold})"