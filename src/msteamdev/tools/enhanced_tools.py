import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta, timezone
from functools import lru_cache, wraps

from crewai.tools import tool
from pydantic import BaseModel, Field

from msteamdev.models import AlertMatchCriteria, GetMatchingAlertsInput
from msteamdev.tools.redis_client import cache_get, cache_set, cache_delete, cache_set_add, cache_set_is_member, cache_set_remove
from msteamdev.tools.redis_client import redis_client

logger = logging.getLogger(__name__)

class ToolMetrics:
    """Track tool usage and performance."""
    
    def __init__(self):
        self.call_counts = {}
        self.error_counts = {}
        self.execution_times = {}
    
    def record_call(self, tool_name: str, duration: float, success: bool = True):
        if tool_name not in self.call_counts:
            self.call_counts[tool_name] = 0
            self.error_counts[tool_name] = 0
            self.execution_times[tool_name] = []
        
        self.call_counts[tool_name] += 1
        self.execution_times[tool_name].append(duration)
        
        if not success:
            self.error_counts[tool_name] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        stats = {}
        for tool_name in self.call_counts:
            avg_time = sum(self.execution_times[tool_name]) / len(self.execution_times[tool_name])
            stats[tool_name] = {
                "calls": self.call_counts[tool_name],
                "errors": self.error_counts[tool_name],
                "avg_execution_time": avg_time,
                "success_rate": (self.call_counts[tool_name] - self.error_counts[tool_name]) / self.call_counts[tool_name] * 100
            }
        return stats

# Global metrics instance
tool_metrics = ToolMetrics()

def with_tool_metrics(tool_name: str):
    """Decorator to add metrics to tool calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            """Wrapper function with preserved docstring and metrics tracking."""
            start_time = datetime.now()
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                tool_metrics.record_call(tool_name, duration, True)
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                tool_metrics.record_call(tool_name, duration, False)
                logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
                raise
        return wrapper
    return decorator

@tool("ReadAlertLogEnhanced")
@with_tool_metrics("ReadAlertLogEnhanced")
async def read_alert_log_enhanced(
    limit: int = 100,
    severity_filter: Optional[str] = None,
    time_window_hours: Optional[int] = None
) -> str:
    """
    Read alert log with enhanced filtering and caching.
    
    Args:
        limit: Maximum number of alerts to return
        severity_filter: Filter by severity (critical, high, warning, etc.)
        time_window_hours: Only return alerts from the last N hours
    
    Returns:
        JSON string of filtered alerts
    """
    try:
        # Try cache first
        cache_key = f"read_alert_log_enhanced:{limit}:{severity_filter}:{time_window_hours}"
        cached_result = await cache_get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached alert log: {cache_key}")
            return json.dumps(cached_result, indent=2)
        
        from msteamdev.tools.alert_store import _load_log
        alerts = await _load_log()
        
        # Apply time filter if specified
        if time_window_hours:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=time_window_hours)
            alerts = [
                alert for alert in alerts
                if datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")) >= cutoff_time
            ]
        
        # Apply severity filter if specified
        if severity_filter:
            alerts = [
                alert for alert in alerts
                if alert.get("severity", "").lower() == severity_filter.lower()
            ]
        
        # Apply limit
        alerts = alerts[-limit:] if limit > 0 else alerts
        
        # Cache result for 5 minutes
        await cache_set(cache_key, alerts, ex=300)
        
        return json.dumps(alerts, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to read enhanced alert log: {e}")
        return f"Error reading alert log: {str(e)}"

@tool("GetMatchingAlertsEnhanced")
@with_tool_metrics("GetMatchingAlertsEnhanced")
def get_matching_alerts_enhanced(criteria_input: Union[str, GetMatchingAlertsInput]) -> str:
    """
    Find alerts matching specific criteria with enhanced pattern matching.
    
    Args:
        criteria_input: Matching criteria (title, severity, metric, status)
    
    Returns:
        JSON string of matching alerts with analysis
    """
    try:
        if isinstance(criteria_input, str):
            try:
                # If the input is a string, try to parse it as JSON
                parsed_input = json.loads(criteria_input)
                # The actual criteria might be nested, adjust as necessary based on observed AI behavior
                if "criteria_input" in parsed_input:
                    criteria_input = GetMatchingAlertsInput(**parsed_input["criteria_input"])
                else:
                    criteria_input = GetMatchingAlertsInput(**parsed_input)
            except (json.JSONDecodeError, TypeError) as e:
                # Fallback for malformed JSON or direct non-JSON string
                # This part may need adjustment based on how the AI formats the string
                # For now, we'll assume it's a simple string representing a title or metric
                criteria_input = GetMatchingAlertsInput(alert=AlertMatchCriteria(title=criteria_input))

        criteria = criteria_input.alert
        
        # Create cache key based on criteria
        cache_key = f"matching_alerts:{hash(str(criteria.dict()))}"
        cached_result = cache_get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached matching alerts: {cache_key}")
            return json.dumps(cached_result, indent=2)
        
        from msteamdev.tools.alert_store import _load_log
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            alerts = loop.run_until_complete(_load_log())
        except RuntimeError:
            # Create new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            alerts = loop.run_until_complete(_load_log())
        
        matching_alerts = []
        for alert in alerts:
            match = True
            
            # Check each criteria field
            if criteria.title and criteria.title.lower() not in alert.get("title", "").lower():
                match = False
            if criteria.severity and criteria.severity.lower() != alert.get("severity", "").lower():
                match = False
            if criteria.metric and criteria.metric.lower() != alert.get("metric", "").lower():
                match = False
            if criteria.status and criteria.status.lower() != alert.get("status", "").lower():
                match = False
            
            if match:
                matching_alerts.append(alert)
        
        # Enhanced analysis
        analysis = {
            "total_matches": len(matching_alerts),
            "alerts": matching_alerts[-50:],  # Last 50 matches
            "patterns": _analyze_alert_patterns(matching_alerts),
            "time_distribution": _analyze_time_distribution(matching_alerts),
            "criteria_used": criteria.dict()
        }
        
        # Cache for 10 minutes
        cache_set(cache_key, analysis, ttl_seconds=600)
        
        return json.dumps(analysis, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to get matching alerts: {e}")
        return f"Error getting matching alerts: {str(e)}"

@tool("CheckEscalationEligibility")
@with_tool_metrics("CheckEscalationEligibility") 
def check_escalation_eligibility_enhanced(
    incident_number: str,
    severity: str,
    title: str,
    timestamp: str,
    status: str
) -> str:
    """
    Enhanced escalation eligibility check with detailed analysis.
    
    Args:
        incident_number: Incident number to check
        severity: Alert severity
        title: Alert title
        timestamp: Alert timestamp
    
    Returns:
        JSON string with eligibility decision and detailed reasoning
    """
    try:
        if isinstance(incident_number, str) and incident_number.startswith('{'):
            data = json.loads(incident_number)
            incident_number = data.get('incident_number')
            severity = data.get('severity')
            title = data.get('title')
            timestamp = data.get('timestamp')
            status = data.get('status')

        from msteamdev.tools.alert_store import check_escalation_eligibility
        
        # Create alert dict for existing function
        alert = {
            "incident_number": incident_number,
            "severity": severity,
            "title": title,
            "timestamp": timestamp,
            "status": status
        }
        
        # Handle async function call
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            eligible, reason = loop.run_until_complete(check_escalation_eligibility(alert))
        except RuntimeError:
            # Create new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            eligible, reason = loop.run_until_complete(check_escalation_eligibility(alert))
        
        # Enhanced analysis
        analysis = {
            "eligible": eligible,
            "reason": reason,
            "incident_number": incident_number,
            "severity": severity,
            "detailed_analysis": _get_detailed_escalation_analysis(alert),
            "similar_alerts_count": _count_similar_alerts(alert),
            "business_hours": _is_business_hours(timestamp),
            "escalation_history": _get_escalation_history(title, severity)
        }
        
        return json.dumps(analysis, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to check escalation eligibility: {e}")
        return f"Error checking escalation eligibility: {str(e)}"

@tool("GetAlertTrends")
@with_tool_metrics("GetAlertTrends")
def get_alert_trends(hours: int = 24) -> str:
    """
    Analyze alert trends over specified time period.
    
    Args:
        hours: Number of hours to analyze (default: 24)
    
    Returns:
        JSON string with trend analysis
    """
    try:
        cache_key = f"alert_trends:{hours}"
        cached_result = cache_get(cache_key)
        if cached_result is not None:
            return json.dumps(cached_result, indent=2)
        
        from msteamdev.tools.alert_store import _load_log
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            alerts = loop.run_until_complete(_load_log())
        except RuntimeError:
            # Create new event loop if none exists
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            alerts = loop.run_until_complete(_load_log())
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_alerts = [
            alert for alert in alerts
            if datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")) >= cutoff_time
        ]
        
        trends = {
            "time_period_hours": hours,
            "total_alerts": len(recent_alerts),
            "severity_distribution": _get_severity_distribution(recent_alerts),
            "hourly_distribution": _get_hourly_distribution(recent_alerts),
            "top_metrics": _get_top_metrics(recent_alerts),
            "escalation_rate": _calculate_escalation_rate(recent_alerts),
            "resolution_rate": _calculate_resolution_rate(recent_alerts),
            "alert_velocity": len(recent_alerts) / max(hours, 1)
        }
        
        # Cache for 15 minutes
        cache_set(cache_key, trends, ttl_seconds=900)
        
        return json.dumps(trends, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to get alert trends: {e}")
        return f"Error getting alert trends: {str(e)}"

@tool("GetSystemHealth")
@with_tool_metrics("GetSystemHealth")
def get_system_health() -> str:
    """
    Get current system health metrics.
    
    Returns:
        JSON string with system health information
    """
    try:
        health = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "redis_status": _check_redis_health(),
            "mcp_server_status": _check_mcp_health(),
            "tool_metrics": tool_metrics.get_stats(),
            "active_alerts_count": _get_active_alerts_count_sync(),
            "processing_queue_size": _get_processing_queue_size(),
            "system_uptime": _get_system_uptime()
        }
        
        return json.dumps(health, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to get system health: {e}")
        return f"Error getting system health: {str(e)}"

# Helper functions
def _analyze_alert_patterns(alerts: List[Dict]) -> Dict[str, Any]:
    """Analyze patterns in alert list."""
    if not alerts:
        return {}
    
    severities = [alert.get("severity", "unknown") for alert in alerts]
    metrics = [alert.get("metric", "unknown") for alert in alerts]
    
    return {
        "most_common_severity": max(set(severities), key=severities.count) if severities else None,
        "most_common_metric": max(set(metrics), key=metrics.count) if metrics else None,
        "unique_severities": len(set(severities)),
        "unique_metrics": len(set(metrics)),
        "frequency_by_hour": _get_hourly_frequency(alerts)
    }

def _analyze_time_distribution(alerts: List[Dict]) -> Dict[str, Any]:
    """Analyze time distribution of alerts."""
    if not alerts:
        return {}
    
    timestamps = []
    for alert in alerts:
        try:
            ts = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
            timestamps.append(ts)
        except:
            continue
    
    if not timestamps:
        return {}
    
    timestamps.sort()
    
    return {
        "earliest": timestamps[0].isoformat(),
        "latest": timestamps[-1].isoformat(),
        "span_hours": (timestamps[-1] - timestamps[0]).total_seconds() / 3600,
        "alerts_per_hour": len(alerts) / max((timestamps[-1] - timestamps[0]).total_seconds() / 3600, 1)
    }

def _get_detailed_escalation_analysis(alert: Dict) -> Dict[str, Any]:
    """Get detailed escalation analysis."""
    return {
        "severity_priority": _get_severity_priority(alert.get("severity", "")),
        "time_of_day_factor": _get_time_factor(alert.get("timestamp", "")),
        "similar_recent_count": _count_recent_similar(alert),
        "escalation_recommendation": _get_escalation_recommendation(alert)
    }

def _count_similar_alerts(alert: Dict) -> int:
    """Count similar alerts in recent history."""
    try:
        from msteamdev.tools.alert_store import _load_log
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            alerts = loop.run_until_complete(_load_log())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            alerts = loop.run_until_complete(_load_log())
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
        similar_count = 0
        
        for a in alerts:
            try:
                if datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00")) >= cutoff:
                    if (a.get("severity") == alert.get("severity") and 
                        a.get("metric") == alert.get("metric")):
                        similar_count += 1
            except:
                continue
        
        return similar_count
    except:
        return 0

def _is_business_hours(timestamp: str) -> bool:
    """Check if timestamp falls in business hours (9 AM - 6 PM Singapore time)."""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        singapore_time = dt.astimezone(timezone(timedelta(hours=8)))
        return 9 <= singapore_time.hour < 18
    except:
        return False

def _get_escalation_history(title: str, severity: str) -> List[Dict]:
    """Get escalation history for similar alerts."""
    # This would query escalation logs - simplified for now
    return []

def _get_severity_distribution(alerts: List[Dict]) -> Dict[str, int]:
    """Get distribution of alert severities."""
    distribution = {}
    for alert in alerts:
        severity = alert.get("severity", "unknown")
        distribution[severity] = distribution.get(severity, 0) + 1
    return distribution

def _get_hourly_distribution(alerts: List[Dict]) -> Dict[str, int]:
    """Get hourly distribution of alerts."""
    distribution = {}
    for alert in alerts:
        try:
            dt = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
            hour = dt.hour
            distribution[str(hour)] = distribution.get(str(hour), 0) + 1
        except:
            continue
    return distribution

def _get_top_metrics(alerts: List[Dict]) -> List[Dict]:
    """Get top alert metrics."""
    metrics = {}
    for alert in alerts:
        metric = alert.get("metric", "unknown")
        metrics[metric] = metrics.get(metric, 0) + 1
    
    return [
        {"metric": metric, "count": count}
        for metric, count in sorted(metrics.items(), key=lambda x: x[1], reverse=True)[:10]
    ]

def _calculate_escalation_rate(alerts: List[Dict]) -> float:
    """Calculate escalation rate."""
    if not alerts:
        return 0.0
    
    escalated = sum(1 for alert in alerts if alert.get("escalated", False))
    return escalated / len(alerts) * 100

def _calculate_resolution_rate(alerts: List[Dict]) -> float:
    """Calculate resolution rate."""
    if not alerts:
        return 0.0
    
    resolved = sum(1 for alert in alerts if alert.get("status", "").lower() == "resolved")
    return resolved / len(alerts) * 100

def _check_redis_health() -> Dict[str, Any]:
    """Check Redis health."""
    try:
        # Simple ping test
        test_key = "health_check_test"
        cache_set(test_key, "test", ttl=10)
        result = cache_get(test_key)
        cache_delete(test_key)
        
        return {
            "status": "healthy" if result == "test" else "degraded",
            "last_check": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "last_check": datetime.now(timezone.utc).isoformat()
        }

def _check_mcp_health() -> Dict[str, Any]:
    """Check MCP server health."""
    # This would check MCP server - simplified for now
    return {
        "status": "unknown",
        "last_check": datetime.now(timezone.utc).isoformat()
    }

def _get_active_alerts_count() -> int:
    """Get count of active alerts."""
    try:
        from msteamdev.tools.alert_store import _load_log
        alerts = _load_log()
        return sum(1 for alert in alerts if alert.get("status", "").lower() in ["triggered", "acknowledged"])
    except:
        return 0

def _get_active_alerts_count_sync() -> int:
    """Get count of active alerts synchronously."""
    try:
        from msteamdev.tools.alert_store import _load_log
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            alerts = loop.run_until_complete(_load_log())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            alerts = loop.run_until_complete(_load_log())
        return sum(1 for alert in alerts if alert.get("status", "").lower() in ["triggered", "acknowledged"])
    except Exception as e:
        logger.debug(f"Failed to get active alerts count: {e}")
        return 0

def _get_processing_queue_size() -> int:
    """Get processing queue size."""
    # This would check actual queue size - simplified for now
    return 0

def _get_system_uptime() -> str:
    """Get system uptime."""
    # This would calculate actual uptime - simplified for now
    return "unknown"

# Additional helper functions
def _get_hourly_frequency(alerts: List[Dict]) -> Dict[str, int]:
    """Get hourly frequency of alerts."""
    frequency = {}
    for alert in alerts:
        try:
            dt = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
            hour_key = f"{dt.hour:02d}:00"
            frequency[hour_key] = frequency.get(hour_key, 0) + 1
        except:
            continue
    return frequency

def _get_severity_priority(severity: str) -> int:
    """Get numeric priority for severity."""
    priorities = {
        "critical": 5,
        "high": 4,
        "medium": 3,
        "warning": 2,
        "low": 1,
        "info": 1
    }
    return priorities.get(severity.lower(), 1)

def _get_time_factor(timestamp: str) -> str:
    """Get time factor (business hours, after hours, weekend)."""
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        singapore_time = dt.astimezone(timezone(timedelta(hours=8)))
        
        if singapore_time.weekday() >= 5:  # Weekend
            return "weekend"
        elif 9 <= singapore_time.hour < 18:  # Business hours
            return "business_hours"
        else:
            return "after_hours"
    except:
        return "unknown"

def _count_recent_similar(alert: Dict) -> int:
    """Count recent similar alerts."""
    try:
        from msteamdev.tools.alert_store import _load_log
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            alerts = loop.run_until_complete(_load_log())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            alerts = loop.run_until_complete(_load_log())
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        count = 0
        
        for a in alerts:
            try:
                if datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00")) >= cutoff:
                    if (a.get("title", "").lower() in alert.get("title", "").lower() or
                        alert.get("title", "").lower() in a.get("title", "").lower()):
                        count += 1
            except:
                continue
        
        return count
    except Exception as e:
        logger.debug(f"Failed to count recent similar alerts: {e}")
        return 0

def _get_escalation_recommendation(alert: Dict) -> str:
    """Get escalation recommendation based on analysis."""
    severity = alert.get("severity", "").lower()
    
    if severity in ["critical", "high"]:
        return "recommend_escalate"
    elif severity == "medium":
        return "conditional_escalate"
    else:
        return "monitor_only"