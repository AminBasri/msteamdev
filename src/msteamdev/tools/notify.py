import os
import smtplib
import logging
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from typing import Dict
import pytz
from datetime import datetime, timezone

from msteamdev.logging_setup import get_module_logger

# Centralized notify logger
logger = get_module_logger('notify', log_filename='notify.log', level=logging.INFO)

LOCAL_TZ = pytz.timezone('Asia/Singapore')

def validate_smtp_config() -> tuple[bool, str]:
    """Validate SMTP configuration."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    recipients = os.getenv("ALERT_EMAIL_RECIPIENTS", "")

    missing_configs = []
    if not smtp_host:
        missing_configs.append("SMTP_HOST")
    if not smtp_user:
        missing_configs.append("SMTP_USERNAME")
    if not smtp_pass:
        missing_configs.append("SMTP_PASSWORD")
    if not recipients.strip():
        missing_configs.append("ALERT_EMAIL_RECIPIENTS")

    if missing_configs:
        return False, f"Missing environment variables: {', '.join(missing_configs)}"

    try:
        smtp_port = int(smtp_port)
        if smtp_port <= 0 or smtp_port > 65535:
            return False, f"Invalid SMTP_PORT: {smtp_port}"
    except ValueError:
        return False, f"SMTP_PORT must be a number, got: {smtp_port}"

    return True, "SMTP configuration is valid"

def validate_rocketchat_webhook() -> tuple[bool, str]:
    """Validate Rocket.Chat webhook configuration."""
    webhook_url = os.getenv("ROCKETCHAT_WEBHOOK_URL")
    webhook_token = os.getenv("ROCKETCHAT_WEBHOOK_TOKEN")

    if not webhook_url or not webhook_token:
        return False, "Missing ROCKETCHAT_WEBHOOK_URL or ROCKETCHAT_WEBHOOK_TOKEN environment variables"
    return True, "Rocket.Chat webhook configuration is valid"

def send_rocketchat_webhook_message(message: str) -> bool:
    """Send a message to Rocket.Chat using the webhook."""
    is_valid, config_message = validate_rocketchat_webhook()
    if not is_valid:
        logger.error(f"Rocket.Chat webhook validation failed: {config_message}")
        return False

    webhook_url = os.getenv("ROCKETCHAT_WEBHOOK_URL", "")
    webhook_token = os.getenv("ROCKETCHAT_WEBHOOK_TOKEN", "")
    
    if not webhook_url:
        logger.error("ROCKETCHAT_WEBHOOK_URL is not set")
        return False

    payload = {
        "alias": "CrewAI Alert System",
        "text": message
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            logger.info("Rocket.Chat webhook message sent successfully")
            return True
        else:
            logger.error(f"Rocket.Chat webhook failed: HTTP {response.status_code}, Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Rocket.Chat webhook message: {e}")
        return False

def send_notification(alert: Dict, subject: str, body: str) -> str:
    """Send email and Rocket.Chat webhook notification for alert escalation."""
    incident_number = alert.get('incident_number', 'N/A')
    logger.info(f"Starting notification for incident #{incident_number}")
    
    try:
        is_valid_smtp, smtp_message = validate_smtp_config()
        if not is_valid_smtp:
            logger.error(f"SMTP configuration validation failed: {smtp_message}")
            raise ValueError(f"SMTP configuration error: {smtp_message}")

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USERNAME")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        recipients = [email.strip() for email in os.getenv("ALERT_EMAIL_RECIPIENTS", "").split(",") if email.strip()]
        sender_name = os.getenv("SENDER_NAME", "CrewAI Escalation Alert System")
        sender_email = os.getenv("SENDER_EMAIL", smtp_user)

        msg = MIMEMultipart()
        msg["From"] = formataddr((str(Header(sender_name, 'utf-8')), sender_email))
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(sender_email, recipients, msg.as_string())
            logger.info(f"Email notification sent successfully to {len(recipients)} recipients")

        # Send Rocket.Chat webhook notification
        if send_rocketchat_webhook_message(body):
            logger.info(f"Rocket.Chat webhook notification sent successfully for incident #{incident_number}")
        else:
            logger.warning("Rocket.Chat webhook notification failed, but email was sent")

        return f"Notifications sent successfully: email to {len(recipients)} recipients, Rocket.Chat webhook message sent"
    except (ValueError, smtplib.SMTPException) as e:
        logger.error(f"Failed to send notifications: {e}")
        raise