"""Report metrics collection and monitoring.

This module tracks report generation health metrics and provides monitoring capabilities
to detect quality degradation or persistent failures.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ReportGenerationMetric(BaseModel):
    """Individual report generation metric."""
    timestamp: str
    shift_type: str
    generation_time_ms: float
    structured_output_success: bool
    fallback_used: bool
    extraction_method: str
    alert_count: int
    error_count: int
    completeness_score: float
    data_freshness: str
    known_gaps: List[str]

class ReportMetricsCollector:
    """Collects and analyzes report generation metrics."""
    
    def __init__(self, metrics_file: str = None):
        """Initialize the metrics collector.
        
        Args:
            metrics_file: Path to store metrics. Defaults to 'report_metrics.ndjson' in log directory.
        """
        self.metrics_file = metrics_file or os.path.join(
            os.path.dirname(__file__), "..", "log", "report_metrics.ndjson"
        )
        self._ensure_metrics_file()
        
        # In-memory recent metrics cache
        self._recent_metrics: List[ReportGenerationMetric] = []
        self._max_recent = 100  # Keep last 100 metrics in memory
    
    def _ensure_metrics_file(self) -> None:
        """Ensure metrics file and directory exist."""
        os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
        if not os.path.exists(self.metrics_file):
            with open(self.metrics_file, 'w') as f:
                pass
    
    def record_metric(self, metric: ReportGenerationMetric) -> None:
        """Record a new report generation metric.
        
        Args:
            metric: The metric to record.
        """
        try:
            # Write to file
            with open(self.metrics_file, 'a') as f:
                f.write(metric.json() + '\n')
            
            # Update in-memory cache
            self._recent_metrics.append(metric)
            if len(self._recent_metrics) > self._max_recent:
                self._recent_metrics.pop(0)
                
            # Log warning if quality is degrading
            if self.should_alert_on_quality():
                logger.warning(
                    "Report quality degradation detected: "
                    f"Last {self._max_recent} reports show high fallback usage "
                    f"or low completeness scores"
                )
        except Exception as e:
            logger.error(f"Failed to record metric: {e}")
    
    def get_recent_stats(self) -> Dict[str, Any]:
        """Calculate statistics from recent metrics.
        
        Returns:
            Dictionary containing:
            - average_generation_time_ms
            - fallback_rate
            - structured_output_success_rate
            - average_completeness
            - error_rate
        """
        if not self._recent_metrics:
            return {
                "average_generation_time_ms": 0,
                "fallback_rate": 0,
                "structured_output_success_rate": 0,
                "average_completeness": 0,
                "error_rate": 0
            }
        
        total = len(self._recent_metrics)
        return {
            "average_generation_time_ms": sum(m.generation_time_ms for m in self._recent_metrics) / total,
            "fallback_rate": sum(1 for m in self._recent_metrics if m.fallback_used) / total,
            "structured_output_success_rate": sum(1 for m in self._recent_metrics if m.structured_output_success) / total,
            "average_completeness": sum(m.completeness_score for m in self._recent_metrics) / total,
            "error_rate": sum(m.error_count > 0 for m in self._recent_metrics) / total
        }
    
    def should_alert_on_quality(self) -> bool:
        """Check if report quality is degrading.
        
        Returns:
            True if quality metrics indicate problems, False otherwise.
        """
        stats = self.get_recent_stats()
        return any([
            stats["fallback_rate"] > 0.3,  # More than 30% using fallback
            stats["structured_output_success_rate"] < 0.7,  # Less than 70% structured
            stats["average_completeness"] < 0.8,  # Below 80% complete
            stats["error_rate"] > 0.2  # More than 20% with errors
        ])
    
    def get_quality_summary(self) -> str:
        """Generate a human-readable quality summary.
        
        Returns:
            Formatted string with recent quality metrics.
        """
        stats = self.get_recent_stats()
        return f"""Report Generation Quality Summary
================================
Based on last {len(self._recent_metrics)} reports:

Performance:
- Average generation time: {stats['average_generation_time_ms']:.1f}ms
- Error rate: {stats['error_rate']*100:.1f}%

Output Quality:
- Structured output success: {stats['structured_output_success_rate']*100:.1f}%
- Fallback usage rate: {stats['fallback_rate']*100:.1f}%
- Average completeness: {stats['average_completeness']*100:.1f}%

Status: {'⚠️ DEGRADED' if self.should_alert_on_quality() else '✅ HEALTHY'}
"""

# Global metrics collector instance
REPORT_METRICS = ReportMetricsCollector()