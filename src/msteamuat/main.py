#!/usr/bin/env python
import sys
import warnings

from datetime import datetime

from msteamuat.crew import msteamuat

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# This main file is intended to be a way for you to run your
# crew locally, so refrain from adding unnecessary logic into this file.
# Replace with inputs you want to test with, it will automatically
# interpolate any tasks and agents information

def run():
    """
    Run the crew.
    """
    print("CrewAI project ready. Use webhook or daily_report.py.")


def train():
    """
    Train the crew for a given number of iterations.
    """
    print("Training...")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    print("Replay complete.")

def test():
    """
    Test the crew execution and returns the results.
    """
    print("Testing...")
