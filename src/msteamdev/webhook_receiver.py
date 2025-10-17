# src/msteamdev/webhook_receiver.py

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from msteamdev.crew import start_alert_pipeline, get_user_email_from_pagerduty
from msteamdev.tools.redis_client import cache_get, cache_set, cache_delete
import json
import os
import re
import time
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path

# FastAPI application for receiving PagerDuty webhooks
app = FastAPI(title="PagerDuty Webhook Receiver")
LOG_PATH = "src/msteamdev/alert_log.json"

# Otobo server URL
OTOBO_SERVER_URL = "http://localhost:7007"

# Configuration flags for filtering
FILTER_ENABLED = True
ALLOWED_STATUSES = ["triggered", "resolved", "acknowledged"]

# CrewAI Knowledge System Configuration
CREWAI_KNOWLEDGE_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "knowledge")
INCIDENT_KNOWLEDGE_FILE = os.path.join(CREWAI_KNOWLEDGE_BASE, "incident_knowledge.json")
PATTERNS_KNOWLEDGE_FILE = os.path.join(CREWAI_KNOWLEDGE_BASE, "alert_patterns.json")
BUSINESS_CONTEXT_FILE = os.path.join(CREWAI_KNOWLEDGE_BASE, "business_context.json")

from msteamdev.logging_setup import get_module_logger

webhook_logger = get_module_logger("webhook_receiver", log_filename="webhook_receiver.log", level=logging.INFO)

def ensure_knowledge_folder():
    """Ensure CrewAI knowledge folder structure exists"""
    try:
        Path(CREWAI_KNOWLEDGE_BASE).mkdir(parents=True, exist_ok=True)
        
        # Initialize files if they don't exist
        for file_path in [INCIDENT_KNOWLEDGE_FILE, PATTERNS_KNOWLEDGE_FILE, BUSINESS_CONTEXT_FILE]:
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    json.dump({}, f)
        
        webhook_logger.info(f"Knowledge folder initialized at {CREWAI_KNOWLEDGE_BASE}")
        return True
    except Exception as e:
        webhook_logger.error(f"Failed to initialize knowledge folder: {e}")
        return False

def extract_severity_from_title(title: str) -> str:
    """Extract severity level from alert title."""
    match = re.search(r"\b(Critical|Warning|High|Medium|Low)\b", title, re.IGNORECASE)
    return match.group(1).lower() if match else "info"

def extract_metric_from_title(title: str) -> str:
    """Extract metric type from alert title."""
    infrastructure_patterns = [
        r"\b(CPU|Memory|Disk|Storage|Network|Bandwidth)\b",
        r"\b(Load|Latency|Response\s*Time|Throughput)\b",
        r"\b(Database|DB|MySQL|PostgreSQL|Redis)\b",
        r"\b(Apache|Nginx|HTTP|HTTPS|SSL)\b",
        r"\b(Docker|Container|Kubernetes|K8s)\b"
    ]
    application_patterns = [
        r"\b(Error\s*Rate|Exception|Crash|Failure)\b",
        r"\b(Queue|Job|Task|Worker)\b",
        r"\b(API|Service|Endpoint|Health\s*Check)\b",
        r"\b(Login|Authentication|Session)\b",
        r"\b(Payment|Transaction|Order)\b"
    ]
    business_patterns = [
        r"\b(Revenue|Sales|Conversion|User\s*Registration)\b",
        r"\b(Traffic|Visitor|Page\s*View|Click)\b"
    ]
    all_patterns = infrastructure_patterns + application_patterns + business_patterns
    
    for pattern in all_patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1).lower().replace(" ", "_")
    
    fallback_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", title)
    if fallback_match:
        return fallback_match.group(1).lower().replace(" ", "_")
    
    return "unknown"

def validate_timestamp(timestamp: str) -> bool:
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

def should_process_alert(status: str) -> bool:
    if not FILTER_ENABLED:
        return True
    return status.lower() in [s.lower() for s in ALLOWED_STATUSES]

def parse_knowledge_from_note(note_content: str) -> List[dict]:
    """Parse structured knowledge from PagerDuty notes using keywords"""
    knowledge_updates = []
    
    # Define knowledge extraction patterns
    patterns = {
        # Root cause patterns
        "root_cause": [
            r"(?i)root\s*cause:?\s*(.+)",
            r"(?i)caused\s*by:?\s*(.+)",
            r"(?i)issue\s*was:?\s*(.+)",
            r"(?i)problem:?\s*(.+)"
        ],
        
        # Resolution patterns  
        "resolution": [
            r"(?i)resolved\s*by:?\s*(.+)",
            r"(?i)fixed\s*by:?\s*(.+)",
            r"(?i)solution:?\s*(.+)",
            r"(?i)action\s*taken:?\s*(.+)"
        ],
        
        # False positive patterns
        "false_positive": [
            r"(?i)false\s*positive",
            r"(?i)false\s*alarm", 
            r"(?i)no\s*actual\s*issue",
            r"(?i)monitoring\s*error",
            r"(?i)threshold\s*too\s*low"
        ],
        
        # Planned maintenance patterns
        "planned_maintenance": [
            r"(?i)planned\s*maintenance",
            r"(?i)scheduled\s*work",
            r"(?i)batch\s*job",
            r"(?i)deployment",
            r"(?i)maintenance\s*window",
            r"(?i)expected\s*activity"
        ],
        
        # Customer feedback patterns
        "customer_feedback": [
            r"(?i)customer\s*(?:says?|confirms?|reports?):?\s*(.+)",
            r"(?i)client\s*(?:says?|confirms?|reports?):?\s*(.+)",
            r"(?i)user\s*feedback:?\s*(.+)"
        ],
        
        # Business context patterns
        "business_context": [
            r"(?i)business\s*impact:?\s*(.+)",
            r"(?i)affects?:?\s*(.+)",
            r"(?i)service\s*impact:?\s*(.+)"
        ]
    }
    
    # Extract knowledge using patterns
    for knowledge_type, pattern_list in patterns.items():
        for pattern in pattern_list:
            matches = re.finditer(pattern, note_content, re.MULTILINE)
            for match in matches:
                if knowledge_type in ["false_positive", "planned_maintenance", "customer_feedback", "business_context"]:
                    # Boolean flags
                    knowledge_updates.append({
                        "type": knowledge_type,
                        "content": match.group(0),
                        "value": True,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                else:
                    # Text content
                    content = match.group(1) if match.groups() else match.group(0)
                    knowledge_updates.append({
                        "type": knowledge_type,
                        "content": content.strip(),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
    
    # Also capture free-form lessons learned
    if len(note_content) > 50:  # Substantial note
        knowledge_updates.append({
            "type": "note_content",
            "content": note_content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    return knowledge_updates

def get_incident_details_from_mcp(incident_id: str) -> Optional[dict]:
    """
    Calls the local MCP server to get full incident details by incident ID.
    """
    mcp_url = "http://localhost:7006/mcp"
    request_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "GetIncidentById",
            "arguments": {"incident_id": incident_id}
        },
        "id": "webhook-receiver-1" # Static ID for this purpose
    }
    try:
        webhook_logger.info(f"Calling MCP server for incident ID: {incident_id}")
        response = requests.post(mcp_url, json=request_payload, timeout=10) # 10 second timeout
        response.raise_for_status()  # Raise an exception for bad status codes
        
        mcp_response = response.json()
        
        if "error" in mcp_response and mcp_response["error"]:
            webhook_logger.error(f"MCP server returned an error: {mcp_response['error']}")
            return None
            
        result_content = mcp_response.get("result", {}).get("content", [])
        if not result_content:
            webhook_logger.error("MCP response is missing result content.")
            return None
            
        # The actual incident data is a JSON string inside the 'text' field
        incident_details_str = result_content[0].get("text", "{}")
        incident_details = json.loads(incident_details_str)
        
        webhook_logger.info(f"Successfully retrieved incident details from MCP: #{incident_details.get('incident_number')}")
        return incident_details
        
    except requests.exceptions.RequestException as e:
        webhook_logger.error(f"Could not connect to MCP server at {mcp_url}: {e}")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        webhook_logger.error(f"Failed to parse MCP server response: {e}")
        return None

def update_incident_summary(incident_data: dict, new_updates: List[dict]):
    """Update incident summary with latest knowledge"""
    summary = incident_data.get("summary", {})
    
    for update in new_updates:
        update_type = update["type"]
        
        if update_type == "root_cause":
            summary["root_cause"] = update["content"]
        elif update_type == "resolution":
            summary["resolution_method"] = update["content"]
        elif update_type == "false_positive":
            summary["false_positive"] = update.get("value", True)
        elif update_type == "planned_maintenance":
            summary["planned_maintenance"] = update.get("value", True)
        elif update_type == "customer_feedback":
            summary["customer_response"] = update.get("value", True)
        elif update_type == "business_context":
            summary["business_impact"] = update.get("value", True)
    
    incident_data["summary"] = summary

def load_knowledge_base() -> dict:
    """Load incident knowledge base"""
    try:
        with open(INCIDENT_KNOWLEDGE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        webhook_logger.error(f"Error loading knowledge base: {e}")
        return {}

def save_knowledge_base(knowledge_base: dict):
    """Save incident knowledge base"""
    try:
        with open(INCIDENT_KNOWLEDGE_FILE, "w") as f:
            json.dump(knowledge_base, f, indent=2, default=str)
    except Exception as e:
        webhook_logger.error(f"Error saving knowledge base: {e}")

async def create_otobo_ticket_with_lock(incident_number: str, alert: dict) -> Optional[str]:
    """
    Creates an Otobo ticket with a Redis distributed lock to prevent race conditions.
    Returns the ticket ID if created or found, otherwise None.
    """
    lock_key = f"otobo_create_lock:{incident_number}"
    ticket_cache_key = f"otobo_ticket:{incident_number}"
    
    # Try to acquire a lock with a 10-second expiry
    # nx=True means set the key only if it does not already exist
    lock_acquired = cache_set(lock_key, "1", nx=True, ex=10)
    
    if not lock_acquired:
        webhook_logger.info(f"Lock not acquired for incident {incident_number}. Waiting for existing ticket.")
        # Another process is creating, wait and retrieve
        time.sleep(0.5) # Small delay to allow other process to complete
        existing_ticket_id = cache_get(ticket_cache_key)
        if existing_ticket_id:
            webhook_logger.info(f"Retrieved existing Otobo ticket {existing_ticket_id} for incident {incident_number}.")
            return existing_ticket_id
        else:
            webhook_logger.warning(f"Lock not acquired and no existing ticket found after waiting for incident {incident_number}. This might indicate a failed previous attempt or a very tight race.")
            return None # Indicate that ticket was not created by this attempt
    
    try:
        # Double-check after acquiring lock, in case it was created between initial check and lock acquisition
        existing_ticket_id = cache_get(ticket_cache_key)
        if existing_ticket_id:
            webhook_logger.info(f"Otobo ticket {existing_ticket_id} found after acquiring lock for incident {incident_number}. Skipping creation.")
            return existing_ticket_id
        
        # Create ticket
        create_payload = {"title": alert["title"], "body": json.dumps(alert, indent=2), "subject": f"Incident {incident_number}: {alert['title']}"}
        response = requests.post(f"{OTOBO_SERVER_URL}/create_ticket", json=create_payload, timeout=10)
        response.raise_for_status()
        ticket_data = response.json().get("ticket_data", {})
        
        if ticket_data and "TicketID" in ticket_data:
            ticket_id = ticket_data["TicketID"]
            ticket_number = ticket_data.get("TicketNumber")
            cache_set(ticket_cache_key, ticket_id, ttl_seconds=86400)  # Cache for 24 hours
            if ticket_number:
                cache_set(f"otobo_ticket_number:{incident_number}", ticket_number, ttl_seconds=86400)  # Cache TicketNumber
            webhook_logger.info(f"Created Otobo ticket {ticket_id} (Number: {ticket_number}) for incident {incident_number}")
            return ticket_id
        else:
            webhook_logger.error(f"Otobo ticket creation failed for incident {incident_number}: No TicketID in response.")
            return None
            
    except Exception as e:
        webhook_logger.error(f"Failed to create Otobo ticket for incident {incident_number} with lock: {e}")
        return None
    finally:
        # Ensure the lock is released
        cache_delete(lock_key)

async def store_incident_knowledge(incident_number: str, knowledge_updates: List[dict], incident_info: dict, note_content: str = None):
    """Store extracted knowledge in CrewAI knowledge folder"""
    try:
        # Load existing knowledge
        knowledge_base = load_knowledge_base()
        
        # Create incident entry if not exists
        if incident_number not in knowledge_base:
            knowledge_base[incident_number] = {
                "incident_number": incident_number,
                "title": incident_info.get("title", ""),
                "severity": incident_info.get("severity", ""),
                "metric": incident_info.get("metric", ""),
                "status": incident_info.get("status", ""),
                "created_at": incident_info.get("timestamp", ""),
                "from_email": incident_info.get("from_email", ""),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "notes": [],
                "knowledge_updates": [],
                "summary": {}
            }
        else: # If incident exists, update the status
            knowledge_base[incident_number]["status"] = incident_info.get("status", knowledge_base[incident_number]["status"])

        # Add the raw note if provided
        if note_content:
            knowledge_base[incident_number]["notes"].append({
                "content": note_content,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "processed_at": datetime.now(timezone.utc).isoformat()
            })
        
        # Add parsed knowledge
        knowledge_base[incident_number]["knowledge_updates"].extend(knowledge_updates)
        knowledge_base[incident_number]["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Update summary
        update_incident_summary(knowledge_base[incident_number], knowledge_updates)
        
        # Save back to CrewAI knowledge folder
        save_knowledge_base(knowledge_base)
        
        webhook_logger.info(f"Knowledge stored in CrewAI folder for incident {incident_number}: {len(knowledge_updates)} updates")
        
    except Exception as e:
        webhook_logger.error(f"Error storing knowledge: {e}")

async def update_pattern_knowledge(incident_info: dict, knowledge_updates: List[dict]):
    """Update pattern recognition knowledge base"""
    try:
        with open(PATTERNS_KNOWLEDGE_FILE, 'r') as f:
            patterns = json.load(f)
        
        metric = incident_info.get("metric", "unknown")
        title = incident_info.get("title", "")
        
        # Initialize metric patterns
        if metric not in patterns:
            patterns[metric] = {
                "metric_name": metric,
                "alert_patterns": {},
                "false_positive_indicators": [],
                "planned_maintenance_indicators": [],
                "customer_feedback_indicators": [],
                "business_context_indicators": [],
                "common_root_causes": {},
                "resolution_methods": {},
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        
        metric_patterns = patterns[metric]
        
        # Process each knowledge update
        for update in knowledge_updates:
            update_type = update["type"]
            content = update["content"]
            
            if update_type == "false_positive":
                if content not in metric_patterns["false_positive_indicators"]:
                    metric_patterns["false_positive_indicators"].append(content)
            
            elif update_type == "planned_maintenance":
                if content not in metric_patterns["planned_maintenance_indicators"]:
                    metric_patterns["planned_maintenance_indicators"].append(content)

            elif update_type == "customer_feedback":
                if content not in metric_patterns["customer_feedback_indicators"]:
                    metric_patterns["customer_feedback_indicators"].append(content)
            
            elif update_type == "business_context":
                if content not in metric_patterns["business_context_indicators"]:
                    metric_patterns["business_context_indicators"].append(content)

            elif update_type == "root_cause":
                root_causes = metric_patterns["common_root_causes"]
                root_causes[content] = root_causes.get(content, 0) + 1
            
            elif update_type == "resolution":
                resolutions = metric_patterns["resolution_methods"]
                resolutions[content] = resolutions.get(content, 0) + 1
        
        metric_patterns["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Save patterns
        with open(PATTERNS_KNOWLEDGE_FILE, 'w') as f:
            json.dump(patterns, f, indent=2, default=str)
        
        webhook_logger.info(f"Updated pattern knowledge for metric: {metric}")
        
    except Exception as e:
        webhook_logger.error(f"Error updating pattern knowledge: {e}")

def detect_webhook_version_and_extract(payload: dict) -> tuple:
    """
    Detect webhook version and extract relevant information
    Returns: (webhook_version, event_type, incident_data, note_content, incident_id)
    """
    # PagerDuty Webhook v3 detection (your new format)
    if "event" in payload and isinstance(payload["event"], dict):
        event = payload["event"]
        event_type = event.get("event_type", "")
        
        # For incident.annotated events - extract note and incident info
        if event_type == "incident.annotated":
            data = event.get("data", {})
            note_content = data.get("content", "")  # Direct content field
            incident_info = data.get("incident", {})  # Incident reference
            incident_id = incident_info.get("id", "")
            
            # Extract incident number from summary if available
            summary = incident_info.get("summary", "")
            incident_number = "unknown"
            
            return ("v3", event_type, incident_info, note_content, incident_id)
        
        # Other v3 events (triggered, resolved, etc.)
        else:
            incident_data = event.get("data", {})
            return ("v3", event_type, incident_data, None, incident_data.get("id", ""))
    
    # Your current webhook format (existing functionality)
    elif isinstance(payload, list) and payload:
        item = payload[0]
        event = item.get("body", {}).get("event", {})
        data = event.get("data", {})
        return ("v2", "incident.triggered", data, None, data.get("id", ""))
    
    # Direct event format (existing functionality)
    elif "event" in payload:
        event = payload["event"]
        data = event.get("data", {})
        return ("v2", "incident.triggered", data, None, data.get("id", ""))
    
    return ("unknown", "", {}, None, "")

@app.post("/pagerduty")
async def receive_alert(request: Request):
    try:
        # Initialize knowledge system
        if not ensure_knowledge_folder():
            webhook_logger.warning("Knowledge system initialization failed, continuing without it")

        raw_payload = await request.body()
        webhook_logger.info(f"Received webhook payload: {raw_payload.decode('utf-8')}")

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as jde:
            webhook_logger.error(f"JSON parsing error: {str(jde)}")
            raise ValueError(f"Invalid JSON format: {str(jde)}")

        # Detect webhook version and extract data
        webhook_version, event_type, data, note_content, incident_id = detect_webhook_version_and_extract(payload)
        webhook_logger.info(f"Detected webhook {webhook_version}, event: {event_type}")

        # Handle annotation events for knowledge extraction (NEW FEATURE)
        if event_type == "incident.annotated" and note_content:
            webhook_logger.info(f"Processing annotation for incident ID: {incident_id}")
            webhook_logger.info(f"Note content: {note_content}")

            # New: Get full incident details from MCP server
            incident_details = get_incident_details_from_mcp(incident_id)

            if not incident_details:
                webhook_logger.error(f"Could not retrieve details for incident ID {incident_id}. Aborting knowledge update.")
                return JSONResponse(
                    content={"status": "error", "message": f"Failed to get incident details for ID {incident_id}"},
                    status_code=500
                )

            incident_number = str(incident_details.get("incident_number", incident_id))
            webhook_logger.info(f"Resolved incident ID {incident_id} to number {incident_number}")

            # OTOBO INTEGRATION: Update Otobo ticket if it exists
            otobo_ticket_id = cache_get(f"otobo_ticket:{incident_number}")
            if otobo_ticket_id:
                try:
                    # Use the local otobo_server.py proxy endpoint
                    otobo_update_url = f"{OTOBO_SERVER_URL}/update_ticket"
                    update_payload = {
                        "ticket_id": str(otobo_ticket_id),
                        "body": f"PagerDuty Note Added:\n\n{note_content}",
                        "subject": f"PagerDuty Note for Incident {incident_number}"
                    }
                    response = requests.post(otobo_update_url, json=update_payload, timeout=10)
                    response.raise_for_status()  # Raise an exception for bad status codes
                    webhook_logger.info(f"Sent update to Otobo for ticket {otobo_ticket_id}")
                except Exception as e:
                    webhook_logger.error(f"Failed to send update to Otobo for ticket {otobo_ticket_id}: {e}")

            # Parse knowledge from note
            knowledge_updates = parse_knowledge_from_note(note_content)

            if knowledge_updates:
                # Use the correct details from the MCP call
                incident_info = {
                    "incident_id": incident_id,
                    "incident_number": incident_number,
                    "title": incident_details.get("title", data.get("summary", "")),
                    "severity": extract_severity_from_title(incident_details.get("title", "")),
                    "metric": extract_metric_from_title(incident_details.get("title", "")),
                    "status": incident_details.get("status", "unknown"),
                    "timestamp": incident_details.get("created_at", payload["event"].get("occurred_at", datetime.now(timezone.utc).isoformat())),
                    "from_email": payload["event"].get("agent", {}).get("summary", "")
                }

                # Use the correct incident_number to store knowledge
                await store_incident_knowledge(incident_number, knowledge_updates, incident_info, note_content)
                await update_pattern_knowledge(incident_info, knowledge_updates)

                webhook_logger.info(f"Stored {len(knowledge_updates)} knowledge updates for incident #{incident_number}")

                return JSONResponse(content={
                    "status": "knowledge_updated",
                    "incident_id": incident_id,
                    "incident_number": incident_number,
                    "updates": len(knowledge_updates),
                })
            else:
                webhook_logger.info(f"No extractable knowledge found in note for incident #{incident_number}")
                return JSONResponse(content={
                    "status": "note_processed",
                    "incident_id": incident_id,
                    "incident_number": incident_number,
                    "message": "Note processed but no structured knowledge extracted"
                })

        # Handle triggered and resolved incidents
        if event_type not in ["incident.annotated"]:
            
            if not data:
                raise ValueError("Missing 'data' in event")

            title = data.get("title") or data.get("summary", "")
            if not title:
                raise ValueError("Missing 'title' in data")

            status = data.get("status", "unknown").lower()
            incident_number = str(data.get("incident_number") or data.get("number") or data.get("id", "unknown"))

            # OTOBO INTEGRATION: Handle resolved status
            if status == "resolved":
                otobo_ticket_id = cache_get(f"otobo_ticket:{incident_number}")
                if otobo_ticket_id:
                    try:
                        resolve_payload = {"ticket_id": str(otobo_ticket_id), "body": "Incident resolved in PagerDuty.", "subject": f"Incident {incident_number} Resolved"}
                        requests.post(f"{OTOBO_SERVER_URL}/resolve_ticket", json=resolve_payload, timeout=10)
                        webhook_logger.info(f"Sent resolve request to Otobo for ticket {otobo_ticket_id}")
                    except Exception as e:
                        webhook_logger.error(f"Failed to send resolve request to Otobo for ticket {otobo_ticket_id}: {e}")
                # Continue processing for logging purposes
            
            # Get timestamp from appropriate field
            occurred_at = data.get("created_at") or data.get("occurred_at") or payload.get("event", {}).get("occurred_at", "unknown")

            if occurred_at != "unknown" and not validate_timestamp(occurred_at):
                raise ValueError("Invalid timestamp format")

            if not should_process_alert(status):
                webhook_logger.info(f"Alert with status '{status}' filtered out. Allowed statuses: {ALLOWED_STATUSES}")
                return JSONResponse(
                    content={"status": "filtered", "message": f"Alert status '{status}' not in allowed list"},
                    status_code=200
                )

            # Extract from_email
            from_email = data.get("from_email")
            if not from_email and data.get("assignees"):
                first_assignee = data["assignees"][0]
                if first_assignee and first_assignee.get("id"):
                    assignee_id = first_assignee["id"]
                    fetched_email = get_user_email_from_pagerduty(assignee_id)
                    if fetched_email:
                        from_email = fetched_email
                else:
                    from_email = os.getenv("SENDER_EMAIL", "noc@infopro.com.my")
            elif not from_email:
                from_email = os.getenv("SENDER_EMAIL", "noc@infopro.com.my")

            alert = {
                "severity": extract_severity_from_title(title),
                "metric": extract_metric_from_title(title),
                "status": status,
                "timestamp": occurred_at,
                "incident_number": incident_number,
                "title": title,
                "original_metric": title,
                "from_email": from_email
            }

            webhook_logger.info(f"Processed alert: {json.dumps(alert, indent=2)}")

            with open(LOG_PATH, "a") as f:
                f.write(json.dumps(alert) + "\n")

            await store_incident_knowledge(str(alert["incident_number"]), [], alert)

            # Only start the pipeline for triggered alerts
            if status == "triggered":
                # OTOBO INTEGRATION: Create ticket for escalated alert
                # Note: This is a simplified approach. A better way would be to call this *after* the crew decides to escalate.
                # For this example, we create the ticket immediately.
                
                # OTOBO INTEGRATION: Create ticket for escalated alert using distributed lock
                # Note: This is a simplified approach. A better way would be to call this *after* the crew decides to escalate.
                # For this example, we create the ticket immediately.
                
                # Use the new function with distributed lock
                await create_otobo_ticket_with_lock(incident_number, alert)

                result = start_alert_pipeline(alert)
                return JSONResponse(content={"status": "received", "result": result})
            else:
                return JSONResponse(content={"status": "processed_non_trigger", "incident_number": incident_number})
        
        else:
            webhook_logger.warning(f"Unhandled event type: {event_type}")
            return JSONResponse(content={"status": "ignored", "event_type": event_type})

    except ValueError as ve:
        webhook_logger.error(f"Payload parsing error: {ve}")
        return JSONResponse(
            content={"status": "error", "message": f"Bad format: {str(ve)}"},
            status_code=400
        )
    except Exception as e:
        webhook_logger.error(f"Processing error: {e}")
        return JSONResponse(
            content={"status": "error", "message": f"Processing error: {str(e)}"},
            status_code=500
        )

@app.get("/knowledge/{incident_number}")
async def get_incident_knowledge(incident_number: str):
    """Get knowledge for a specific incident"""
    try:
        knowledge_base = load_knowledge_base()
        incident_data = knowledge_base.get(incident_number, {})
        
        if incident_data:
            return JSONResponse(content=incident_data)
        else:
            return JSONResponse(
                content={"message": f"No knowledge found for incident {incident_number}"},
                status_code=404
            )
    except Exception as e:
        webhook_logger.error(f"Error retrieving knowledge: {e}")
        return JSONResponse(
            content={"error": str(e)},
            status_code=500
        )

@app.get("/knowledge")
async def get_all_knowledge():
    """Get all stored knowledge"""
    try:
        knowledge_base = load_knowledge_base()
        return JSONResponse(content={
            "total_incidents": len(knowledge_base),
            "incidents": list(knowledge_base.keys()),
            "knowledge_stats": {
                "with_notes": len([k for k, v in knowledge_base.items() if v.get("notes")]),
                "with_root_cause": len([k for k, v in knowledge_base.items() if v.get("summary", {}).get("root_cause")]),
                "false_positives": len([k for k, v in knowledge_base.items() if v.get("summary", {}).get("false_positive")]),
                "planned_maintenance": len([k for k, v in knowledge_base.items() if v.get("summary", {}).get("planned_maintenance")]),
                "customer_feedback": len([k for k, v in knowledge_base.items() if v.get("summary", {}).get("customer_response")]),
                "business_context": len([k for k, v in knowledge_base.items() if v.get("summary", {}).get("business_impact")])
            }
        })
    except Exception as e:
        webhook_logger.error(f"Error retrieving all knowledge: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/config")
def get_config():
    return JSONResponse(content={
        "filter_enabled": FILTER_ENABLED,
        "allowed_statuses": ALLOWED_STATUSES,
        "knowledge_folder": CREWAI_KNOWLEDGE_BASE,
        "knowledge_files": {
            "incidents": os.path.exists(INCIDENT_KNOWLEDGE_FILE),
            "patterns": os.path.exists(PATTERNS_KNOWLEDGE_FILE),
            "business_context": os.path.exists(BUSINESS_CONTEXT_FILE)
        }
    })

@app.post("/config")
async def update_config(request: Request):
    global FILTER_ENABLED, ALLOWED_STATUSES
    try:
        config = await request.json()
        if "filter_enabled" in config:
            FILTER_ENABLED = config["filter_enabled"]
        if "allowed_statuses" in config:
            ALLOWED_STATUSES = config["allowed_statuses"]
        webhook_logger.info(f"Configuration updated: filter_enabled={FILTER_ENABLED}, allowed_statuses={ALLOWED_STATUSES}")
        return JSONResponse(content={
            "status": "updated",
            "filter_enabled": FILTER_ENABLED,
            "allowed_statuses": ALLOWED_STATUSES
        })
    except Exception as e:
        webhook_logger.error(f"Configuration update failed: {e}")
        return JSONResponse(
            content={"status": "error", "message": f"Config update failed: {str(e)}"},
            status_code=400
        )

@app.get("/health")
def health_check():
    knowledge_status = "enabled" if os.path.exists(CREWAI_KNOWLEDGE_BASE) else "disabled"
    return JSONResponse(content={
        "name": "pagerduty-webhook-receiver",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "knowledge_system": knowledge_status,
        "knowledge_folder": CREWAI_KNOWLEDGE_BASE
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7005, log_level="info")
