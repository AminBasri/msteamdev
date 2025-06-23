# src/msteam/tools/alert_store.py

import os, json
from datetime import datetime, timedelta, timezone

LOG_FILE = "src/msteam/alert_log.json"

def _load_log():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r") as f:
        return [json.loads(line.strip()) for line in f]

def _save_log(data):
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")

def _last_alert(alerts, title, severity, current_timestamp):
    # Convert current timestamp to datetime for proper comparison
    current_time = datetime.fromisoformat(current_timestamp.replace("Z", "+00:00"))
    
    matching_alerts = []
    for alert in alerts:
        if (alert["title"] == title and 
            alert["severity"] == severity and 
            alert["status"] == "triggered"):  # Only consider triggered alerts
            
            alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
            # Use < for strictly previous alerts, or <= to include same timestamp
            if alert_time < current_time:
                matching_alerts.append((alert, alert_time))
    
    if not matching_alerts:
        return None
    
    # Return the most recent previous alert
    return max(matching_alerts, key=lambda x: x[1])[0]

def check_escalation_eligibility(current_alert):
    alerts = _load_log()
    
    # Check for previous alert before saving current one
    last = _last_alert(alerts, current_alert["title"], current_alert["severity"], current_alert["timestamp"])
    
    # Save current alert after checking
    _save_log(current_alert)
    
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