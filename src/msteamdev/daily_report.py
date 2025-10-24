import os
import json
import logging
import smtplib
import requests
import arrow
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple, Union
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from crewai import Agent, Task, Crew
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import logging setup
from src.msteamdev.logging_setup import get_module_logger

# Configure logging
logger = get_module_logger(__name__, log_filename='report.log')

# Configure timezone
LOCAL_TZ_NAME = os.getenv("LOCAL_TZ_NAME", "Asia/Kuala_Lumpur")

# Import models and tools
from src.msteamdev.models import (
    ReportMetadata,
    ShiftReportOutput,
    AlertDetail,
    AlertMatchCriteria,
)
from src.msteamdev.crew import load_agents, load_yaml
from src.msteamdev.tools.alert_cache import ALERT_CACHE
from src.msteamdev.tools.report_metrics import REPORT_METRICS, ReportGenerationMetric

class ShiftConfig:
    """Centralized shift configuration."""
    SHIFT_MORNING_START = 7
    SHIFT_MORNING_END = 16
    SHIFT_EVENING_START = 16
    SHIFT_EVENING_END = 23
    ESCALATION_DELAY_MINUTES = int(os.getenv("ESCALATION_DELAY_MINUTES", "25"))
    CRITICAL_ALERT_THRESHOLD_RED = int(os.getenv("CRITICAL_ALERT_THRESHOLD_RED", "5"))
    CRITICAL_ALERT_THRESHOLD_AMBER = int(os.getenv("CRITICAL_ALERT_THRESHOLD_AMBER", "3"))
    ESCALATED_ALERT_THRESHOLD_RED = int(os.getenv("ESCALATED_ALERT_THRESHOLD_RED", "3"))
    ESCALATED_ALERT_THRESHOLD_AMBER = int(os.getenv("ESCALATED_ALERT_THRESHOLD_AMBER", "2"))


def parse_ts_utc(ts: Optional[str]) -> arrow.arrow.Arrow:
    """Parse an ISO timestamp string and return an Arrow object in UTC.
    
    Accepts ISO timestamps in any of these formats:
    - With Z suffix (e.g., 2025-10-21T00:42:01Z)
    - With timezone offset (e.g., 2025-10-21T00:42:01+00:00)
    - Without timezone (assumed UTC)
    
    Returns arrow.Arrow in UTC.
    """
    if not ts:
        raise ValueError("Empty timestamp")
    
    try:
        # arrow.get() handles most ISO formats automatically
        parsed = arrow.get(ts)
        
        # For timestamps without explicit timezone, treat as UTC
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo='UTC')
            
        # Convert to UTC
        utc_ts = parsed.to('UTC')
        
        # Verify the timestamp is reasonable (not too far in past/future)
        now = arrow.utcnow()
        if utc_ts.year < 2020 or utc_ts.year > 2030:
            raise ValueError(f"Timestamp year {utc_ts.year} outside reasonable range")
            
        return utc_ts
        
    except (arrow.parser.ParserError, ValueError) as e:
        raise ValueError(f"Invalid timestamp format: {ts}") from e


def to_local_str(ts_arrow: arrow.arrow.Arrow, fmt: str = 'YYYY-MM-DD HH:mm:ss') -> str:
    """Convert an Arrow UTC timestamp to the local timezone and format as string."""
    return ts_arrow.to(LOCAL_TZ_NAME).format(fmt)


def _load_log_sync() -> List[Dict[str, Any]]:
    """Load alert log synchronously."""
    try:
        log_file = os.path.join(os.path.dirname(__file__), "alert_log.json")
        with open(log_file, 'r') as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning(f"Alert log file not found")
        return []


def load_alerts(start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
    """Load alerts for the specified time period.
    
    Args:
        start_time: Start of the search window (timezone-aware datetime)
        end_time: End of the search window (timezone-aware datetime)
        
    Returns:
        List of matching alert dictionaries with final status for each incident
    """
    # Load from cache
    alerts, last_update, source = ALERT_CACHE.get_alerts(force_refresh=True)
    logger.info(f"Loaded {len(alerts)} total alerts from {source}")
    
    # Convert start/end times to UTC Arrow objects for comparison
    try:
        if start_time.tzinfo is None:
            start_arrow = arrow.get(start_time, LOCAL_TZ_NAME).to('UTC')
        else:
            start_arrow = arrow.get(start_time).to('UTC')
            
        if end_time.tzinfo is None:
            end_arrow = arrow.get(end_time, LOCAL_TZ_NAME).to('UTC')
        else:
            end_arrow = arrow.get(end_time).to('UTC')
        
        logger.info(f"Search window UTC: {start_arrow.format('YYYY-MM-DD HH:mm:ss ZZ')} to {end_arrow.format('YYYY-MM-DD HH:mm:ss ZZ')}")
        logger.info(f"Search window Local: {start_arrow.to(LOCAL_TZ_NAME).format('YYYY-MM-DD HH:mm:ss ZZ')} to {end_arrow.to(LOCAL_TZ_NAME).format('YYYY-MM-DD HH:mm:ss ZZ')}")
        
    except Exception as e:
        logger.error(f"Error converting search window times: {e}")
        return []

    # Track incident state transitions
    incident_states = {}
    valid_count = 0
    invalid_count = 0
    outside_window_count = 0
    
    # Status priority: resolved > acknowledged > triggered
    STATUS_PRIORITY = {
        'resolved': 3,
        'acknowledged': 2,
        'triggered': 1
    }
    
    # Process each alert in order (they're already in chronological order in the log)
    for idx, alert in enumerate(alerts):
        try:
            incident_number = str(alert.get('incident_number', ''))
            if not incident_number:
                continue
            
            # Parse alert timestamp
            timestamp = alert.get('timestamp')
            try:
                alert_arrow = parse_ts_utc(timestamp)
                valid_count += 1
            except ValueError:
                invalid_count += 1
                logger.debug(f"Invalid timestamp for alert {incident_number}: {timestamp}")
                continue
            
            # Check if in window
            in_window = start_arrow <= alert_arrow <= end_arrow
            
            if in_window:
                status = alert.get('status', '').lower()
                
                # Initialize incident tracking if not exists
                if incident_number not in incident_states:
                    incident_states[incident_number] = {
                        'first_alert': alert,
                        'current_alert': alert,
                        'status_sequence': [status],
                        'timestamps': [alert_arrow],
                        'log_order': idx
                    }
                    logger.debug(f"New incident {incident_number} with status '{status}' at {to_local_str(alert_arrow)}")
                else:
                    # Update incident state
                    state = incident_states[incident_number]
                    state['status_sequence'].append(status)
                    state['timestamps'].append(alert_arrow)
                    state['log_order'] = idx  # Track latest position in log
                    
                    # Determine which alert to keep based on:
                    # 1. Higher status priority (resolved > acknowledged > triggered)
                    # 2. If same priority, keep the later one in the log
                    current_priority = STATUS_PRIORITY.get(state['current_alert'].get('status', '').lower(), 0)
                    new_priority = STATUS_PRIORITY.get(status, 0)
                    
                    if new_priority > current_priority:
                        state['current_alert'] = alert
                        logger.debug(f"Updated incident {incident_number} to higher priority status '{status}' at {to_local_str(alert_arrow)}")
                    elif new_priority == current_priority:
                        # Same priority - this is a duplicate or re-notification, keep the latest in log
                        state['current_alert'] = alert
                        logger.debug(f"Updated incident {incident_number} to same status '{status}' (later in log)")
            else:
                outside_window_count += 1
                    
        except Exception as e:
            logger.error(f"Error processing alert {alert.get('incident_number', 'Unknown')}: {str(e)}")
            continue
    
    # Extract final state for each incident
    filtered_alerts = []
    for incident_number, state in incident_states.items():
        final_alert = state['current_alert']
        final_status = final_alert.get('status', '').lower()
        
        logger.debug(f"Incident {incident_number} final state: {final_status}")
        logger.debug(f"  Status sequence: {' -> '.join(state['status_sequence'])}")
        
        filtered_alerts.append(final_alert)
    
    logger.info(f"Alert filtering summary:")
    logger.info(f"  - Valid timestamps: {valid_count}")
    logger.info(f"  - Invalid timestamps: {invalid_count}")
    logger.info(f"  - Outside window: {outside_window_count}")
    logger.info(f"  - Unique incidents in window: {len(filtered_alerts)}")
    
    # Log final status distribution
    status_counts = {}
    for alert in filtered_alerts:
        status = alert.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    logger.info(f"  - Final status distribution: {status_counts}")
    
    return filtered_alerts


def check_escalation_eligibility(alert_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Check if an alert was actually escalated by checking the escalation log."""
    try:
        log_file = os.path.join(os.path.dirname(__file__), "escalation_log.json")
        with open(log_file, 'r') as f:
            for line in f:
                escalation = json.loads(line)
                if str(escalation.get('incident_number')) == str(alert_data.get('incident_number')):
                    if escalation.get('escalated', False):
                        return True, escalation.get('reason', 'Alert was escalated')
                    return False, "Alert was not escalated"
        return False, "No escalation record found"
    except FileNotFoundError:
        logger.warning(f"Escalation log file not found at {log_file}")
        return False, "Escalation log not found"
    except Exception as e:
        logger.error(f"Error checking escalation status: {e}")
        return False, f"Error checking escalation: {str(e)}"


def check_resolution_status(alert: dict, delay_minutes: int) -> bool:
    """Check if alert was resolved within delay period."""
    alerts = _load_log_sync()
    incident_number = alert.get("incident_number")
    
    try:
        current_time = parse_ts_utc(alert.get("timestamp"))
        cutoff_time = current_time.shift(minutes=+delay_minutes)
    except ValueError:
        return False

    for logged_alert in alerts:
        try:
            alert_time = parse_ts_utc(logged_alert.get("timestamp"))
            if (logged_alert.get("incident_number") == incident_number and
                logged_alert.get("status") == "resolved" and
                current_time <= alert_time <= cutoff_time):
                return True
        except ValueError:
            continue
    return False


def build_incident_states(alerts: List[dict], incident_numbers_in_window: set) -> Dict[str, Dict]:
    """
    Build comprehensive incident state tracking with timing information.
    
    Args:
        alerts: All alerts from alert_log.json
        incident_numbers_in_window: Set of incident numbers in the shift window
        
    Returns:
        Dictionary mapping incident numbers to their state tracking data
    """
    incident_states = {}
    
    for alert in alerts:
        inc_num = str(alert.get('incident_number'))
        if inc_num not in incident_numbers_in_window:
            continue
            
        status = alert.get("status", "").lower()
        
        try:
            timestamp = parse_ts_utc(alert.get('timestamp'))
        except ValueError:
            continue
        
        if inc_num not in incident_states:
            incident_states[inc_num] = {
                'triggered_at': None,
                'acknowledged_at': None,
                'resolved_at': None,
                'severity': alert.get("severity", "").lower(),
                'final_status': status,
                'all_statuses': []
            }
        
        state = incident_states[inc_num]
        state['all_statuses'].append((status, timestamp))
        state['final_status'] = status  # Keep updating to get final status
        
        # Track timing for each state (keep earliest occurrence for triggered/acknowledged, latest for resolved)
        if status == 'triggered' and state['triggered_at'] is None:
            state['triggered_at'] = timestamp
        elif status == 'acknowledged' and state['acknowledged_at'] is None:
            state['acknowledged_at'] = timestamp
        elif status == 'resolved':
            state['resolved_at'] = timestamp  # Keep updating to get final resolution time
    
    return incident_states


def calculate_time_to_resolve(triggered_at: arrow.arrow.Arrow, resolved_at: arrow.arrow.Arrow) -> str:
    """
    Calculate human-readable time to resolve.
    
    Args:
        triggered_at: Arrow timestamp when incident was triggered
        resolved_at: Arrow timestamp when incident was resolved
        
    Returns:
        Human-readable duration string (e.g., "1h 23m" or "45m")
    """
    try:
        duration = resolved_at - triggered_at
        total_seconds = duration.total_seconds()
        
        if total_seconds < 0:
            return "Invalid (negative duration)"
        
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
            
    except Exception as e:
        logger.error(f"Error calculating TTR: {e}")
        return "Calculation error"


def create_alert_details_with_timing(alerts: List[dict], incident_states: Dict[str, Dict]) -> List[AlertDetail]:
    """
    Create AlertDetail objects with comprehensive timing information.
    
    Args:
        alerts: List of alert dictionaries (final state for each incident)
        incident_states: Dictionary mapping incident numbers to their state tracking data
        
    Returns:
        List of AlertDetail objects with complete timing data
    """
    alert_summary = []
    
    for alert in alerts:
        try:
            incident_number = str(alert.get('incident_number'))
            state = incident_states.get(incident_number, {})
            
            # Get escalation info
            eligible, reason = check_escalation_eligibility(alert)
            was_resolved = check_resolution_status(alert, ShiftConfig.ESCALATION_DELAY_MINUTES)
            escalation_status = "Escalated" if eligible and not was_resolved else "Not Escalated"
            
            # Format primary timestamp
            try:
                alert_ts = parse_ts_utc(alert.get('timestamp'))
                alert_timestamp_local = to_local_str(alert_ts)
            except:
                alert_timestamp_local = 'Unknown'
            
            # Extract timing information from state tracking
            acknowledged_at = None
            resolved_at = None
            first_response_at = None
            
            if state:
                # Format timestamps for display
                if state.get('acknowledged_at'):
                    acknowledged_at = to_local_str(state['acknowledged_at'])
                    if not first_response_at:
                        first_response_at = acknowledged_at
                
                if state.get('resolved_at'):
                    resolved_at = to_local_str(state['resolved_at'])
                    if not first_response_at:
                        first_response_at = resolved_at
            
            # Create AlertDetail with all timing information
            alert_summary.append(AlertDetail(
                incident_number=int(alert.get('incident_number', 0)),
                title=alert.get('title', 'Unknown'),
                severity=alert.get('severity', 'Unknown').upper(),
                metric=alert.get('metric', 'Unknown'),
                status=alert.get('status', 'Unknown'),
                timestamp=alert_timestamp_local,
                escalation_status=escalation_status,
                escalation_reason=reason if not was_resolved else 'Resolved within delay period',
                acknowledged_at=acknowledged_at,
                resolved_at=resolved_at,
                first_response_at=first_response_at
            ))
            
        except Exception as e:
            logger.error(f"Failed to process alert {alert.get('incident_number')}: {e}")
    
    return alert_summary


def calculate_shift_kpis(alerts: List[dict], shift_start: arrow.arrow.Arrow, shift_end: arrow.arrow.Arrow) -> dict:
    """Calculate key operational metrics for the shift."""
    logger.info(f"Calculating KPIs for {len(alerts)} alerts")
    
    if not alerts:
        logger.info("No alerts to calculate KPIs for")
        return {
            "total_alerts": 0,
            "unique_alerts": 0,
            "resolved_alerts": 0,
            "acknowledged_alerts": 0,
            "critical_alerts": 0,
            "warning_alerts": 0,
            "escalated_alerts": 0,
            "resolution_rate": "0.0%",
            "acknowledgment_rate": "0.0%",
            "escalation_rate": "0.0%",
            "mean_time_to_resolve": "N/A",
            "mean_time_to_acknowledge": "N/A",
            "mean_time_to_first_response": "N/A",
            "sla_breaches": 0,
            "sla_compliance": "N/A",
            "sla_compliance_percentage": "N/A"
        }
    
    # Load all alerts to track full state progression
    all_alerts = _load_log_sync()
    
    # Track state transitions for each incident
    incident_states = {}
    
    # First, identify which incidents are in our window
    incident_numbers_in_window = set()
    for alert in alerts:
        incident_numbers_in_window.add(str(alert.get('incident_number')))
    
    logger.info(f"Tracking state transitions for {len(incident_numbers_in_window)} incidents")
    
    # Process all alerts to track state transitions for incidents in our window
    for alert in all_alerts:
        inc_num = str(alert.get('incident_number'))
        if inc_num not in incident_numbers_in_window:
            continue
            
        status = alert.get("status", "").lower()
        
        try:
            timestamp = parse_ts_utc(alert.get('timestamp'))
        except ValueError:
            continue
        
        if inc_num not in incident_states:
            incident_states[inc_num] = {
                'triggered_at': None,
                'acknowledged_at': None,
                'resolved_at': None,
                'severity': alert.get("severity", "").lower(),
                'final_status': status,
                'all_statuses': []
            }
        
        state = incident_states[inc_num]
        state['all_statuses'].append((status, timestamp))
        state['final_status'] = status  # Keep updating to get final status
        
        # Track timing for each state (keep earliest occurrence)
        if status == 'triggered' and state['triggered_at'] is None:
            state['triggered_at'] = timestamp
        elif status == 'acknowledged' and state['acknowledged_at'] is None:
            state['acknowledged_at'] = timestamp
        elif status == 'resolved':
            state['resolved_at'] = timestamp  # Keep updating to get final resolution time
    
    # Calculate metrics based on final states
    unique_alerts = len(incident_states)
    resolved_alerts = sum(1 for state in incident_states.values() if state['final_status'] == 'resolved')
    acknowledged_alerts = sum(1 for state in incident_states.values() if state['final_status'] in ['acknowledged', 'resolved'])
    active_alerts = sum(1 for state in incident_states.values() if state['final_status'] != 'resolved')
    critical_alerts = sum(1 for state in incident_states.values() if state['severity'] == 'critical')
    warning_alerts = sum(1 for state in incident_states.values() if state['severity'] == 'warning')
    
    logger.info(f"Status summary:")
    logger.info(f"  - Unique incidents: {unique_alerts}")
    logger.info(f"  - Resolved: {resolved_alerts}")
    logger.info(f"  - Acknowledged: {acknowledged_alerts}")
    logger.info(f"  - Active: {active_alerts}")
    logger.info(f"  - Critical: {critical_alerts}")
    logger.info(f"  - Warning: {warning_alerts}")
    
    # Calculate timing metrics
    ttr_values = []  # Time to resolve
    tta_values = []  # Time to acknowledge
    ttfr_values = []  # Time to first response
    
    for inc_num, state in incident_states.items():
        if state['triggered_at']:
            # Time to acknowledge
            if state['acknowledged_at']:
                tta = (state['acknowledged_at'] - state['triggered_at']).total_seconds() / 60
                if tta >= 0:
                    tta_values.append(tta)
                    ttfr_values.append(tta)  # First response was acknowledgment
                    logger.debug(f"Incident {inc_num}: TTA = {tta:.1f}m")
            
            # Time to resolve
            if state['resolved_at']:
                ttr = (state['resolved_at'] - state['triggered_at']).total_seconds() / 60
                if ttr >= 0:
                    ttr_values.append(ttr)
                    # If resolved without acknowledgment, count as first response
                    if not state['acknowledged_at']:
                        ttfr_values.append(ttr)
                    logger.debug(f"Incident {inc_num}: TTR = {ttr:.1f}m")
    
    # Calculate escalations based on actual escalation records
    escalated_alerts = []
    for alert in alerts:
        is_escalated, reason = check_escalation_eligibility(alert)
        if is_escalated:
            escalated_alerts.append(alert)
            logger.info(f"Found escalated alert {alert.get('incident_number')}: {reason}")
    
    # Calculate rates
    resolution_rate = (resolved_alerts / unique_alerts * 100) if unique_alerts > 0 else 0.0
    ack_rate = (acknowledged_alerts / unique_alerts * 100) if unique_alerts > 0 else 0.0
    escalation_rate = (len(escalated_alerts) / unique_alerts * 100) if unique_alerts > 0 else 0.0
    
    # Calculate averages
    mean_time_to_resolve = f"{sum(ttr_values) / len(ttr_values):.1f}m" if ttr_values else "N/A"
    mean_time_to_acknowledge = f"{sum(tta_values) / len(tta_values):.1f}m" if tta_values else "N/A"
    mean_time_to_first_response = f"{sum(ttfr_values) / len(ttfr_values):.1f}m" if ttfr_values else "N/A"
    
    # SLA metrics (30 minute response SLA)
    sla_threshold = 30
    sla_breaches = sum(1 for t in ttfr_values if t > sla_threshold)
    total_with_sla = len(ttfr_values)
    sla_compliance = f"{((total_with_sla - sla_breaches) / total_with_sla * 100):.1f}%" if total_with_sla > 0 else "N/A"
    
    logger.info(f"Timing metrics:")
    logger.info(f"  - MTTR: {mean_time_to_resolve}")
    logger.info(f"  - MTTA: {mean_time_to_acknowledge}")
    logger.info(f"  - MTTR: {mean_time_to_first_response}")
    logger.info(f"  - SLA breaches: {sla_breaches}/{total_with_sla}")
    logger.info(f"  - SLA compliance: {sla_compliance}")
    
    return {
        "total_alerts": len(alerts),
        "unique_alerts": unique_alerts,
        "resolved_alerts": resolved_alerts,
        "acknowledged_alerts": acknowledged_alerts,
        "critical_alerts": critical_alerts,
        "warning_alerts": warning_alerts,
        "escalated_alerts": escalated_alerts,
        "resolution_rate": f"{resolution_rate:.1f}%",
        "acknowledgment_rate": f"{ack_rate:.1f}%",
        "escalation_rate": f"{escalation_rate:.1f}%",
        "mean_time_to_resolve": mean_time_to_resolve,
        "mean_time_to_acknowledge": mean_time_to_acknowledge,
        "mean_time_to_first_response": mean_time_to_first_response,
        "sla_breaches": sla_breaches,
        "sla_compliance": sla_compliance,
        "sla_compliance_percentage": sla_compliance
    }


def create_metadata(alerts: Optional[List[Dict[str, Any]]] = None) -> ReportMetadata:
    """Create report metadata."""
    now = datetime.now(timezone.utc)
    
    if not alerts:
        return ReportMetadata(
            generation_timestamp=now.isoformat(),
            alert_count=0,
            critical_alerts=0,
            sla_breaches=0,
            mttr_minutes=0.0
        )
    
    critical_count = sum(1 for a in alerts if a.get('severity') == 'critical')
    sla_breaches = 0  # Calculate if needed
    
    # Calculate MTTR for resolved alerts
    resolved_alerts = []
    for a in alerts:
        if a.get('status') == 'resolved' and a.get('timestamp'):
            try:
                resolved_alerts.append(a)
            except:
                pass
    
    mttr = 0.0
    if resolved_alerts:
        try:
            total_time = 0
            count = 0
            for a in resolved_alerts:
                try:
                    created = parse_ts_utc(a['timestamp'])
                    # Assume resolution time is proportional to number of state changes
                    # This is a simplification - adjust based on your data
                    count += 1
                except:
                    pass
            if count > 0:
                mttr = total_time / count / 60  # Convert to minutes
        except:
            pass
    
    return ReportMetadata(
        generation_timestamp=now.isoformat(),
        alert_count=len(alerts),
        critical_alerts=critical_count,
        sla_breaches=sla_breaches,
        mttr_minutes=mttr
    )


def send_report_email(subject: str, body: str, report_metadata: Optional[ReportMetadata] = None) -> bool:
    """Send the report via email."""
    smtp_host = os.getenv('SMTP_HOST', '')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_username = os.getenv('SMTP_USERNAME', '')
    smtp_password = os.getenv('SMTP_PASSWORD', '')
    report_email = os.getenv('REPORT_EMAIL', '')
    
    if not all([smtp_host, smtp_username, smtp_password, report_email]):
        logger.error("Missing SMTP configuration")
        return False
        
    try:
        logger.info(f"Preparing to send email to {report_email}")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = formataddr((str(Header('NOC Team', 'utf-8')), 'noc@infopro.com.my'))
        msg['To'] = report_email
        
        text = MIMEText(body, 'plain')
        msg.attach(text)

        logger.info(f"Connecting to SMTP server {smtp_host}:{smtp_port}")
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            logger.info(f"Successfully sent shift report email to {msg['To']}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return False


def send_rocketchat_webhook_message(message: str) -> bool:
    """Send a message to Rocket.Chat via webhook."""
    webhook_url = os.getenv("ROCKETCHAT_WEBHOOK_URL", "")
    
    if not webhook_url:
        logger.warning("ROCKETCHAT_WEBHOOK_URL not configured")
        return False
        
    webhook_token = os.getenv("ROCKETCHAT_WEBHOOK_TOKEN")
    if webhook_token and webhook_token not in webhook_url:
        webhook_url = f"{webhook_url}/{webhook_token}"
    
    try:
        payload = {
            "text": message,
            "alias": "NOC Shift Report",
            "emoji": ":memo:"
        }
        response = requests.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Successfully sent Rocket.Chat webhook notification")
            return True
        else:
            logger.error(f"Rocket.Chat webhook failed: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Rocket.Chat webhook: {str(e)}")
        return False


def extract_report_output(result: Any, logger: logging.Logger) -> ShiftReportOutput:
    """Extract report output from crew result."""
    try:
        if hasattr(result, 'pydantic') and result.pydantic:
            logger.info("Using pydantic structured output")
            return result.pydantic
            
        elif hasattr(result, 'json_dict') and result.json_dict:
            logger.info("Using json_dict output")
            return ShiftReportOutput(**result.json_dict)
            
        elif hasattr(result, 'raw') and result.raw:
            logger.info("Parsing raw output")
            lines = result.raw.split('\n')
            subject = lines[0] if lines else "NOC Shift Report"
            body = '\n'.join(lines[1:]) if len(lines) > 1 else "No content available"
            
            return ShiftReportOutput(
                subject=subject,
                body=body,
                metadata=create_metadata()
            )
    except Exception as e:
        logger.error(f"Failed to extract report: {e}")
    
    # Fallback
    return ShiftReportOutput(
        subject="NOC Shift Report",
        body="Report generation encountered an error.",
        metadata=create_metadata()
    )


def run(shift_type: Optional[str] = None, shift_start: Optional[datetime] = None, shift_end: Optional[datetime] = None):
    """Run the shift report task."""
    
    # Get current time in local timezone
    now_local = arrow.now(LOCAL_TZ_NAME)
    
    # Determine shift type
    if shift_type is None:
        current_hour = now_local.hour
        if ShiftConfig.SHIFT_MORNING_START <= current_hour < ShiftConfig.SHIFT_MORNING_END:
            shift_type = "morning"
        elif ShiftConfig.SHIFT_EVENING_START <= current_hour < ShiftConfig.SHIFT_EVENING_END:
            shift_type = "evening"
        else:
            shift_type = "morning"
    
    logger.info(f"Starting {shift_type} shift report generation at {now_local.format('YYYY-MM-DD HH:mm:ss ZZ')}")
    
    # Set shift times
    if shift_start is None or shift_end is None:
        current_hour = now_local.hour
        
        if shift_type == "morning":
            if current_hour < ShiftConfig.SHIFT_MORNING_START:
                shift_start_local = now_local.shift(days=-1).replace(hour=ShiftConfig.SHIFT_MORNING_START, minute=0, second=0, microsecond=0)
                shift_end_local = now_local.shift(days=-1).replace(hour=ShiftConfig.SHIFT_MORNING_END, minute=0, second=0, microsecond=0)
            else:
                shift_start_local = now_local.replace(hour=ShiftConfig.SHIFT_MORNING_START, minute=0, second=0, microsecond=0)
                shift_end_local = now_local.replace(hour=ShiftConfig.SHIFT_MORNING_END, minute=0, second=0, microsecond=0)
        else:
            if current_hour < ShiftConfig.SHIFT_EVENING_START:
                shift_start_local = now_local.shift(days=-1).replace(hour=ShiftConfig.SHIFT_EVENING_START, minute=0, second=0, microsecond=0)
                shift_end_local = now_local.shift(days=-1).replace(hour=ShiftConfig.SHIFT_EVENING_END, minute=0, second=0, microsecond=0)
            else:
                shift_start_local = now_local.replace(hour=ShiftConfig.SHIFT_EVENING_START, minute=0, second=0, microsecond=0)
                shift_end_local = now_local.replace(hour=ShiftConfig.SHIFT_EVENING_END, minute=0, second=0, microsecond=0)
        
        shift_start = shift_start_local.datetime
        shift_end = shift_end_local.datetime
    
    logger.info(f"Shift window: {shift_start} to {shift_end}")
    
    # Load alerts
    alerts = load_alerts(shift_start, shift_end)
    logger.info(f"Processing {len(alerts)} alerts for report")
    
    # Load agents and tasks
    agents = load_agents()
    tasks_def = load_yaml("src/msteamdev/config/tasks_enhanced.yaml")
    
    reporter_agent = agents.get("reporter")
    if not reporter_agent:
        logger.error("Missing reporter agent")
        return
    
    report_task_def = tasks_def.get("shift_report")
    if not report_task_def:
        logger.error("Missing shift_report task definition")
        return
    
    # Process alerts
    alert_summary = []
    for alert in alerts:
        try:
            eligible, reason = check_escalation_eligibility(alert)
            was_resolved = check_resolution_status(alert, ShiftConfig.ESCALATION_DELAY_MINUTES)
            escalation_status = "Escalated" if eligible and not was_resolved else "Not Escalated"
            
            try:
                alert_ts = parse_ts_utc(alert.get('timestamp'))
                alert_timestamp_local = to_local_str(alert_ts)
            except:
                alert_timestamp_local = 'Unknown'

            alert_summary.append(AlertDetail(
                incident_number=int(alert.get('incident_number', 0)),
                title=alert.get('title', 'Unknown'),
                severity=alert.get('severity', 'Unknown').upper(),
                metric=alert.get('metric', 'Unknown'),
                status=alert.get('status', 'Unknown'),
                timestamp=alert_timestamp_local,
                escalation_status=escalation_status,
                escalation_reason=reason if not was_resolved else 'Resolved within delay period'
            ))
        except Exception as e:
            logger.error(f"Failed to process alert {alert.get('incident_number')}: {e}")
    
    # Calculate KPIs
    shift_start_arrow = arrow.get(shift_start)
    shift_end_arrow = arrow.get(shift_end)
    
    # Calculate metrics including escalations from escalation log
    escalated_alerts = []
    for alert in alerts:
        is_escalated, reason = check_escalation_eligibility(alert)
        if is_escalated:
            escalated_alerts.append(alert)
            logger.info(f"Found escalated alert {alert.get('incident_number')}: {reason}")
    
    # Calculate all metrics
    shift_kpis = calculate_shift_kpis(alerts, shift_start_arrow, shift_end_arrow)
    
    # Determine report status based on actual escalation count from escalation log
    critical_count = sum(1 for alert in alerts if alert.get('severity', '').lower() == 'critical')
    escalated_count = len(escalated_alerts)
    
    if (critical_count >= ShiftConfig.CRITICAL_ALERT_THRESHOLD_RED or 
        escalated_count >= ShiftConfig.ESCALATED_ALERT_THRESHOLD_RED):
        report_status_emoji = "🔴"
        report_status_text = "RED"
    elif (critical_count >= ShiftConfig.CRITICAL_ALERT_THRESHOLD_AMBER or 
          escalated_count >= ShiftConfig.ESCALATED_ALERT_THRESHOLD_AMBER):
        report_status_emoji = "🟡"
        report_status_text = "AMBER"
    else:
        report_status_emoji = "🟢"
        report_status_text = "GREEN"
    
    logger.info(f"Report status: {report_status_text} (Critical: {critical_count}, Escalated: {escalated_count})")
    
    # Format data for task
    shift_start_local = arrow.get(shift_start).to(LOCAL_TZ_NAME).format('YYYY-MM-DD HH:mm:ss')
    shift_end_local = arrow.get(shift_end).to(LOCAL_TZ_NAME).format('YYYY-MM-DD HH:mm:ss')
    report_date = arrow.get(shift_start).to(LOCAL_TZ_NAME).format('YYYY-MM-DD')
    
    alert_summary_dicts = [alert.model_dump() for alert in alert_summary]
    alert_details_str = json.dumps(alert_summary_dicts, indent=2) if alert_summary_dicts else 'No alerts recorded.'
    
    active_incidents = [alert for alert in alert_summary if alert.status != 'resolved']
    resolved_incidents = [alert for alert in alert_summary if alert.status == 'resolved']
    
    active_incidents_data = "\n".join([f"- {inc.title} (Severity: {inc.severity})" for inc in active_incidents]) or "No active incidents"
    resolved_incidents_data = "\n".join([f"- {inc.title} (Severity: {inc.severity})" for inc in resolved_incidents]) or "No resolved incidents"
    
    # Create task
    report_task = Task(
        description=report_task_def["description"].format(
            shift_start=shift_start_local,
            shift_end=shift_end_local,
            shift_type=shift_type.capitalize(),
            total_alerts=len(alerts),
            unique_alerts=len(set(str(a.get('incident_number')) for a in alerts)),
            critical_alerts=critical_count,
            warning_alerts=sum(1 for a in alerts if a.get('severity', '').lower() == 'warning'),
            resolved_alerts=sum(1 for a in alerts if a.get('status', '').lower() == 'resolved'),
            acknowledged_alerts=sum(1 for a in alerts if a.get('status', '').lower() in ['acknowledged', 'resolved']),
            escalated_alerts=escalated_count,
            alert_details=alert_details_str,
            report_status_text=report_status_text,
            report_status_emoji=report_status_emoji,
            active_incidents_data=active_incidents_data,
            resolved_incidents_data=resolved_incidents_data,
            report_date=report_date,
            mttr_acknowledge=shift_kpis.get('mean_time_to_acknowledge', 'N/A'),
            mttr_resolve=shift_kpis.get('mean_time_to_resolve', 'N/A'),
            mttr_first_response=shift_kpis.get('mean_time_to_first_response', 'N/A'),
            escalation_rate=f"{(escalated_count / len(alerts) * 100):.1f}%" if alerts else "0.0%",
            resolution_rate=f"{(sum(1 for a in alerts if a.get('status', '').lower() == 'resolved') / len(alerts) * 100):.1f}%" if alerts else "0.0%",
            acknowledgment_rate=f"{(sum(1 for a in alerts if a.get('status', '').lower() in ['acknowledged', 'resolved']) / len(alerts) * 100):.1f}%" if alerts else "0.0%",
            sla_compliance=shift_kpis.get('sla_compliance_percentage', 'N/A'),
            sla_breaches=shift_kpis.get('sla_breaches', 0)
        ),
        expected_output=report_task_def["expected_output"],
        agent=reporter_agent,
        output_pydantic=ShiftReportOutput
    )
    
    # Run crew
    crew = Crew(
        agents=[reporter_agent],
        tasks=[report_task],
        verbose=True
    )
    
    try:
        logger.info("Kicking off AI crew for shift report")
        result = crew.kickoff()
        
        output = extract_report_output(result, logger)
        
        if not output.subject or not output.body:
            logger.warning("Invalid output, using fallback")
            output.subject = f"{report_status_emoji} NOC {shift_type.capitalize()} Shift Report | {report_date}"
            output.body = f"Shift report for {shift_start_local} to {shift_end_local}\n\nProcessed {len(alerts)} alerts."
        
        # Send notifications
        send_report_email(output.subject, output.body, output.metadata)
        send_rocketchat_webhook_message(f"**{output.subject}**\n\n{output.body[:500]}...")
        
        logger.info("Shift report sent successfully")
        logger.info(f"Subject: {output.subject}")
        logger.info(f"Body length: {len(output.body)} characters")
        
    except Exception as e:
        logger.error(f"Report generation failed: {e}", exc_info=True)
        raise


def run_weekly_report():
    """Run the weekly report task."""
    now = arrow.now(LOCAL_TZ_NAME)
    # Go back to the last Monday
    start_of_last_week = now.shift(days=-(now.weekday() + 7))
    end_of_last_week = start_of_last_week.shift(days=6)

    shift_start = start_of_last_week.replace(hour=0, minute=0, second=0, microsecond=0).datetime
    shift_end = end_of_last_week.replace(hour=23, minute=59, second=59, microsecond=0).datetime

    run(shift_type="weekly", shift_start=shift_start, shift_end=shift_end)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate NOC shift reports')
    parser.add_argument("--shift", choices=["morning", "evening", "weekly"], 
                       help="Shift type to generate report for")
    parser.add_argument("--test", action="store_true",
                       help="Run timestamp parsing tests")
    args = parser.parse_args()
    
    if args.test:
        # Run tests
        print("Testing timestamp parsing:")
        print("=" * 60)
        
        test_timestamps = [
            "2025-10-21T00:42:01Z",
            "2025-10-17T03:43:15Z",
            "2025-10-14T06:13:28Z"
        ]
        
        for ts in test_timestamps:
            try:
                parsed = parse_ts_utc(ts)
                print(f"✓ {ts}")
                print(f"  UTC:   {parsed.format('YYYY-MM-DD HH:mm:ss ZZ')}")
                print(f"  Local: {to_local_str(parsed)}")
            except Exception as e:
                print(f"✗ {ts} -> Error: {e}")
        
        print("\n" + "=" * 60)
        print("Testing alert filtering:")
        print("=" * 60)
        
        # Test morning shift
        now = arrow.now(LOCAL_TZ_NAME)
        shift_start_local = now.replace(hour=7, minute=0, second=0, microsecond=0)
        shift_end_local = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        print(f"Current time: {now.format('YYYY-MM-DD HH:mm:ss ZZ')}")
        print(f"Morning shift window (Local): {shift_start_local.format('YYYY-MM-DD HH:mm:ss ZZ')} to {shift_end_local.format('YYYY-MM-DD HH:mm:ss ZZ')}")
        print(f"Morning shift window (UTC):   {shift_start_local.to('UTC').format('YYYY-MM-DD HH:mm:ss ZZ')} to {shift_end_local.to('UTC').format('YYYY-MM-DD HH:mm:ss ZZ')}")
        
        # Load and filter alerts
        alerts = load_alerts(shift_start_local.datetime, shift_end_local.datetime)
        
        if alerts:
            print(f"\nFound {len(alerts)} alerts in morning shift window:")
            print("-" * 60)
            for alert in alerts[:5]:  # Show first 5
                try:
                    ts = parse_ts_utc(alert.get('timestamp'))
                    print(f"  Incident {alert.get('incident_number')}: {alert.get('title')[:50]}")
                    print(f"    Time: {to_local_str(ts)} (Status: {alert.get('status')})")
                except:
                    print(f"  Incident {alert.get('incident_number')}: Invalid timestamp")
            if len(alerts) > 5:
                print(f"  ... and {len(alerts) - 5} more")
        else:
            print("\nNo alerts found in morning shift window")
            
        # Test evening shift
        print("\n" + "=" * 60)
        shift_start_local = now.replace(hour=16, minute=0, second=0, microsecond=0)
        shift_end_local = now.replace(hour=23, minute=0, second=0, microsecond=0)
        
        print(f"Evening shift window (Local): {shift_start_local.format('YYYY-MM-DD HH:mm:ss ZZ')} to {shift_end_local.format('YYYY-MM-DD HH:mm:ss ZZ')}")
        print(f"Evening shift window (UTC):   {shift_start_local.to('UTC').format('YYYY-MM-DD HH:mm:ss ZZ')} to {shift_end_local.to('UTC').format('YYYY-MM-DD HH:mm:ss ZZ')}")
        
        alerts = load_alerts(shift_start_local.datetime, shift_end_local.datetime)
        
        if alerts:
            print(f"\nFound {len(alerts)} alerts in evening shift window:")
            print("-" * 60)
            for alert in alerts[:5]:
                try:
                    ts = parse_ts_utc(alert.get('timestamp'))
                    print(f"  Incident {alert.get('incident_number')}: {alert.get('title')[:50]}")
                    print(f"    Time: {to_local_str(ts)} (Status: {alert.get('status')})")
                except:
                    print(f"  Incident {alert.get('incident_number')}: Invalid timestamp")
            if len(alerts) > 5:
                print(f"  ... and {len(alerts) - 5} more")
        else:
            print("\nNo alerts found in evening shift window")
            
        # Show all unique timestamps in the log for debugging
        print("\n" + "=" * 60)
        print("All unique alert timestamps in log (latest 20):")
        print("=" * 60)
        
        all_alerts = _load_log_sync()
        unique_times = {}
        
        for alert in all_alerts:
            ts = alert.get('timestamp')
            inc = alert.get('incident_number')
            if ts:
                try:
                    parsed = parse_ts_utc(ts)
                    time_key = parsed.format('YYYY-MM-DD HH:mm')
                    if time_key not in unique_times:
                        unique_times[time_key] = {
                            'utc': parsed.format('YYYY-MM-DD HH:mm:ss ZZ'),
                            'local': to_local_str(parsed),
                            'incidents': []
                        }
                    unique_times[time_key]['incidents'].append(inc)
                except:
                    pass
        
        sorted_times = sorted(unique_times.items(), reverse=True)[:20]
        for time_key, data in sorted_times:
            print(f"  {data['local']} (UTC: {data['utc']})")
            print(f"    Incidents: {', '.join(map(str, data['incidents'][:5]))}")
        
        print("\n" + "=" * 60)
        print("Test completed!")
        print("=" * 60)
        
    else:
        # Run actual report generation
        if args.shift == "weekly":
            run_weekly_report()
        else:
            run(args.shift)