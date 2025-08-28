# Function Documentation

This document provides a detailed breakdown of the functions and classes within the `msteamdev` project. Each section corresponds to a Python file, explaining its purpose and the logic of its components.

---

## **`src/msteamdev/config.py`**

**Purpose:** Defines the configuration models for the application using Pydantic, ensuring that environment variables and other settings are loaded and validated correctly from a `.env` file.

### **Class `Config`**
A Pydantic `BaseSettings` class that defines the main configuration structure for the application. It automatically reads variables from the environment.

#### **Attributes:**
- `OPENAI_API_KEY`: The API key for accessing OpenAI services.
- `OPENLIT_API_KEY`: The API key for OpenLit telemetry.
- `PAGERDUTY_API_KEY`: The API key for PagerDuty integration.
- `PAGERDUTY_USER_EMAIL`: The user email for PagerDuty actions.
- `ROCKET_CHAT_WEBHOOK_URL`: The webhook URL for sending Rocket.Chat notifications.
- `SMTP_SERVER`: The address of the SMTP server for sending emails.
- `SMTP_PORT`: The port for the SMTP server.
- `SMTP_USER`: The username for SMTP authentication.
- `SMTP_PASSWORD`: The password for SMTP authentication.
- `EMAIL_SENDER`: The email address from which notifications are sent.
- `EMAIL_RECIPIENT`: The recipient email address for notifications.
- `REDIS_HOST`: The hostname of the Redis server.
- `REDIS_PORT`: The port for the Redis server.
- `REDIS_DB`: The Redis database index to use.

### **`load_config()`**
```python
def load_config():
```
#### **Function Breakdown:**
```
- Load environment variables from the `.env` file using `load_dotenv()`.
- Instantiate the `Config` class, which automatically reads the loaded variables.
- Return the populated and validated configuration object.
```

---

## **`src/msteamdev/crew.py`**

**Purpose:** Orchestrates the core alert processing pipeline. It handles the creation of AI agents, scheduling of tasks, and the end-to-end execution flow for analyzing and responding to alerts.

### **`AlertProcessor` Class**

#### **`__init__(self, alert)`**
Initializes the alert processor, setting up the necessary components for handling a new alert.
```
- Stores the incoming `alert` data.
- Initializes the `CrewPerformanceMonitor` to track metrics.
- Loads the custom MCP (Mission Critical Platform) tools available to the agents.
- Establishes a connection to the Redis client for state management.
```

#### **`_run_alert_pipeline_async(self)`**
The main asynchronous pipeline for processing a single alert to avoid blocking the main thread.
```
- Use the Redis client to check if the alert has already been scheduled for escalation.
  - If a schedule key exists in Redis, log that it's a duplicate and exit.
- Calculate the escalation delay (default is 3 minutes).
- Schedule the `check_and_acknowledge_alert_task` to run after a 1-minute delay.
- Schedule the main `run_escalation_pipeline` to run after the calculated 3-minute delay.
```

#### **`check_and_acknowledge_alert_task(self)`**
A background task designed to automatically acknowledge a PagerDuty incident to signal that it's being looked at.
```
- Wait for a 1-minute delay to allow the system to stabilize.
- Instantiate the `pagerduty_manager` agent.
- Define a CrewAI task for the agent to check and acknowledge the PagerDuty incident using its ID.
- Form a temporary crew with the agent and task, and execute it.
```

#### **`run_escalation_pipeline(self)`**
The core pipeline that determines if an alert requires human intervention and escalation.
```
- Wait for the scheduled 3-minute delay.
- Check with PagerDuty to see if the incident has already been resolved or acknowledged.
  - If it has, log this status and terminate the pipeline.
- Check if the alert is eligible for escalation by calling the `check_escalation_eligibility_sync` policy function.
- If the policy determines the alert should be suppressed, log the reason and terminate.
- If eligible, instantiate the `escalation_checker` and `communicator` AI agents.
- Define analysis and communication tasks for the agents.
- Execute the main CrewAI crew to get an AI-driven escalation decision and a composed notification message.
- Analyze the `communicator` agent's output for keywords (e.g., "escalate," "notify") to make the final decision.
- If the decision is to escalate, call `send_notification` and log the action.
```

#### **`process_alert(self)`**
The public entry point for starting the alert processing for a given alert.
```
- Create a new background thread targeting the `_run_alert_pipeline_async` method.
- Start the thread to run the pipeline asynchronously.
```

---

## **`src/msteamdev/daily_report.py`**

**Purpose:** Contains the logic for generating and sending a daily summary report of the system's performance and alert handling.

### **`generate_daily_report()`**
```python
def generate_daily_report():
```
#### **Function Breakdown:**
```
- Initialize the `CrewPerformanceMonitor` to access performance data.
- Instantiate the `reporter` agent.
- Define a CrewAI task for the agent to generate a daily report using the latest performance metrics.
- Form a crew and execute the task.
- Return the generated report content as a string.
```

### **`send_report(report)`**
```python
def send_report(report):
```
#### **Function Breakdown:**
```
- Instantiate the `communicator` agent.
- Define a CrewAI task for the agent to send the provided report.
- Form a crew and execute the task to distribute the report.
```

---

## **`src/msteamdev/tools/alert_store.py`**

**Purpose:** Manages the history of alerts and implements the core business logic for the escalation policy.

### **`read_alert_log()` & `read_escalation_log()`**
Simple tools to read and return the contents of `alert_log.json` and `escalation_log.json` respectively.

### **`check_escalation_eligibility_sync(current_alert)`**
The synchronous function that contains the core escalation policy logic.
```
- Check if there have been any recent escalations within a defined threshold.
  - If so, suppress the current alert.
- Find all historical alerts that match the current one.
- If matching alerts are found, calculate the time span between the first and last occurrence.
  - If the span exceeds a threshold (e.g., 5 days), recommend escalation.
  - Otherwise, suppress the alert.
- If no matching historical alerts are found, recommend escalating as it's a first occurrence.
```

---

## **`src/msteamdev/tools/inc_mgt.py`**

**Purpose:** Provides tools for interacting with the PagerDuty API to manage incidents.

### **`PagerDutyTool` Class**

#### **`get_incident_status(self, incident_id)`**
```python
def get_incident_status(self, incident_id: str) -> str:
```
#### **Function Breakdown:**
```
- Make a GET request to the PagerDuty API for the specified `incident_id`.
- Extract and return the incident's status (e.g., "triggered", "acknowledged", "resolved").
- Handle API errors gracefully.
```

#### **`acknowledge_incident(self, incident_id)`**
```python
def acknowledge_incident(self, incident_id: str) -> str:
```
#### **Function Breakdown:**
```
- First, call `get_incident_status` to ensure the incident is still "triggered".
- If it is, make a PUT request to the PagerDuty API to change its status to "acknowledged".
- Return a success or failure message.
```

---

## **`src/msteamdev/tools/notify.py`**

**Purpose:** A tool for sending notifications via different channels, such as email and Rocket.Chat.

### **`NotificationTool` Class**

#### **`send_notification(self, message, decision)`**
```python
def send_notification(self, message: str, decision: str) -> str:
```
#### **Function Breakdown:**
```
- Check if the `decision` contains keywords indicating escalation is required.
- If yes:
  - Construct and send an email using the configured SMTP settings.
  - Send a message to the configured Rocket.Chat webhook.
  - Log the successful notification.
- If no, log that the notification was suppressed.
- Return a status message.
```
