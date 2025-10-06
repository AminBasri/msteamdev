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

def send_rocketchat_webhook_message(message: str, alert: Dict = None, subject: str = None) -> bool:
    """Send a message to Rocket.Chat using the webhook, with a fallback to email."""
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
            raise requests.exceptions.RequestException
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Rocket.Chat webhook message: {e}")
        logger.info("Attempting to send email notification as fallback.")
        if alert and subject:
            try:
                is_valid_smtp, smtp_message = validate_smtp_config()
                if not is_valid_smtp:
                    logger.error(f"SMTP configuration validation failed: {smtp_message}")
                    return False

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
                msg.attach(MIMEText(message, "plain"))

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(sender_email, recipients, msg.as_string())
                    logger.info(f"Fallback email notification sent successfully to {len(recipients)} recipients")
                    return True
            except (ValueError, smtplib.SMTPException) as smtp_e:
                logger.error(f"Failed to send fallback email notification: {smtp_e}")
                return False
        return False

def send_dynamic_notification(alert: Dict, subject: str, body: str) -> str:
    """Send notifications via email and Rocket.Chat, with fallback logic."""
    incident_number = alert.get('incident_number', 'N/A')
    logger.info(f"Starting dynamic notification for incident #{incident_number}")

    smtp_sent = False
    rocketchat_sent = False
    recipients_count = 0

    # Attempt to send email via SMTP
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
        recipients_count = len(recipients)
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
            logger.info(f"Email notification sent successfully to {recipients_count} recipients")
            smtp_sent = True

    except (ValueError, smtplib.SMTPException) as e:
        logger.error(f"Failed to send email notification: {e}")

    # Attempt to send Rocket.Chat message
    if send_rocketchat_webhook_message(body, alert=alert, subject=subject):
        rocketchat_sent = True
        logger.info(f"Rocket.Chat webhook notification sent successfully for incident #{incident_number}")
    else:
        logger.error("Rocket.Chat webhook notification failed.")

    # Final status report
    if smtp_sent and rocketchat_sent:
        return f"Notifications sent successfully: email to {recipients_count} recipients, Rocket.Chat webhook message sent"
    elif smtp_sent:
        return f"Notification sent successfully via email to {recipients_count} recipients. Rocket.Chat failed."
    elif rocketchat_sent:
        return "Notification sent successfully via Rocket.Chat. Email failed."
    else:
        error_message = "Failed to send notification via both email and Rocket.Chat."
        logger.critical(error_message)
        raise Exception(error_message)

def send_notification(alert: Dict, subject: str, body: str) -> str:
    """Send email and Rocket.Chat webhook notification for alert escalation."""
    return send_dynamic_notification(alert, subject, body)