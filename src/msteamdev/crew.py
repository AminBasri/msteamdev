# Enhanced crew.py - Core Engine with Preserved Logic + Performance Improvements
import os
import sys
import yaml
from threading import Thread
from datetime import datetime, timedelta, timezone, time
from functools import wraps
import time
import logging
import asyncio
import json
import re
import requests
import openlit
from crewai import Agent, Task, Crew, Process
from crewai.agent import Agent as BaseAgent
from crewai.task import Task as BaseTask
from msteamdev.llm import get_llm
from msteamdev.tools.alert_store import check_escalation_eligibility, _load_log

# Enhance Agent and Task classes with logging
class LoggedAgent(BaseAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)
        
    def execute_task(self, task, *args, **kwargs):
        self.logger.info(f"Agent '{self.name}' starting task: {task.description}")
        try:
            result = super().execute_task(task, *args, **kwargs)
            self.logger.info(f"Agent '{self.name}' completed task successfully")
            return result
        except Exception as e:
            self.logger.error(f"Agent '{self.name}' failed task with error: {str(e)}")
            raise

class LoggedTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)
        
    def execute(self, *args, **kwargs):
        self.logger.info(f"Starting task execution: {self.description}")
        try:
            result = super().execute(*args, **kwargs)
            self.logger.info(f"Task completed successfully: {self.description}")
            return result
        except Exception as e:
            self.logger.error(f"Task failed with error: {str(e)}")
            raise
from crewai.tools import tool
from pdpyras import APISession
from msteamdev.tools.redis_client import cache_set_add, cache_set_remove, cache_set_is_member
from msteamdev.tools.alert_store import (
    read_alert_log,
    read_escalation_log,
    get_matching_alerts,
)
from msteamdev.tools.enhanced_tools import (
    read_alert_log_enhanced,
    get_matching_alerts_enhanced,
    check_escalation_eligibility_enhanced,
    get_alert_trends,
    get_system_health as get_system_health_tool,
)
from crewai_tools import FileReadTool
from msteamdev.logging_setup import setup_root_logger, configure_llm_library_loggers

setup_root_logger('crew.log', logging.INFO)
# Route llm-related libraries (httpx/httpcore/LiteLLM/litellm/openlit) to llm.log
configure_llm_library_loggers(["httpx", "httpcore", "litellm", "LiteLLM", "openlit", "opentelemetry.trace", "opentelemetry.instrumentation.instrumentor"])

logger = logging.getLogger(__name__)

# Initialize OpenLit for telemetry
openlit.init()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:7006/mcp")
from_email = os.getenv("SENDER_EMAIL", "noc@infopro.com.my")

def log_crew_execution(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Starting CrewAI execution: {func.__name__}")
        try:
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            logger.info(f"CrewAI execution completed in {duration:.2f} seconds")
            return result
        except Exception as e:
            logger.error(f"CrewAI execution failed: {str(e)}")
            raise
    return wrapper

# Lightweight performance monitor to preserve existing logic and calls
class _PerformanceMonitor:
    def __init__(self):
        self.processing_records = []
        self.error_patterns = {}

    def record_processing(self, incident_number: str, duration: float, status: str, stage: str):
        try:
            self.processing_records.append({
                "incident_number": str(incident_number),
                "duration": float(duration),
                "status": str(status),
                "stage": str(stage),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception:
            # safety: never raise from monitor
            pass

    def record_error_pattern(self, pattern_name: str, incident_number: str | None = None):
        try:
            key = str(pattern_name)
            self.error_patterns[key] = self.error_patterns.get(key, 0) + 1
        except Exception:
            pass

    def get_health_report(self) -> dict:
        try:
            total = len(self.processing_records)
            by_status = {}
            avg_duration = 0.0
            if total:
                total_duration = 0.0
                for rec in self.processing_records:
                    total_duration += rec.get("duration", 0.0)
                    status = rec.get("status", "unknown")
                    by_status[status] = by_status.get(status, 0) + 1
                avg_duration = total_duration / max(total, 1)
            return {
                "total_operations": total,
                "avg_duration": avg_duration,
                "by_status": by_status,
                "error_patterns": dict(self.error_patterns)
            }
        except Exception:
            return {
                "total_operations": 0,
                "avg_duration": 0.0,
                "by_status": {},
                "error_patterns": {}
            }

# Global instance used throughout the module
performance_monitor = _PerformanceMonitor()

# PRESERVE YOUR EXISTING Tool implementations with ENHANCEMENT
@tool("GetIncidentStatus")
def get_incident_status(incident_number: str) -> str:
    """
    Get the status of a PagerDuty incident by incident number.
    Input should be the incident number as a string.
    """
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "GetIncidentStatus", "arguments": {"incident_number": incident_number}},
        "id": "1"
    }
    try:
        # ENHANCED: Add timeout and better error handling
        start_time = time.time()
        response = requests.post(MCP_SERVER_URL, json=jsonrpc_request, timeout=10)
        response.raise_for_status()
        
        # ENHANCED: Track tool performance
        duration = time.time() - start_time
        performance_monitor.record_processing(incident_number, duration, "successful", "GetIncidentStatus")
        
        return response.text
    except requests.RequestException as e:
        logger.error(f"GetIncidentStatus tool failed: {e}")
        performance_monitor.record_error_pattern("MCP_GetIncidentStatus_Failure", incident_number)
        return f"Error calling MCP server: {e}"

@tool("AcknowledgeIncident")
def acknowledge_incident(incident_number: str, from_email: str) -> str:
    """
    Acknowledge a PagerDuty incident.
    Input should be the incident number and the email of the user acknowledging the incident.
    First tries SENDER_EMAIL, falls back to provided email or fallback chain if SENDER_EMAIL fails.
    """
    # First try with SENDER_EMAIL
    sender_email = os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")
    jsonrpc_request_sender = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "AcknowledgeIncident", "arguments": {"incident_number": incident_number, "from_email": sender_email}},
        "id": "2"
    }
    
    try:
        start_time = time.time()
        response = requests.post(MCP_SERVER_URL, json=jsonrpc_request_sender, timeout=15)
        response.raise_for_status()
        
        # If successful with SENDER_EMAIL, return the result
        duration = time.time() - start_time
        performance_monitor.record_processing(incident_number, duration, "successful_sender_email", "AcknowledgeIncident")
        return response.text
    except requests.RequestException as e:
        logger.warning(f"Failed to acknowledge with SENDER_EMAIL, trying fallback: {e}")
        performance_monitor.record_error_pattern("SENDER_EMAIL_Failed", incident_number)
        
        # If SENDER_EMAIL fails, try with fallback chain
        provided = (from_email or "").strip()
        if provided.lower() in {"your_email@example.com", "test@example.com", "user@example.com"} or provided.endswith("@example.com"):
            provided = ""
        valid_from_email = provided or os.getenv("PAGERDUTY_FALLBACK_FROM_EMAIL") or sender_email
        jsonrpc_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "AcknowledgeIncident", "arguments": {"incident_number": incident_number, "from_email": valid_from_email}},
            "id": "2"
        }
        try:
            # Track performance for fallback attempt
            start_time = time.time()
            response = requests.post(MCP_SERVER_URL, json=jsonrpc_request, timeout=15)
            response.raise_for_status()
            
            duration = time.time() - start_time
            performance_monitor.record_processing(incident_number, duration, "successful_fallback", "AcknowledgeIncident")
            
            return response.text
        except requests.RequestException as e:
            logger.error(f"Both SENDER_EMAIL and fallback acknowledgment failed: {e}")
            performance_monitor.record_error_pattern("Complete_Acknowledgment_Failure", incident_number)
            return f"Error calling MCP server: {e}"

# ENHANCED: Improve get_mcp_tools with better error handling
def get_mcp_tools() -> list:
    """Load MCP tools with enhanced error handling."""
    logger.info("Loading MCP tools...")
    
    # The user suggested using FileReadTool, so we'll add it.
    # We can configure it to read the alert and escalation logs.
    alert_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alert_log.json")
    escalation_log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escalation_log.json")
    
    mcp_tools = [
        get_incident_status, 
        acknowledge_incident,
        read_alert_log,
        read_escalation_log,
        get_matching_alerts,
        read_alert_log_enhanced,
        get_matching_alerts_enhanced,
        check_escalation_eligibility_enhanced,
        get_alert_trends,
        get_system_health_tool,
        FileReadTool(file_path=alert_log_path, description="A tool to read the alert log file."),
        FileReadTool(file_path=escalation_log_path, description="A tool to read the escalation log file.")
    ]

    logger.info(f"Successfully loaded total {len(mcp_tools)} MCP tools.")
    return mcp_tools

# PRESERVE YOUR retry decorator - it's excellent!
def retry(max_attempts=3, delay=2):
    """Retry decorator for CrewAI tasks, supporting both sync and async functions."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    await asyncio.sleep(delay * (2 ** attempt))
                    logger.warning(f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}")

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
                    logger.warning(f"Retry {attempt + 1}/{max_attempts} for {func.__name__}: {e}")

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

# PRESERVE all your existing PagerDuty functions
def get_pagerduty_session():
    token = os.getenv("PAGERDUTY_API_TOKEN")
    if not token:
        logger.critical("PAGERDUTY_API_TOKEN environment variable is not set")
        raise ValueError("Missing PagerDuty API token")
    return APISession(token)

def _is_placeholder_email_local(email: str | None) -> bool:
    if not email:
        return True
    lowered = email.strip().lower()
    return lowered in {"your_email@example.com", "test@example.com", "user@example.com"} or lowered.endswith("@example.com")

def _resolve_requester_email_local(provided_email: str | None) -> str:
    if provided_email and not _is_placeholder_email_local(provided_email):
        return provided_email
    fallback = os.getenv("PAGERDUTY_FALLBACK_FROM_EMAIL") or os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")
    return fallback

def find_incident_by_number(session, incident_number: str):
    logger.debug(f"Searching for incident number: {incident_number}")
    try:
        for incident in session.iter_all("incidents"):
            if str(incident.get("incident_number")) == str(incident_number):
                logger.info(f"Found incident: {incident_number}")
                return incident
        logger.warning(f"Incident {incident_number} not found")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch incidents: {str(e)}")
        raise

def get_user_email_from_pagerduty(user_id: str) -> str | None:
    """Fetches a user's email from PagerDuty API given their user ID."""
    try:
        session = get_pagerduty_session()
        user = session.rget(f"/users/{user_id}")
        if user and user.get("email"):
            logger.info(f"Found email {user['email']} for user ID {user_id}")
            return user["email"]
        logger.warning(f"Email not found for user ID {user_id}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch email for user ID {user_id}: {str(e)}")
        return None

# PRESERVE your YAML loading functions
def load_yaml(path):
    """Load YAML configuration file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)

# ENHANCED: Add caching to load_agents for better performance
_agents_cache = {}
_agents_cache_time = None

def load_agents(mcp_tools=None):
    """Load agents from YAML with caching."""
    global _agents_cache, _agents_cache_time
    
    # Cache for 5 minutes to reduce YAML parsing overhead
    cache_timeout = 300  # 5 minutes
    current_time = time.time()
    
    cache_key = f"agents_{hash(str(sorted([t.name for t in (mcp_tools or [])])))}"
    
    if (_agents_cache_time and 
        current_time - _agents_cache_time < cache_timeout and 
        cache_key in _agents_cache):
        logger.debug("Using cached agents")
        return _agents_cache[cache_key]
    
    agent_def = load_yaml("src/msteamdev/config/agents_enhanced.yaml")
    agents = {}
    for name, cfg in agent_def.items():
        llm = get_llm()
        tools = []
        
        # Assign tools based on agent configuration and availability
        if name == "pagerduty_manager" and mcp_tools:
            # PagerDuty manager gets incident management tools
            tools = [tool for tool in mcp_tools if tool.name in ["GetIncidentStatus", "AcknowledgeIncident"]]
            logger.info(f"Assigned {len(tools)} PagerDuty tools to pagerduty_manager")
            
        elif name == "escalation_checker" and mcp_tools:
            # Escalation checker gets comprehensive analysis tools
            enhanced_tool_names = [
                "ReadAlertLog", "ReadEscalationLog", "GetMatchingAlerts",  # Original tools
                "ReadAlertLogEnhanced", "GetMatchingAlertsEnhanced", "CheckEscalationEligibility", 
                "GetAlertTrends", "GetSystemHealth"  # Enhanced tools
            ]
            tools = [tool for tool in mcp_tools if tool.name in enhanced_tool_names]
            logger.info(f"Assigned {len(tools)} enhanced analysis tools to escalation_checker")
            
        elif name == "reporter" and mcp_tools:
            # Reporter gets trend analysis and system health tools
            reporter_tool_names = ["ReadAlertLogEnhanced", "GetAlertTrends", "GetSystemHealth"]
            tools = [tool for tool in mcp_tools if tool.name in reporter_tool_names]
            logger.info(f"Assigned {len(tools)} reporting tools to reporter")

        agents[name] = Agent(
            role=cfg["role"],
            goal=cfg["goal"],
            backstory=cfg["backstory"],
            verbose=True,
            llm=llm,
            tools=tools,
            allow_delegation=cfg.get("allow_delegation", True)
        )
    
    # Update cache
    _agents_cache[cache_key] = agents
    _agents_cache_time = current_time
    
    logger.debug(f"Loaded agents: {list(agents.keys())}")
    return agents

def load_tasks():
    """Load tasks from YAML."""
    return yaml.safe_load(open("src/msteamdev/config/tasks_enhanced.yaml", "r"))

# PRESERVE your existing check_resolution_status
async def check_resolution_status(alert: dict, delay_minutes: int) -> bool:
    """Check if an alert with the same incident number has resolved status within the delay period."""
    alerts = await _load_log()
    incident_number = alert.get("incident_number")
    current_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
    cutoff_time = current_time + timedelta(minutes=delay_minutes)

    for logged_alert in alerts:
        alert_time = datetime.fromisoformat(logged_alert["timestamp"].replace("Z", "+00:00"))
        if (logged_alert["incident_number"] == incident_number and
            logged_alert["status"] == "resolved" and
            current_time <= alert_time <= cutoff_time):
            return True
    return False

# PRESERVE your check_and_acknowledge_alert_task with performance tracking
@log_crew_execution
async def check_and_acknowledge_alert_task(alert: dict, mcp_tools: list, max_retries=3):
    """Check and acknowledge alerts with retries and enhanced error handling."""
    logger.info(f"Processing alert: {alert.get('incident_number', 'UNKNOWN')}")
    logger.info(f"Alert details: {json.dumps(alert, indent=2)}")
    start_time = time.time()
    incident_number = alert['incident_number']
    
    try:
        delay_minutes = int(os.getenv("ACKNOWLEDGMENT_DELAY_MINUTES", "1"))
        delay_seconds = delay_minutes * 60
        logger.info(f"Scheduling acknowledgment check for incident {incident_number} in {delay_seconds} seconds")
        await asyncio.sleep(delay_seconds)

        agents = load_agents(mcp_tools)
        pagerduty_manager = agents.get("pagerduty_manager")
        tasks_def = load_tasks()

        if not pagerduty_manager:
            logger.error("Missing pagerduty_manager agent")
            raise ValueError("Missing pagerduty_manager agent")
        
        if not mcp_tools:
            raise ValueError("MCP tools not available.")

        logger.debug(f"PagerDuty Manager Agent: role={pagerduty_manager.role}")

        task_description = tasks_def["check_and_acknowledge_alert"]["description"].format(
            incident_number=alert["incident_number"],
            from_email=alert.get("from_email", "noramin@infopro.com.my")
        )
        logger.debug(f"Task description: {task_description}")

        acknowledge_task = Task(
            description=task_description,
            expected_output=tasks_def["check_and_acknowledge_alert"]["expected_output"],
            agent=pagerduty_manager,
        )

        for attempt in range(max_retries):
            try:
                with openlit.start_trace(name=f"Acknowledge_Incident_{incident_number}") as trace:
                    crew = Crew(agents=[pagerduty_manager], tasks=[acknowledge_task], verbose=True, telemetry=True)
                    kickoff_result = await crew.kickoff_async()
                    result = str(kickoff_result.raw or "")
                    trace.set_metadata({
                        "incident_number": incident_number,
                        "agent": "pagerduty_manager"
                    })
                
                logger.debug(f"Task output for incident {incident_number}: {result}")
                logger.info(f"Raw acknowledgment task result for incident {incident_number}: {result}")

                if isinstance(result, str):
                    try:
                        json_match = re.search(r'\{.*\}', result, re.DOTALL)
                        if json_match:
                            parsed_result = json.loads(json_match.group(0))
                            
                            # ENHANCED: Record successful acknowledgment
                            duration = time.time() - start_time
                            performance_monitor.record_processing(incident_number, duration, "successful", "acknowledge_task")
                            
                            return parsed_result
                        else:
                            return {"status": "success", "message": result}
                    except json.JSONDecodeError:
                        return {"status": "success", "message": result}
                else:
                    logger.error(f"Task output is not a string for incident {incident_number}: {result}")
                    return {"status": "error", "message": "Task output is not a string", "raw_response": result}

            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{max_retries} failed for incident {incident_number}: {str(e)}")
                if attempt == max_retries - 1:
                    logger.error(f"Max retries reached for incident {incident_number}")
                    raise
                await asyncio.sleep(2 ** attempt)

    except Exception as e:
        logger.error(f"Acknowledgment task via MCP failed for incident {incident_number}: {str(e)}. Attempting direct PagerDuty API call.")
        performance_monitor.record_error_pattern("Acknowledge_MCP_Failure", incident_number)
        
        try:
            session = get_pagerduty_session()
            incident = find_incident_by_number(session, alert["incident_number"])
            if not incident:
                logger.error(f"Incident {incident_number} not found via direct API")
                return {"status": "error", "message": f"Incident {incident_number} not found"}

            if incident["status"] == "resolved":
                logger.info(f"Direct API check: Incident {incident_number} is already resolved. No action taken.")
                return {"status": "already_resolved", "message": "Incident is already resolved"}

            result_payload = {
                "incident_number": incident_number,
                "status": incident["status"],
                "acknowledgment": "skipped",
                "related_alerts": []
            }
            if incident["status"] == "triggered":
                session.rput(
                    f"/incidents/{incident['id']}",
                    json={"incident": {"type": "incident_reference", "status": "acknowledged"}},
                    headers={"From": _resolve_requester_email_local(alert.get("from_email"))}
                )
                verified = find_incident_by_number(session, incident_number)
                result_payload["acknowledgment"] = "success" if verified and verified["status"] == "acknowledged" else "failed"
            
            # ENHANCED: Record fallback usage
            duration = time.time() - start_time
            performance_monitor.record_processing(incident_number, duration, "fallback_used", "acknowledge_direct_api")
            
            logger.info(f"Direct API result for incident {incident_number}: {result_payload}")
            return result_payload
        except Exception as api_e:
            logger.error(f"Direct PagerDuty API call also failed for incident {incident_number}: {str(api_e)}")
            
            # ENHANCED: Record complete failure
            duration = time.time() - start_time
            performance_monitor.record_processing(incident_number, duration, "failed", "acknowledge_all_failed")
            performance_monitor.record_error_pattern("Acknowledge_Complete_Failure", incident_number)
            
            return {"status": "error", "message": str(api_e)}

# PRESERVE your run_escalation_pipeline with performance enhancements
@retry()
async def run_escalation_pipeline(alert: dict, mcp_tools: list):
    """Run the escalation pipeline, deciding whether to escalate and notify."""
    start_time = time.time()
    incident_number = alert["incident_number"]
    logger.info(f"⏰ Escalation pipeline triggered for incident {incident_number}")
    from msteamdev.tools.notify import send_notification

    eligible = False
    reason = ""
    try:
        delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "3"))
        if await check_resolution_status(alert, delay_minutes):
            logger.info(f"✅ Alert with incident #{incident_number} resolved before escalation")
            cache_set_remove(ESCALATION_SET_NAME, incident_number)
            
            # ENHANCED: Record resolved status
            duration = time.time() - start_time
            performance_monitor.record_processing(incident_number, duration, "resolved_before_escalation", "escalation_pipeline")
            
            return {"status": "resolved", "message": "Alert resolved, escalation canceled"}

        agents = load_agents(mcp_tools)
        tasks_def = load_tasks()
        escalation_agent = agents.get("escalation_checker")
        communicator_agent = agents.get("communicator")

        if not escalation_agent or not communicator_agent:
            logger.error("Missing required agents")
            cache_set_remove(ESCALATION_SET_NAME, incident_number)
            
            # ENHANCED: Record agent failure
            duration = time.time() - start_time
            performance_monitor.record_processing(incident_number, duration, "failed", "missing_agents")
            performance_monitor.record_error_pattern("Missing_Required_Agents", incident_number)
            
            return {"status": "error", "message": "Missing required agents"}

        eligible, reason = await check_escalation_eligibility(alert)
        logger.info(f"🧪 Policy check for incident {incident_number}: {eligible}, Reason: {reason}")

        alert_history = await _load_log()

        context = (
            f"Alert Title: {alert['title']}\n"
            f"Severity: {alert['severity']}\n"
            f"Occurred At: {alert['timestamp']}\n"
            f"Metric: {alert['metric']}\n"
            f"Incident #: {incident_number}\n\n"
            f"Policy Result: {eligible} - {reason}\n\n"
            f"Full Alert History: {json.dumps(alert_history)}\n\n"
            f"You must verify the policy's output against the raw logs and the escalation history. Use the ReadEscalationLog tool to check past escalations. If the policy output is correct, use it to make your decision. If it is incorrect, override it and make the correct decision based on your own analysis of the alert history and escalation history.\n\n"
            f"Should this alert be escalated to BAU?"
        )

        escalation_task = Task(
            description=tasks_def["evaluate_escalation"]["description"] + "\n\n" + context,
            expected_output=tasks_def["evaluate_escalation"]["expected_output"],
            agent=escalation_agent
        )

        notification_task = Task(
            description=tasks_def["notify_bau"]["description"] + "\n\nAlert Details:\n" + context + "\n\nIf escalation is required, compose a message and prepare for email.",
            expected_output=tasks_def["notify_bau"]["expected_output"],
            agent=communicator_agent,
            context=[escalation_task]
        )

        crew = Crew(
            agents=[escalation_agent, communicator_agent],
            tasks=[escalation_task, notification_task],
            verbose=True,
            telemetry=True
        )

        logger.info(f"🧠 Kicking off AI crew for escalation and notification of incident {incident_number}")
        with openlit.start_trace(name=f"Escalation_Pipeline_{incident_number}") as trace:
            result = await crew.kickoff_async()
            trace.set_metadata({
                "incident_number": incident_number,
                "agents": ["escalation_checker", "communicator"]
            })

        comm_response = str(result.raw or "")
        logger.info(f"🤖 Crew execution completed with result: {comm_response}")

        escalation_keywords = ["yes", "escalate", "send", "notify", "proceed", "approved", "urgent", "critical"]
        found_keywords = [kw for kw in escalation_keywords if kw in comm_response.lower()]
        logger.info(f"🔍 Keywords found: {found_keywords}")

        should_send_email = len(found_keywords) > 0

        if should_send_email or eligible:
            try:
                final_reason = comm_response if should_send_email else reason
                send_notification(alert, final_reason)
                logger.info(f"✅ Email sent to BAU for incident {incident_number}")
                cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # Record escalation in escalation_log.json
                escalation_entry = {
                    "incident_number": incident_number,
                    "title": alert["title"],
                    "severity": alert["severity"],
                    "timestamp": alert["timestamp"],
                    "escalated": True,
                    "reason": final_reason,
                    "escalation_time": datetime.now(timezone.utc).isoformat(),
                    "escalation_type": "ai_decision" if should_send_email else "policy_check"
                }
                from msteamdev.tools.alert_store import save_escalation_log_sync
                save_escalation_log_sync(escalation_entry)
                
                # ENHANCED: Record escalation success
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "escalated", "escalation_pipeline")
                
                return {"status": "escalated", "message": "Email sent to BAU successfully"}
            except Exception as email_error:
                logger.error(f"❌ Failed to send email for incident {incident_number}: {email_error}")
                cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # ENHANCED: Record email failure
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "failed", "email_send_failure")
                performance_monitor.record_error_pattern("Email_Send_Failure", incident_number)
                
                return {"status": "error", "message": f"Failed to send email: {str(email_error)}"}
        else:
            logger.info(f"ℹ️ Escalation not approved for incident {incident_number} by AI and policy check failed")
            cache_set_remove(ESCALATION_SET_NAME, incident_number)
            
            # ENHANCED: Record suppression
            duration = time.time() - start_time
            performance_monitor.record_processing(incident_number, duration, "suppressed", "escalation_pipeline")
            
            return {"status": "suppressed", "message": "Escalation not approved, no email sent"}

    except Exception as e:
        logger.error(f"💥 Crew execution failed for incident {incident_number}: {e}")
        if eligible:
            logger.info(f"⚠️ Crew failed but policy indicates escalation needed for incident {incident_number}")
            try:
                send_notification(alert, f"Crew execution failed but policy indicates escalation: {reason}")
                logger.info(f"✅ Fallback email sent for incident {incident_number}")
                cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # ENHANCED: Record fallback escalation
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "fallback_escalated", "escalation_pipeline")
                
                return {"status": "escalated", "message": "Fallback email sent successfully"}
            except Exception as fallback_error:
                logger.error(f"❌ Fallback email failed for incident {incident_number}: {fallback_error}")
                cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # ENHANCED: Record complete failure
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "failed", "complete_failure")
                performance_monitor.record_error_pattern("Complete_Pipeline_Failure", incident_number)
                
                return {"status": "error", "message": f"Fallback email failed: {str(fallback_error)}"}
        cache_set_remove(ESCALATION_SET_NAME, incident_number)
        
        # ENHANCED: Record pipeline failure
        duration = time.time() - start_time
        performance_monitor.record_processing(incident_number, duration, "failed", "pipeline_failure")
        performance_monitor.record_error_pattern("Pipeline_Execution_Failure", incident_number)
        
        return {"status": "error", "message": f"Crew execution failed: {str(e)}"}

# PRESERVE your core async pipeline
async def _run_alert_pipeline_async(alert: dict, mcp_tools: list = None):
    """The core async pipeline logic."""
    start_time = time.time()
    incident_number = alert.get("incident_number", "N/A")
    
    # Log pipeline start to incident_pipeline.log
    try:
        pipeline_start_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "pipeline_start",
            "incident_number": incident_number,
            "alert": {
                "title": alert.get("title"),
                "severity": alert.get("severity"),
                "status": alert.get("status"),
                "metric": alert.get("metric"),
                "timestamp": alert.get("timestamp")
            }
        }
        with open("/home/crewai/msteamdev/log/incident_pipeline.log", "a") as f:
            f.write(json.dumps(pipeline_start_entry) + "\n")
    except Exception as log_exc:
        logger.error(f"Failed to write pipeline start to incident log: {log_exc}")
    
    try:
        mcp_tools = mcp_tools or get_mcp_tools()
        
        if cache_set_is_member(ESCALATION_SET_NAME, incident_number):
            logger.info(f"Alert {incident_number} already scheduled for escalation, skipping")
            return

        occurred_at = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "3"))
        delay = (occurred_at + timedelta(minutes=delay_minutes)) - now
        seconds = max(0, delay.total_seconds())
        
        # Mark as scheduled to prevent duplicates
        cache_set_add(ESCALATION_SET_NAME, incident_number)
        logger.info(f"⏱ Holding alert {incident_number} for {int(seconds)} seconds before escalation decision")

        if alert["status"] == "triggered":
            asyncio.create_task(check_and_acknowledge_alert_task(alert, mcp_tools))
            logger.info(f"⏳ Scheduled acknowledgment check for incident {incident_number}")
        else:
            logger.info(f"✅ Alert #{incident_number} is already resolved. Skipping acknowledgment scheduling.")

        await asyncio.sleep(seconds)
        await run_escalation_pipeline(alert, mcp_tools)

    except Exception as e:
        logger.error(f"Error in _run_alert_pipeline_async for incident {incident_number}: {str(e)}")
        performance_monitor.record_error_pattern("Pipeline_Async_Failure", incident_number)
    finally:
        end_time = time.time()
        duration = end_time - start_time
        
        # Log pipeline completion to incident_pipeline.log
        try:
            pipeline_completion_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "pipeline_completion",
                "incident_number": incident_number,
                "duration_seconds": duration,
                "status": "completed" if not sys.exc_info()[0] else "error",
                "metrics": {
                    "processing_time": duration,
                    "had_error": bool(sys.exc_info()[0]),
                }
            }
            with open("/home/crewai/msteamdev/log/incident_pipeline.log", "a") as f:
                f.write(json.dumps(pipeline_completion_entry) + "\n")
        except Exception as log_exc:
            logger.error(f"Failed to write pipeline completion to incident log: {log_exc}")
            
        logger.info(f"CrewAI pipeline for incident {incident_number} finished in {duration:.2f} seconds.")

# PRESERVE your background processing
def _run_pipeline_in_background(alert: dict):
    """Helper to run the async pipeline in a new event loop in a new thread."""
    logger.info(f"Starting background processing for incident {alert.get('incident_number', 'N/A')}")
    asyncio.run(_run_alert_pipeline_async(alert))

# PRESERVE your main entry point
def start_alert_pipeline(alert: dict):
    """
    Synchronous entry point to start the alert pipeline in a background thread.
    This should be called from the webhook receiver.
    """
    thread = Thread(target=_run_pipeline_in_background, args=(alert,))
    thread.daemon = True
    thread.start()
    logger.info(f"Webhook received. Handed off incident {alert.get('incident_number', 'N/A')} to background processor.")
    return {"status": "processing_started"}

# NEW: Health monitoring endpoint (doesn't interfere with existing flow)
def get_system_health() -> dict:
    """Get comprehensive system health report combining crew and enhanced tools metrics."""
    health_report = performance_monitor.get_health_report()
    health_report["timestamp"] = datetime.now(timezone.utc).isoformat()
    health_report["environment"] = {
        "mcp_server_url": MCP_SERVER_URL,
        "sender_email": from_email,
        "escalation_delay_minutes": os.getenv("ESCALATION_DELAY_MINUTES", "3"),
        "acknowledgment_delay_minutes": os.getenv("ACKNOWLEDGMENT_DELAY_MINUTES", "1")
    }
    
    # Add enhanced tools metrics if available
    try:
        from msteamdev.tools.enhanced_tools import tool_metrics, get_system_health as enhanced_health
        health_report["enhanced_tools_metrics"] = tool_metrics.get_stats()
        
        # Get enhanced system health data (call the tool's run method)
        enhanced_health_data = json.loads(enhanced_health._run())
        health_report["enhanced_system_data"] = enhanced_health_data
        
        # Log system health info to incident pipeline log
        try:
            pipeline_log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "system_health",
                "data": {
                    "crew_metrics": {
                        "total_operations": health_report["total_operations"],
                        "avg_duration": health_report["avg_duration"],
                        "error_patterns": health_report["error_patterns"]
                    },
                    "tool_metrics": health_report["enhanced_tools_metrics"],
                    "active_alerts": enhanced_health_data.get("active_alerts_count", 0),
                    "processing_queue": enhanced_health_data.get("processing_queue_size", 0)
                }
            }
            with open("/home/crewai/msteamdev/log/incident_pipeline.log", "a") as f:
                f.write(json.dumps(pipeline_log_entry) + "\n")
        except Exception as log_exc:
            logger.error(f"Failed to write system health to incident pipeline log: {log_exc}")
        
        logger.debug("Successfully integrated enhanced tools metrics")
        logger.info(f"System health: {get_system_health()}")
    except Exception as e:
        logger.warning(f"Could not integrate enhanced tools metrics: {e}")
        health_report["enhanced_tools_metrics"] = "unavailable"
    
    return health_report

# Track scheduled escalations to prevent duplicates
ESCALATION_SET_NAME = "scheduled_escalations"

# PRESERVE your main execution
if __name__ == "__main__":
    alert = {
        "incident_number": "192",
        "title": "ALARM: '[WARNING] [INFOPRO-RFC] Synergi CORE Prod - High CPU Util...' in Asia Pacific (Singapore)",
        "severity": "WARNING",
        "timestamp": "2025-08-19T03:08:06Z",
        "metric": "CPU Utilization",
        "status": "triggered",
        "from_email": "noramin@infopro.com.my"
    }
    logger.info("Running enhanced pipeline directly for testing...")
    asyncio.run(_run_alert_pipeline_async(alert))
    logger.info("Enhanced pipeline test run finished.")
    logger.info(f"System health: {get_system_health()}")
