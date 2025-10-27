"""
Daily Metrics Storage System

This module handles storing daily shift metrics to JSON files for weekly report aggregation.
Similar to Otobo's data storage approach, it maintains historical metrics for analysis.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import arrow

# Import logging setup
from src.msteamdev.logging_setup import get_module_logger

logger = get_module_logger(__name__, log_filename='daily_metrics.log')

@dataclass
class DailyMetrics:
    """Daily shift metrics data structure."""
    date: str  # YYYY-MM-DD format
    shift_type: str  # morning, evening
    shift_start: str  # ISO format
    shift_end: str  # ISO format
    
    # Alert counts
    total_alerts: int
    unique_incidents: int
    resolved_alerts: int
    acknowledged_alerts: int
    critical_alerts: int
    warning_alerts: int
    escalated_alerts: int
    
    # Timing metrics (in minutes)
    mtta_minutes: float
    mttr_minutes: float
    mttfr_minutes: float
    
    # Rates (percentages)
    resolution_rate: float
    acknowledgment_rate: float
    escalation_rate: float
    
    # SLA metrics
    sla_compliance: float  # Overall SLA compliance percentage
    sla_breaches: int
    s2_sla_compliance: float
    s3_sla_compliance: float
    
    # Incident details
    incident_details: List[Dict[str, Any]]
    
    # Metadata
    generated_at: str  # ISO format
    data_version: str = "1.0"

class DailyMetricsStorage:
    """Handles storage and retrieval of daily metrics."""
    
    def __init__(self, storage_dir: str = None):
        """Initialize storage with directory path."""
        if storage_dir is None:
            # Default to data directory in project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            storage_dir = os.path.join(project_root, 'data', 'daily_metrics')
        
        self.storage_dir = storage_dir
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self):
        """Ensure storage directory exists."""
        os.makedirs(self.storage_dir, exist_ok=True)
        logger.info(f"Daily metrics storage directory: {self.storage_dir}")
    
    def _get_file_path(self, date: str, shift_type: str) -> str:
        """Get file path for specific date and shift."""
        filename = f"{date}_{shift_type}_metrics.json"
        return os.path.join(self.storage_dir, filename)
    
    def save_daily_metrics(self, metrics: DailyMetrics) -> bool:
        """Save daily metrics to JSON file."""
        try:
            file_path = self._get_file_path(metrics.date, metrics.shift_type)
            
            # Convert to dictionary for JSON serialization
            metrics_dict = asdict(metrics)
            
            with open(file_path, 'w') as f:
                json.dump(metrics_dict, f, indent=2)
            
            logger.info(f"Saved daily metrics to {file_path}")
            logger.info(f"Metrics: {metrics.total_alerts} alerts, {metrics.sla_compliance:.1f}% SLA compliance")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save daily metrics: {e}")
            return False
    
    def load_daily_metrics(self, date: str, shift_type: str) -> Optional[DailyMetrics]:
        """Load daily metrics from JSON file."""
        try:
            file_path = self._get_file_path(date, shift_type)
            
            if not os.path.exists(file_path):
                logger.warning(f"Daily metrics file not found: {file_path}")
                return None
            
            with open(file_path, 'r') as f:
                metrics_dict = json.load(f)
            
            # Convert back to DailyMetrics object
            metrics = DailyMetrics(**metrics_dict)
            logger.info(f"Loaded daily metrics from {file_path}")
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to load daily metrics: {e}")
            return None
    
    def get_weekly_metrics(self, start_date: str, end_date: str) -> List[DailyMetrics]:
        """Get all daily metrics for a week period."""
        metrics_list = []
        
        try:
            # Generate date range
            start_arrow = arrow.get(start_date)
            end_arrow = arrow.get(end_date)
            
            current_arrow = start_arrow
            while current_arrow <= end_arrow:
                current_date = current_arrow.format('YYYY-MM-DD')
                
                # Try to load both morning and evening shifts
                for shift_type in ['morning', 'evening']:
                    metrics = self.load_daily_metrics(current_date, shift_type)
                    if metrics:
                        metrics_list.append(metrics)
                
                current_arrow = current_arrow.shift(days=1)
            
            logger.info(f"Loaded {len(metrics_list)} daily metrics for period {start_date} to {end_date}")
            return metrics_list
            
        except Exception as e:
            logger.error(f"Failed to get weekly metrics: {e}")
            return []
    
    def list_available_dates(self) -> List[str]:
        """List all available dates with metrics."""
        dates = set()
        
        try:
            for filename in os.listdir(self.storage_dir):
                if filename.endswith('_metrics.json'):
                    # Extract date from filename (format: YYYY-MM-DD_shift_metrics.json)
                    date_part = filename.split('_')[0]
                    dates.add(date_part)
            
            sorted_dates = sorted(list(dates))
            logger.info(f"Found metrics for {len(sorted_dates)} dates")
            return sorted_dates
            
        except Exception as e:
            logger.error(f"Failed to list available dates: {e}")
            return []

def create_daily_metrics_from_kpis(
    kpis: Dict[str, Any],
    shift_type: str,
    shift_start: datetime,
    shift_end: datetime,
    incident_details: List[Dict[str, Any]]
) -> DailyMetrics:
    """Create DailyMetrics object from KPI calculation results."""
    
    # Extract date from shift start
    date_str = shift_start.strftime('%Y-%m-%d')
    
    # Convert timing metrics from string format to float
    def parse_timing_metric(metric_str: str) -> float:
        """Parse timing metric string (e.g., '1454.6m') to float minutes."""
        if metric_str == 'N/A':
            return 0.0
        try:
            return float(metric_str.replace('m', ''))
        except:
            return 0.0
    
    # Parse SLA compliance percentages
    def parse_percentage(percentage_str: str) -> float:
        """Parse percentage string (e.g., '57.1%') to float."""
        if percentage_str == 'N/A':
            return 0.0
        try:
            return float(percentage_str.replace('%', ''))
        except:
            return 0.0
    
    return DailyMetrics(
        date=date_str,
        shift_type=shift_type,
        shift_start=shift_start.isoformat(),
        shift_end=shift_end.isoformat(),
        
        # Alert counts
        total_alerts=kpis.get('total_alerts', 0),
        unique_incidents=kpis.get('unique_alerts', 0),
        resolved_alerts=kpis.get('resolved_alerts', 0),
        acknowledged_alerts=kpis.get('acknowledged_alerts', 0),
        critical_alerts=kpis.get('critical_alerts', 0),
        warning_alerts=kpis.get('warning_alerts', 0),
        escalated_alerts=len(kpis.get('escalated_alerts', [])),
        
        # Timing metrics
        mtta_minutes=parse_timing_metric(kpis.get('mean_time_to_acknowledge', '0.0m')),
        mttr_minutes=parse_timing_metric(kpis.get('mean_time_to_resolve', '0.0m')),
        mttfr_minutes=parse_timing_metric(kpis.get('mean_time_to_first_response', '0.0m')),
        
        # Rates
        resolution_rate=parse_percentage(kpis.get('resolution_rate', '0.0%')),
        acknowledgment_rate=parse_percentage(kpis.get('acknowledgment_rate', '0.0%')),
        escalation_rate=parse_percentage(kpis.get('escalation_rate', '0.0%')),
        
        # SLA metrics
        sla_compliance=parse_percentage(kpis.get('sla_compliance_percentage', '0.0%')),
        sla_breaches=kpis.get('sla_breaches', 0),
        s2_sla_compliance=parse_percentage(kpis.get('sla_compliance_by_severity', {}).get('S2', '0.0%')),
        s3_sla_compliance=parse_percentage(kpis.get('sla_compliance_by_severity', {}).get('S3', '0.0%')),
        
        # Incident details
        incident_details=incident_details,
        
        # Metadata
        generated_at=datetime.now(timezone.utc).isoformat()
    )

# Global storage instance
daily_storage = DailyMetricsStorage()
