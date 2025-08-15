# Enhanced crew.py - Core Engine with Preserved Logic + Performance Improvements
import os
import sys
import yaml
from threading import Thread
from datetime import datetime, timedelta, timezone
from functools import wraps
import time
import logging
import asyncio
import json
import re
import requests
import openlit
from crewai import Agent, Task, Crew, Process
from msteamdev.llm import get_llm
from crewai_tools import MCPServerAdapter
from mcp import StdioServerParameters
from msteamdev.tools.alert_store import check_escalation_eligibility, _load_log
from crewai.tools import tool
from pdpyras import APISession
from msteamdev.tools.redis_client import cache_set_add, cache_set_remove, cache_set_is_member

# Initialize OpenLit for telemetry
openlit.init()

# ENHANCED: Performance and Error Tracking
class CrewPerformanceMonitor:
    """Enhanced performance monitoring without disrupting existing flow."""
    
    def __init__(self):
        self.processing_stats = {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "escalated": 0,
            "suppressed": 0,
            "fallback_used": 0,
            "avg_processing_time": 0,
            "processing_times": []
        }
        self.agent_stats = {}
        self.error_patterns = {}
    
    def record_processing(self, incident_number: str, duration: float, status: str, agent_used: str = None):
        """Record processing metrics."""
        self.processing_stats["total_processed"] += 1
        self.processing_stats["processing_times"].append(duration)
        
        # Keep only last 100 processing times for memory efficiency
        if len(self.processing_stats["processing_times"]) > 100:
            self.processing_stats["processing_times"] = self.processing_stats["processing_times"][-100:]
        
        # Update average
        self.processing_stats["avg_processing_time"] = sum(self.processing_stats["processing_times"]) / len(self.processing_stats["processing_times"])
        
        # Status tracking
        if status in self.processing_stats:
            self.processing_stats[status] += 1
        
        # Agent performance tracking
        if agent_used:
            if agent_used not in self.agent_stats:
                self.agent_stats[agent_used] = {"calls": 0, "successes": 0, "avg_time": 0, "times": []}
            
            self.agent_stats[agent_used]["calls"] += 1
            self.agent_stats[agent_used]["times"].append(duration)
            if status == "successful":
                self.agent_stats[agent_used]["successes"] += 1
            
            # Update agent average time
            self.agent_stats[agent_used]["avg_time"] = sum(self.agent_stats[agent_used]["times"]) / len(self.agent_stats[agent_used]["times"])
    
    def record_error_pattern(self, error_type: str, incident_number: str):
        """Track error patterns for analysis."""
        if error_type not in self.error_patterns:
            self.error_patterns[error_type] = {"count": 0, "recent_incidents": []}
        
        self.error_patterns[error_type]["count"] += 1
        self.error_patterns[error_type]["recent_incidents"].append({
            "incident": incident_number,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Keep only last 20 incidents per error type
        if len(self.error_patterns[error_type]["recent_incidents"]) > 20:
            self.error_patterns[error_type]["recent_incidents"] = self.error_patterns[error_type]["recent_incidents"][-20:]
    
    def get_health_report(self) -> dict:
        """Generate health report."""
        total = self.processing_stats["total_processed"]
        success_rate = (self.processing_stats["successful"] / total * 100) if total > 0 else 0
        
        return {
            "processing_stats": self.processing_stats.copy(),
            "success_rate_percent": round(success_rate, 2),
            "agent_performance": self.agent_stats.copy(),
            "error_patterns": self.error_patterns.copy(),
            "system_health": "healthy" if success_rate > 80 else "degraded" if success_rate > 50 else "critical"
        }

# Global performance monitor
performance_monitor = CrewPerformanceMonitor()

# PRESERVE YOUR EXISTING Tee class and logging setup
class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()  # Ensure each write is flushed
    def flush(self):
        for f in self.files:
            f.flush()

# Create a log directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'log')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'crew.log')

# Create a log file and Tee object
log_file = open(log_file_path, 'a')
original_stdout = sys.stdout
original_stderr = sys.stderr
sys.stdout = Tee(original_stdout, log_file)
sys.stderr = Tee(original_stderr, log_file)

logger = logging.getLogger('crew')
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()

# Add FileHandler for crew.log
file_handler = logging.FileHandler(log_file_path)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Add StreamHandler for console output
stream_handler = logging.StreamHandler(original_stdout)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(stream_handler)

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:6006/mcp")
from_email = os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")

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
    """
    valid_from_email = os.getenv("SENDER_EMAIL", "noramin@infopro.com.my")
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "AcknowledgeIncident", "arguments": {"incident_number": incident_number, "from_email": valid_from_email}},
        "id": "2"
    }
    try:
        # ENHANCED: Add performance tracking
        start_time = time.time()
        response = requests.post(MCP_SERVER_URL, json=jsonrpc_request, timeout=15)
        response.raise_for_status()
        
        duration = time.time() - start_time
        performance_monitor.record_processing(incident_number, duration, "successful", "AcknowledgeIncident")
        
        return response.text
    except requests.RequestException as e:
        logger.error(f"AcknowledgeIncident tool failed: {e}")
        performance_monitor.record_error_pattern("MCP_AcknowledgeIncident_Failure", incident_number)
        return f"Error calling MCP server: {e}"

# ENHANCED: Improve get_mcp_tools with better error handling
def get_mcp_tools() -> list:
    """Load MCP tools with enhanced error handling."""
    logger.info("Loading MCP tools...")
    mcp_tools = [get_incident_status, acknowledge_incident]

    try:
        # Configure StdioServerParameters for the internal MCP server
        stdio_server_params = StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "mcp_stdio_server.py")],
            env=os.environ.copy()  # Pass current environment variables
        )

        # Use MCPServerAdapter to get tools from the Stdio MCP server
        with MCPServerAdapter(stdio_server_params) as stdio_tools:
            mcp_tools.extend(stdio_tools)
            logger.info(f"Successfully loaded {len(stdio_tools)} additional MCP tools from stdio server.")

    except Exception as e:
        logger.error(f"Failed to load stdio MCP tools: {e}. Continuing with basic tools only.")
        performance_monitor.record_error_pattern("MCP_StdioServer_LoadFailure", "system")

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
            # reasoning=cfg.get("reasoning", True),
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
async def check_and_acknowledge_alert_task(alert: dict, mcp_tools: list, max_retries=3):
    """Check incident status after delay and acknowledge if triggered."""
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
            tools=mcp_tools,
            async_execution=True
        )

        for attempt in range(max_retries):
            try:
                with openlit.start_trace(name=f"Acknowledge_Incident_{incident_number}") as trace:
                    result = await asyncio.to_thread(pagerduty_manager.execute_task, acknowledge_task)
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
                    headers={"From": alert.get("from_email", "noramin@infopro.com.my")}
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
            await cache_set_remove(ESCALATION_SET_NAME, incident_number)
            
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
            await cache_set_remove(ESCALATION_SET_NAME, incident_number)
            
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
            telemetry=False
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
                await cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # ENHANCED: Record escalation success
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "escalated", "escalation_pipeline")
                
                return {"status": "escalated", "message": "Email sent to BAU successfully"}
            except Exception as email_error:
                logger.error(f"❌ Failed to send email for incident {incident_number}: {email_error}")
                await cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # ENHANCED: Record email failure
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "failed", "email_send_failure")
                performance_monitor.record_error_pattern("Email_Send_Failure", incident_number)
                
                return {"status": "error", "message": f"Failed to send email: {str(email_error)}"}
        else:
            logger.info(f"ℹ️ Escalation not approved for incident {incident_number} by AI and policy check failed")
            await cache_set_remove(ESCALATION_SET_NAME, incident_number)
            
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
                await cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # ENHANCED: Record fallback escalation
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "fallback_escalated", "escalation_pipeline")
                
                return {"status": "escalated", "message": "Fallback email sent successfully"}
            except Exception as fallback_error:
                logger.error(f"❌ Fallback email failed for incident {incident_number}: {fallback_error}")
                await cache_set_remove(ESCALATION_SET_NAME, incident_number)
                
                # ENHANCED: Record complete failure
                duration = time.time() - start_time
                performance_monitor.record_processing(incident_number, duration, "failed", "complete_failure")
                performance_monitor.record_error_pattern("Complete_Pipeline_Failure", incident_number)
                
                return {"status": "error", "message": f"Fallback email failed: {str(fallback_error)}"}
        await cache_set_remove(ESCALATION_SET_NAME, incident_number)
        
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
    
    try:
        mcp_tools = mcp_tools or get_mcp_tools()
        
        if await cache_set_is_member(ESCALATION_SET_NAME, incident_number):
            logger.info(f"Alert {incident_number} already scheduled for escalation, skipping")
            return

        occurred_at = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delay_minutes = int(os.getenv("ESCALATION_DELAY_MINUTES", "3"))
        delay = (occurred_at + timedelta(minutes=delay_minutes)) - now
        seconds = max(0, delay.total_seconds())
        
        logger.info(f"⏱ Holding alert {incident_number} for {int(seconds)} seconds before escalation decision")

        if alert["status"] == "triggered":
            asyncio.create_task(check_and_acknowledge_alert_task(alert, mcp_tools))
            logger.info(f"⏳ Scheduled acknowledgment check for incident {incident_number}")
        else:
            logger.info(f"✅ Alert #{incident_number} is already resolved. Skipping acknowledgment scheduling.")

        await asyncio.sleep(seconds)

        if await check_resolution_status(alert, delay_minutes):
            logger.info(f"✅ Alert with incident #{incident_number} resolved within {delay_minutes} minutes")
            return

        await cache_set_add(ESCALATION_SET_NAME, incident_number)
        await run_escalation_pipeline(alert, mcp_tools)

    except Exception as e:
        logger.error(f"Error in _run_alert_pipeline_async for incident {incident_number}: {str(e)}")
        performance_monitor.record_error_pattern("Pipeline_Async_Failure", incident_number)
    finally:
        end_time = time.time()
        duration = end_time - start_time
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
        
        logger.debug("Successfully integrated enhanced tools metrics")
    except Exception as e:
        logger.warning(f"Could not integrate enhanced tools metrics: {e}")
        health_report["enhanced_tools_metrics"] = "unavailable"
    
    return health_report

# Track scheduled escalations to prevent duplicates
ESCALATION_SET_NAME = "scheduled_escalations"

# PRESERVE your main execution
if __name__ == "__main__":
    alert = {
        "incident_number": "191",
        "title": "Test Alert",
        "severity": "critical",
        "timestamp": "2025-07-30T00:02:06Z",
        "metric": "Server Down",
        "status": "triggered",
        "from_email": "noramin@infopro.com.my"
    }
    print("Running enhanced pipeline directly for testing...")
    asyncio.run(_run_alert_pipeline_async(alert))
    print("Enhanced pipeline test run finished.")
    print(f"System health: {get_system_health()}")
