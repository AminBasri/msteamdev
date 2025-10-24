"""
Severity-based SLA configuration for PagerDuty alert management.

This module defines severity mapping and SLA thresholds for alert management,
where alerts are early warning signals, not confirmed outages.
"""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SLAThreshold:
    """SLA threshold configuration for a severity level."""
    first_response_minutes: int
    resolution_hours: int
    
    def get_first_response_minutes(self) -> int:
        """Get first response threshold in minutes."""
        return self.first_response_minutes
    
    def get_resolution_hours(self) -> int:
        """Get resolution threshold in hours."""
        return self.resolution_hours


class SeverityConfig:
    """Configuration for severity-based SLA management."""
    
    # Severity mapping: PagerDuty alert severity → ITIL severity
    SEVERITY_MAPPING = {
        "critical": "S2",  # Critical alerts → S2 (High) - not outage yet
        "warning": "S3",    # Warning alerts → S3 (Medium) - start conservative
        "info": "S3",      # Info alerts → S3 (Medium)
        "low": "S3"        # Low alerts → S3 (Medium)
    }
    
    # SLA thresholds by severity level
    SLA_THRESHOLDS = {
        "S1": SLAThreshold(first_response_minutes=15, resolution_hours=4),    # Outage (not used for alerts)
        "S2": SLAThreshold(first_response_minutes=30, resolution_hours=8),    # Critical alerts
        "S3": SLAThreshold(first_response_minutes=60, resolution_hours=24),   # Warning alerts
        "S4": SLAThreshold(first_response_minutes=240, resolution_hours=72)    # Low priority (future use)
    }
    
    @classmethod
    def map_alert_severity(cls, alert: Dict[str, Any]) -> str:
        """
        Map PagerDuty alert severity to ITIL severity level.
        
        Args:
            alert: Alert dictionary with severity information
            
        Returns:
            ITIL severity level (S1, S2, S3, S4)
        """
        severity = alert.get("severity", "").lower().strip()
        return cls.SEVERITY_MAPPING.get(severity, "S3")  # Default to S3 for unknown
    
    @classmethod
    def get_sla_threshold(cls, severity_level: str) -> SLAThreshold:
        """
        Get SLA threshold for a severity level.
        
        Args:
            severity_level: ITIL severity (S1, S2, S3, S4)
            
        Returns:
            SLAThreshold object with first response and resolution times
        """
        return cls.SLA_THRESHOLDS.get(severity_level, cls.SLA_THRESHOLDS["S3"])
    
    @classmethod
    def get_first_response_threshold(cls, severity_level: str) -> int:
        """
        Get first response threshold in minutes for a severity level.
        
        Args:
            severity_level: ITIL severity (S1, S2, S3, S4)
            
        Returns:
            First response threshold in minutes
        """
        threshold = cls.get_sla_threshold(severity_level)
        return threshold.get_first_response_minutes()
    
    @classmethod
    def get_resolution_threshold(cls, severity_level: str) -> int:
        """
        Get resolution threshold in hours for a severity level.
        
        Args:
            severity_level: ITIL severity (S1, S2, S3, S4)
            
        Returns:
            Resolution threshold in hours
        """
        threshold = cls.get_sla_threshold(severity_level)
        return threshold.get_resolution_hours()
    
    @classmethod
    def get_severity_description(cls, severity_level: str) -> str:
        """
        Get human-readable description for severity level.
        
        Args:
            severity_level: ITIL severity (S1, S2, S3, S4)
            
        Returns:
            Human-readable description
        """
        descriptions = {
            "S1": "Critical (Outage)",
            "S2": "High (Critical Alerts)",
            "S3": "Medium (Warning Alerts)",
            "S4": "Low (Info Alerts)"
        }
        return descriptions.get(severity_level, "Unknown")
    
    @classmethod
    def get_all_severity_levels(cls) -> list:
        """Get all configured severity levels."""
        return list(cls.SLA_THRESHOLDS.keys())
    
    @classmethod
    def get_severity_stats(cls, alerts: list) -> Dict[str, int]:
        """
        Get severity distribution statistics for a list of alerts.
        
        Args:
            alerts: List of alert dictionaries
            
        Returns:
            Dictionary with severity level counts
        """
        stats = {}
        for severity_level in cls.get_all_severity_levels():
            stats[severity_level] = 0
        
        for alert in alerts:
            severity_level = cls.map_alert_severity(alert)
            stats[severity_level] = stats.get(severity_level, 0) + 1
        
        return stats
