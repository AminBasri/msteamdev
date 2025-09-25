import json
from datetime import datetime, timedelta
import logging
import os
from crewai.tools import tool

# Get the directory that contains the 'tools' subdirectory and the log files
# '..' navigates up one directory from the script's location
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Construct absolute paths to the log files
LOG_FILE = os.path.join(BASE_DIR, "alert_log.json")
ESCALATION_LOG_FILE = os.path.join(BASE_DIR, "escalation_log.json")

async def _load_log():
    """Load alerts from alert_log.json."""
    logging.info("Loading alert log from file: %s", LOG_FILE)
    try:
        with open(LOG_FILE, "r") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def load_log_sync():
    """Load alerts from alert_log.json synchronously."""
    logging.info("Loading alert log from file: %s", LOG_FILE)
    try:
        with open(LOG_FILE, "r") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def load_escalation_log_sync():
    """Load escalation events from escalation_log.json synchronously."""
    logging.info("Loading escalation log from file: %s", ESCALATION_LOG_FILE)
    try:
        with open(ESCALATION_LOG_FILE, "r") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []

def save_escalation_log_sync(data):
    """Save escalation event to escalation_log.json synchronously, avoiding duplicates."""
    escalations = load_escalation_log_sync()
    if not any(
        e.get('incident_number') == data['incident_number'] and
        e.get('timestamp') == data['timestamp']
        for e in escalations
    ):
        with open(ESCALATION_LOG_FILE, "a") as f:
            f.write(json.dumps(data) + "\n")
