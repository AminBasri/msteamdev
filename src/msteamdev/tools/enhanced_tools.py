import json
import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta, timezone
from functools import lru_cache, wraps

from crewai.tools import tool
from pydantic import BaseModel, Field

from msteamdev.tools.redis_client import cache_get, cache_set, cache_delete, cache_set_add, cache_set_is_member, cache_set_remove

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
def read_alert_log_enhanced(
    limit: int = 100,
    priority_filter: Optional[str] = None,
    hours_back: Optional[int] = None
) -> str:
    """
    Read alert log with enhanced filtering and caching.
    
    Args:
        limit: Maximum number of alerts to return
        priority_filter: Filter by priority (critical, high, warning, etc.)
        hours_back: Only return alerts from the last N hours
    
    Returns:
        JSON string of filtered alerts
    """
    try:
        # Log tool invocation to incident_pipeline.log
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "tool_invocation",
                "tool": "ReadAlertLogEnhanced",
                "parameters": {
                    "limit": limit,
                    "priority_filter": priority_filter,
                    "hours_back": hours_back
                }
            }
            with open("/home/crewai/msteamdev/log/incident_pipeline.log", "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as log_exc:
            logger.error(f"Failed to write tool invocation to incident log: {log_exc}")

        # Try cache first
        cache_key = f"read_alert_log_enhanced:{limit}:{severity_filter}:{hours_back}"
        cached_result = cache_get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached alert log: {cache_key}")
            return json.dumps(cached_result, indent=2)
        
        from msteamdev.tools.alert_store import load_log_sync
        alerts = load_log_sync()
        
        # Apply time filter if specified
        if hours_back:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            alerts = [
                alert for alert in alerts
                if datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")) >= cutoff_time
            ]
        
        # Apply severity filter if specified
        if priority_filter:
            alerts = [
                alert for alert in alerts
                if alert.get("priority", "").lower() == priority_filter.lower()
            ]
        
        # Apply limit
        alerts = alerts[-limit:] if limit > 0 else alerts
        
        # Cache result for 5 minutes
        cache_set(cache_key, alerts, ex=300)
        
        return json.dumps(alerts, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to read enhanced alert log: {e}")
        return f"Error reading alert log: {str(e)}"



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
        
        from msteamdev.tools.alert_store import load_log_sync
        alerts = load_log_sync()
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent_alerts = [
            alert for alert in alerts
            if datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")) >= cutoff_time
        ]
        
        trends = {
            "time_period_hours": hours,
            "total_alerts": len(recent_alerts),
            "priority_distribution": _get_priority_distribution(recent_alerts),
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

def _get_priority_distribution(alerts: List[Dict]) -> Dict[str, int]:
    """Get distribution of alert priorities."""
    distribution = {}
    for alert in alerts:
        priority = alert.get("priority", "unknown")
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
        cache_set(test_key, "test", ttl_seconds=10)
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

def _get_active_alerts_count_sync() -> int:
    """Get count of active alerts synchronously."""
    try:
        from msteamdev.tools.alert_store import load_log_sync
        alerts = load_log_sync()
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