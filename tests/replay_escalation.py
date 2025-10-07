
import asyncio
import json
from msteamdev.crew import run_escalation_pipeline

# Load all alerts from the log file
alerts = []
with open("src/msteamdev/alert_log.json", "r") as f:
    for line in f:
        alerts.append(json.loads(line))

# Get the most recent alert (the last one in the file)
if alerts:
    selected_alert = alerts[-1]
else:
    selected_alert = None

# Replay the escalation pipeline for the selected alert
if __name__ == "__main__":
    if selected_alert:
        print(f"Replaying escalation for incident: {selected_alert.get('incident_number')}")
        asyncio.run(run_escalation_pipeline(selected_alert))
    else:
        print("No alerts found in the log.")
