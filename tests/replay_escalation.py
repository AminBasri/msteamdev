
import asyncio
import json
from msteamdev.crew import run_escalation_pipeline

selected_alert = None
# Load the alert from the log file
with open("src/msteamdev/alert_log.json", "r") as f:
    for line in f:
        alert = json.loads(line)
        if alert.get("incident_number") == 346:
            selected_alert = alert
            break

# Replay the escalation pipeline for the selected alert
if __name__ == "__main__":
    if selected_alert:
        asyncio.run(run_escalation_pipeline(selected_alert))
    else:
        print("Alert with incident number 346 not found in the log.")
