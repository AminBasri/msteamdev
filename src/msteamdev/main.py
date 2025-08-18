#!/usr/bin/env python

import argparse
import sys
import time
import warnings
from datetime import datetime, timezone

from msteamdev.crew import start_alert_pipeline

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pydantic_core")
warnings.filterwarnings("ignore", category=UserWarning, module="crewai.task")

def run_test_pipeline():
    """Runs a test alert through the pipeline."""
    print("--- Running a test alert through the pipeline ---")
    test_alert = {
        "incident_number": "200",
        "title": "Test Alert from main.py",
        "severity": "critical",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "metric": "Test Metric",
        "status": "triggered",
    }
    start_alert_pipeline(test_alert)
    print("--- Test pipeline started in the background. Monitor logs for details. ---")
    # Keep the main thread alive to allow the background thread to run
    try:
        while True:
            time.sleep(60)
            print("Main thread is alive, waiting for background tasks...")
    except KeyboardInterrupt:
        print("--- Test run concluded. ---")

def main():
    """
    Main function to run the crew from the command line.
    """
    parser = argparse.ArgumentParser(description="Run the msteamdev Crew.")
    parser.add_argument(
        "command",
        choices=["run", "test"],
        help="The command to execute. 'run' starts a test pipeline, 'test' is an alias for run."
    )
    args = parser.parse_args()

    if args.command in ["run", "test"]:
        run_test_pipeline()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()