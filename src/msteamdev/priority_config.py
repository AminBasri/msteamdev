"""
Priority-based KPI configuration for PagerDuty alert management.

This module defines alert priority levels (P1-P4) and their corresponding KPI thresholds
for managing alerts in a proactive monitoring environment.
"""

import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class KPIThreshold:
    """KPI threshold configuration for a priority level."""
    acknowledgment_minutes: int
    resolution_hours: int
    
    def get_acknowledgment_minutes(self) -> int:
        """Get acknowledgment threshold in minutes."""
        return self.acknowledgment_minutes
    
    def get_resolution_hours(self) -> int:
        """Get resolution threshold in hours."""
        return self.resolution_hours


class PriorityConfig:
    """Configuration for priority-based KPI management."""
    
    # Priority mapping for PagerDuty alert priorities
    PRIORITY_MAPPING = {
        "critical": "P1",  # Critical alerts → P1 (Highest)
        "warning": "P2",   # Warning alerts → P2 (High)
        "info": "P3",      # Info alerts → P3 (Medium)
        "low": "P4"        # Low alerts → P4 (Low)
    }
    
    # KPI thresholds by alert priority level (aligned with KPI framework)
    KPI_THRESHOLDS = {
        "P1": KPIThreshold(acknowledgment_minutes=5, resolution_hours=4),     # Critical - Major outage
        "P2": KPIThreshold(acknowledgment_minutes=10, resolution_hours=8),    # High - Service degradation
        "P3": KPIThreshold(acknowledgment_minutes=15, resolution_hours=24),   # Medium - Limited impact
        "P4": KPIThreshold(acknowledgment_minutes=20, resolution_hours=72)    # Low - Minor issues
    }
    
    @classmethod
    def get_all_priority_levels(cls) -> List[str]:
        """Get list of all priority levels in order."""
        return ["P1", "P2", "P3", "P4"]
    
    @classmethod
    def map_alert_priority(cls, alert: Dict[str, Any]) -> str:
        """
        Map PagerDuty alert priority to internal alert priority level.
        
        Args:
            alert: Alert dictionary with priority information
            
        Returns:
            Alert priority level (P1, P2, P3, P4)
        """
        # First try explicit priority
        priority = alert.get("priority", "").lower().strip()
        if priority and priority != "unknown":
            return cls.PRIORITY_MAPPING.get(priority, "P3")
            
        # If priority is unknown/empty, check the title for severity indicators
        title = alert.get("title", "").upper()
        if "[CRITICAL]" in title:
            return "P1"
        elif "[WARNING]" in title:
            return "P2"
            
        return "P3"  # Default to P3 for unknown
    
    @classmethod
    def get_kpi_threshold(cls, priority_level: str) -> KPIThreshold:
        """
        Get KPI threshold for a priority level.
        
        Args:
            priority_level: Alert priority (P1, P2, P3, P4)
            
        Returns:
            KPIThreshold object with first response and resolution times
        """
        return cls.KPI_THRESHOLDS.get(priority_level, cls.KPI_THRESHOLDS["P3"])
    
    @classmethod
    def get_acknowledgment_threshold(cls, priority_level: str) -> int:
        """
        Get acknowledgment threshold in minutes for a priority level.
        
        Args:
            priority_level: Alert priority (P1, P2, P3, P4)
            
        Returns:
            Acknowledgment threshold in minutes
        """
        threshold = cls.get_kpi_threshold(priority_level)
        return threshold.get_acknowledgment_minutes()
    
    @classmethod
    def get_resolution_threshold(cls, priority_level: str) -> int:
        """
        Get resolution threshold in hours for a priority level.
        
        Args:
            priority_level: Alert priority (P1, P2, P3, P4)
            
        Returns:
            Resolution threshold in hours
        """
        threshold = cls.get_kpi_threshold(priority_level)
        return threshold.get_resolution_hours()
    
    @classmethod
    def get_priority_description(cls, priority_level: str) -> str:
        """
        Get human-readable description for priority level.
        
        Args:
            priority_level: Alert priority (P1, P2, P3, P4)
            
        Returns:
            Human-readable description
        """
        descriptions = {
            "P1": "Critical Alert Priority",
            "P2": "High Alert Priority",
            "P3": "Medium Alert Priority",
            "P4": "Low Alert Priority"
        }
        return descriptions.get(priority_level, "Unknown")
    
    @classmethod
    def get_all_priority_levels(cls) -> list:
        """Get all configured priority levels."""
        return list(cls.KPI_THRESHOLDS.keys())
    
    @classmethod
    def get_priority_stats(cls, alerts: list) -> Dict[str, int]:
        """
        Get priority distribution statistics for a list of alerts.
        
        Args:
            alerts: List of alert dictionaries
            
        Returns:
            Dictionary with priority level counts
        """
        stats = {}
        for priority_level in cls.get_all_priority_levels():
            stats[priority_level] = 0
        
        for alert in alerts:
            priority_level = cls.map_alert_priority(alert)
            stats[priority_level] = stats.get(priority_level, 0) + 1
        
        return stats
