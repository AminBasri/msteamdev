# src/msteam/crew.py

import os
import yaml
from threading import Timer
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from crewai import Agent, Task, Crew
from msteam.llm import get_llm
from msteam.tools.notify import send_notification
from msteam.tools.alert_store import check_escalation_eligibility

load_dotenv()

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def load_agents():
    agent_def = load_yaml("src/msteam/config/agents.yaml")
    llm = get_llm()
    return {
        name: Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            verbose=True,
            llm=llm,
        )
        for name, cfg in agent_def.items()
    }

def load_tasks():
    return load_yaml("src/msteam/config/tasks.yaml")

def run_alert_pipeline(alert: dict):
    occurred_at = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
    delay = (occurred_at + timedelta(minutes=delay_minutes)) - now
    seconds = max(0, delay.total_seconds())
    print(f"⏱ Holding alert {int(seconds)} seconds before escalation decision")
    Timer(seconds, run_escalation_pipeline, args=[alert]).start()
    return f"⏱ Alert scheduled for evaluation in {int(seconds)} seconds"

def run_escalation_pipeline(alert: dict):
    print("⏰ Escalation pipeline triggered")

    agents = load_agents()
    tasks_def = load_tasks()

    escalation_agent = agents.get("escalation_checker")
    communicator_agent = agents.get("communicator")

    if not escalation_agent or not communicator_agent:
        print("❌ Missing required agents.")
        return

    eligible, reason = check_escalation_eligibility(alert)
    print(f"🧪 Policy check: {eligible}, Reason: {reason}")

    context = (
        f"Alert Title: {alert['title']}\n"
        f"Severity: {alert['severity']}\n"
        f"Occurred At: {alert['timestamp']}\n"
        f"Metric: {alert['metric']}\n"
        f"Incident #: {alert.get('incident_number')}\n\n"
        f"Policy Result: {eligible} - {reason}\n"
        f"Should this alert be escalated to BAU?"
    )

    # Task 1: Decide whether to escalate
    decision_task = Task(
        description=tasks_def["evaluate_escalation"]["description"] + "\n\n" + context,
        expected_output=tasks_def["evaluate_escalation"]["expected_output"],
        agent=escalation_agent,
    )

    # Task 2: Compose escalation message
    notification_task = Task(
        description=tasks_def["notify_bau"]["description"]
        + "\n\nAlert Details:\n"
        + context
        + "\n\nIf escalation is required, compose a message and prepare for email.",
        expected_output=tasks_def["notify_bau"]["expected_output"],
        agent=communicator_agent,
        context=[decision_task],
    )

    crew = Crew(
        agents=[escalation_agent, communicator_agent],
        tasks=[decision_task, notification_task],
        verbose=True,
    )

    try:
        print("🧠 Kicking off AI crew for escalation and notification...")
        result = crew.kickoff()
        print(f"🤖 Crew execution completed with result:\n{result.raw}")

        # Fix: Use result.raw instead of result.output
        comm_response = str(result.raw or "")
        
        # Debug: Show what the AI responded
        print(f"🔍 Full AI response: {comm_response}")

        # Improved keyword detection - make it more flexible
        escalation_keywords = ["yes", "escalate", "send", "notify", "proceed", "approved", "urgent", "critical"]
        found_keywords = [kw for kw in escalation_keywords if kw in comm_response.lower()]
        print(f"🔍 Keywords found: {found_keywords}")

        should_send_email = len(found_keywords) > 0

        # Enhanced decision logic: consider both AI decision and policy check
        if should_send_email or eligible:
            if should_send_email:
                print("📧 AI confirmed escalation. Sending email via notify.py...")
            elif eligible:
                print("📧 Policy check indicates escalation needed, overriding AI decision...")
            
            try:
                send_notification(alert, reason)
                print("✅ Email sent to BAU successfully.")
            except Exception as email_error:
                print(f"❌ Failed to send email: {email_error}")
                if "smtp" in str(email_error).lower():
                    print("🔴 SMTP configuration issue detected.")
                elif "auth" in str(email_error).lower():
                    print("🔴 Authentication issue detected.")
                else:
                    print("🔴 Unknown email sending error.")
        else:
            print("ℹ️ Escalation was not approved by AI and policy check failed. No email sent.")
            print(f"🔍 Response preview: {comm_response[:200]}...")

    except Exception as e:
        print(f"💥 Crew execution failed: {e}")
        print(f"💥 Error type: {type(e).__name__}")
        
        # Enhanced error handling
        if "CrewOutput" in str(e):
            print("🔴 CrewOutput attribute error - check result access method")
        elif "smtp" in str(e).lower() or "email" in str(e).lower():
            print("🔴 Email sending failed — check SMTP configuration.")
        else:
            print(f"🔴 Unexpected error: {str(e)}")
            
        # In case of crew failure but policy says escalate, still try to send email
        if eligible:
            print("⚠️ Crew failed but policy indicates escalation needed. Attempting direct email...")
            try:
                send_notification(alert, f"Crew execution failed but policy indicates escalation: {reason}")
                print("✅ Fallback email sent successfully.")
            except Exception as fallback_error:
                print(f"❌ Fallback email also failed: {fallback_error}")