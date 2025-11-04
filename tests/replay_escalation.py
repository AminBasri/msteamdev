
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
    # Ensure priority is an integer for testing purposes if it's a string like "p2"
    if 'priority' in selected_alert and isinstance(selected_alert['priority'], str):
        # Attempt to convert "p2" to 2, or similar logic
        if selected_alert['priority'].lower().startswith('p'):
            try:
                selected_alert['priority'] = int(selected_alert['priority'][1:])
            except ValueError:
                selected_alert['priority'] = 2 # Default to 2 if conversion fails
        else:
            try:
                selected_alert['priority'] = int(selected_alert['priority'])
            except ValueError:
                selected_alert['priority'] = 2 # Default to 2 if conversion fails
else:
    selected_alert = None

# Replay the escalation pipeline for the selected alert
if __name__ == "__main__":
    if selected_alert:
        print(f"Replaying escalation for incident: {selected_alert.get('incident_number')}")
        asyncio.run(run_escalation_pipeline(selected_alert))
    else:
        print("No alerts found in the log.")
