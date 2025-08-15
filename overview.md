# Msteam Crew Overview

Msteam Crew is a multi-agent AI system designed for intelligent IT alert management. It leverages the [CrewAI](https://crewai.com) framework to automate the processing of alerts from PagerDuty, reducing manual effort and ensuring timely responses to critical incidents.

## Key Features

*   **Automated Alert Ingestion**: Ingests alerts from PagerDuty via webhooks.
*   **Automatic Acknowledgment**: Automatically acknowledges incidents to prevent unnecessary escalations.
*   **AI-Driven Escalation**: Uses a crew of AI agents to analyze alerts and decide whether to escalate them based on predefined rules.
*   **Email and Rocket.Chat Notifications**: Sends detailed notifications with actionable insights.
*   **Daily Shift Reports**: Generates and distributes daily reports summarizing alert activity. These reports are highly detailed, separating alerts into 'Escalated', 'Resolved', and 'Open' categories, complete with reasons for each status.
*   **Centralized Alert Logging**: Stores all alert data in a structured JSON file for easy analysis.

## Architecture

The system is composed of the following key components:

*   **Webhook Receiver**: A FastAPI application that listens for PagerDuty webhooks.
*   **CrewAI Agents**: A team of AI agents responsible for analyzing, acknowledging, and escalating alerts.
*   **Alert Store**: A JSON-based data store for persisting alert information.
*   **Notification Service**: A module for sending email and Rocket.Chat notifications.
*   **Model Context Protocol (MCP) Server**: A server that provides a structured interface for the AI model to receive context and execute actions, such as acknowledging an incident in PagerDuty. It uses a Redis cache to improve performance by reducing redundant API calls.

## How It Works

1.  **Alert Ingestion**: PagerDuty sends a webhook to the Webhook Receiver when a new incident is triggered.
2.  **Alert Logging**: The alert is logged in the Alert Store.
3.  **Automatic Acknowledgment**: The system schedules a task to automatically acknowledge the incident after a configurable delay.
4.  **AI-Powered Escalation**: If the incident is not resolved within a certain timeframe, a crew of AI agents is assembled to analyze the alert.
5.  **Escalation Decision**: The AI agents decide whether to escalate the alert based on its severity, history, and other factors.
6.  **Notification**: If the alert is escalated, a notification is sent to the appropriate team members via email and Rocket.Chat.
7.  **Daily Reporting**: At the end of each shift, a daily report is generated and sent to the team.