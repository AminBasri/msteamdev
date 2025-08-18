import json
import sys
import os
import logging
import traceback

# Determine the project root directory to correctly place the log file
# The script is in src/msteamdev/tools, so root is 3 levels up.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
log_dir = os.path.join(project_root, 'log')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'mcp_stdio_server.log')

# Configure logging
mcp_logger = logging.getLogger("mcp_stdio_server")
mcp_logger.setLevel(logging.INFO)
mcp_logger.propagate = False # Prevent double logging

# Remove existing handlers to avoid duplication
if mcp_logger.hasHandlers():
    mcp_logger.handlers.clear()

# Add a file handler
mcp_handler = logging.FileHandler(log_file_path)
mcp_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
mcp_handler.setFormatter(formatter)
mcp_logger.addHandler(mcp_handler)

from msteamdev.tools.alert_store import get_matching_alerts, read_alert_log, read_escalation_log
from msteamdev.tools.enhanced_tools import (
    read_alert_log_enhanced,
    get_matching_alerts_enhanced,
    check_escalation_eligibility_enhanced,
    get_alert_trends,
    get_system_health
)

# Combine original and enhanced tools
TOOLS = {
    # Original tools (for backward compatibility)
    "GetMatchingAlerts": get_matching_alerts,
    "ReadAlertLog": read_alert_log,
    "ReadEscalationLog": read_escalation_log,
    
    # Enhanced tools with advanced capabilities
    "ReadAlertLogEnhanced": read_alert_log_enhanced,
    "GetMatchingAlertsEnhanced": get_matching_alerts_enhanced,
    "CheckEscalationEligibility": check_escalation_eligibility_enhanced,
    "GetAlertTrends": get_alert_trends,
    "GetSystemHealth": get_system_health,
}

import asyncio

def main():
    """
    Listens for JSON-RPC requests on stdin and sends responses to stdout.
    """
    mcp_logger.info("MCP Stdio Server started.")
    while True:
        try:
            # Read a line from stdin, assuming one line per JSON message
            json_message = sys.stdin.readline()
            if not json_message:
                mcp_logger.info("End of input, exiting.")
                break

            json_message = json_message.strip()
            if not json_message:
                continue

            mcp_logger.info(f"Received request: {json_message}")
            request = json.loads(json_message)

            tool_name = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            if tool_name == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "serverInfo": {
                            "name": "mcp_stdio_server",
                            "version": "0.1.0"
                        },
                        "capabilities": {}
                    },
                    "id": request_id
                }
            elif tool_name == "notifications/initialized":
                mcp_logger.info("Received notifications/initialized request.")
                response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "message": "Initialization complete."
                    },
                    "id": request_id
                }
            elif tool_name == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            # Original tools
                            {
                                "name": "GetMatchingAlerts",
                                "description": "Get alerts that match a specific criteria.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "alert": {
                                            "type": "object",
                                            "description": "The alert to match against."
                                        }
                                    },
                                    "required": ["alert"]
                                }
                            },
                            {
                                "name": "ReadAlertLog",
                                "description": "Read the entire alert log.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            },
                            {
                                "name": "ReadEscalationLog",
                                "description": "Read the entire escalation log.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            },
                            # Enhanced tools
                            {
                                "name": "ReadAlertLogEnhanced",
                                "description": "Read alert log with enhanced filtering, caching, and time window support.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "limit": {"type": "integer", "description": "Maximum alerts to return", "default": 100},
                                        "severity_filter": {"type": "string", "description": "Filter by severity"},
                                        "time_window_hours": {"type": "integer", "description": "Hours to look back"}
                                    },
                                    "required": []
                                }
                            },
                            {
                                "name": "GetMatchingAlertsEnhanced",
                                "description": "Find alerts with enhanced pattern matching and analysis.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "criteria_input": {
                                            "type": "object",
                                            "description": "Alert matching criteria with analysis"
                                        }
                                    },
                                    "required": ["criteria_input"]
                                }
                            },
                            {
                                "name": "CheckEscalationEligibility",
                                "description": "Enhanced escalation check with detailed analysis and business logic.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "incident_number": {"type": "string", "description": "Incident number"},
                                        "severity": {"type": "string", "description": "Alert severity"},
                                        "title": {"type": "string", "description": "Alert title"},
                                        "timestamp": {"type": "string", "description": "Alert timestamp"}
                                    },
                                    "required": ["incident_number", "severity", "title", "timestamp"]
                                }
                            },
                            {
                                "name": "GetAlertTrends",
                                "description": "Analyze alert trends and patterns over time.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "hours": {"type": "integer", "description": "Hours to analyze", "default": 24}
                                    },
                                    "required": []
                                }
                            },
                            {
                                "name": "GetSystemHealth",
                                "description": "Get comprehensive system health metrics and status.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            }
                        ]
                    }
                }
            elif tool_name in TOOLS:
                try:
                    mcp_logger.info(f"Executing tool: {tool_name}")
                    tool_function = TOOLS[tool_name]
                    if asyncio.iscoroutinefunction(tool_function):
                        result = asyncio.run(tool_function(**params))
                    else:
                        result = tool_function(**params)
                    response = {
                        "jsonrpc": "2.0",
                        "result": result,
                        "id": request_id
                    }
                except Exception as e:
                    mcp_logger.error(f"Error executing tool {tool_name}: {e}\n{traceback.format_exc()}")
                    response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": f"Internal error: {e}"},
                        "id": request_id
                    }
            else:
                mcp_logger.warning(f"Tool not found: {tool_name}")
                response = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": "Method not found"},
                    "id": request_id
                }

            response_json = json.dumps(response)
            sys.stdout.write(response_json + '\n') # Write response as a single line
            sys.stdout.flush()
            mcp_logger.info(f"Sent response: {response_json}")

        except json.JSONDecodeError:
            mcp_logger.error(f"Failed to decode JSON from stdin: {json_message}\n{traceback.format_exc()}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
                "id": None
            }
            error_json = json.dumps(error_response)
            sys.stdout.write(error_json + '\n')
            sys.stdout.flush()
        except Exception as e:
            mcp_logger.error(f"An unexpected error occurred: {e}\n{traceback.format_exc()}")
            break

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        mcp_logger.critical(f"Unhandled exception in main: {e}\n{traceback.format_exc()}")