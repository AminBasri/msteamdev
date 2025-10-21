import unittest
import os
import sys
import arrow
from datetime import timezone

# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.msteamdev.daily_report import calculate_shift_kpis

class TestKPICalculations(unittest.TestCase):
    def setUp(self):
        self.base_time = arrow.now()
        self.shift_start = self.base_time.shift(hours=-8)
        self.shift_end = self.base_time
        
    def create_test_alert(self, **kwargs):
        """Create a test alert with default values that can be overridden."""
        # Base alert with mandatory fields
        alert = {
            "incident_number": kwargs.get("incident_number", "1"),
            "title": kwargs.get("title", "Test Alert"),
            "severity": kwargs.get("severity", "critical"),
            "status": kwargs.get("status", "triggered"),
            "timestamp": kwargs.get("timestamp", self.base_time.isoformat()),
            "escalation_status": kwargs.get("escalation_status", "None"),
            "escalation_reason": kwargs.get("escalation_reason", "")
        }
        
        # Update remaining fields
        alert.update(kwargs)
        return alert

    def test_timing_metrics(self):
        """Test KPI calculations for timing metrics."""
        # Create sequence of state changes for an incident
        base = self.base_time
        alerts = [
            # Initial alert
            self.create_test_alert(
                incident_number="1",
                status="triggered",
                timestamp=base.isoformat()
            ),
            # Acknowledged
            self.create_test_alert(
                incident_number="1",
                status="acknowledged",
                timestamp=base.shift(minutes=5).isoformat()
            ),
            # Resolved
            self.create_test_alert(
                incident_number="1",
                status="resolved",
                timestamp=base.shift(minutes=30).isoformat()
            )
        ]
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        
        self.assertEqual(kpis['mean_time_to_acknowledge'], '5.0')  # 5 minutes to acknowledge
        self.assertEqual(kpis['mean_time_to_resolve'], '30.0')  # 30 minutes to resolve

    def test_calculate_shift_kpis(self):
        """Test comprehensive KPI calculations for a shift."""
        base = self.base_time
        alerts = [
            # Incident 1: Goes through full lifecycle
            self.create_test_alert(
                incident_number="1",
                status="triggered",
                severity="critical",
                timestamp=base.isoformat()
            ),
            self.create_test_alert(
                incident_number="1",
                status="acknowledged",
                severity="critical",
                timestamp=base.shift(minutes=5).isoformat()
            ),
            self.create_test_alert(
                incident_number="1",
                status="resolved",
                severity="critical",
                timestamp=base.shift(minutes=30).isoformat()
            ),
            # Incident 2: Escalated warning
            self.create_test_alert(
                incident_number="2",
                status="triggered",
                severity="warning",
                timestamp=base.shift(minutes=8).isoformat()
            ),
            self.create_test_alert(
                incident_number="2",
                status="acknowledged",
                severity="warning",
                escalation_status="escalated",
                timestamp=base.shift(minutes=10).isoformat()
            ),
            # Incident 3: Critical with no acknowledgment
            self.create_test_alert(
                incident_number="3",
                status="triggered",
                severity="critical",
                timestamp=base.shift(minutes=40).isoformat()
            )
        ]
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        
        # Test alert counts
        self.assertEqual(kpis['total_alerts'], 3)
        self.assertEqual(kpis['unique_alerts'], 3)
        self.assertEqual(kpis['resolved_alerts'], 1)
        self.assertEqual(kpis['critical_alerts'], 2)
        self.assertEqual(kpis['warning_alerts'], 1)
        self.assertEqual(kpis['escalated_alerts'], 1)
        
        # Test rates
        self.assertEqual(kpis['resolution_rate'], '33.3%')
        self.assertEqual(kpis['escalation_rate'], '33.3%')
        
        # Test SLA metrics
        self.assertEqual(kpis['sla_breaches'], 1)
        self.assertEqual(kpis['sla_compliance'], '66.7%')
        
    def test_invalid_alert_data(self):
        """Test KPI calculations with invalid alert data."""
        # Alert with missing metadata
        invalid_alert = {
            "incident_number": "1",
            "title": "Invalid Alert",
            "severity": "critical",
            "status": "open",
            "timestamp": self.base_time.isoformat()
        }
        
        # Should not raise exception
        kpis = calculate_shift_kpis([invalid_alert], self.shift_start, self.shift_end)
        
        # Should have default values
        self.assertEqual(kpis['mean_time_to_acknowledge'], 'N/A')
        self.assertEqual(kpis['mean_time_to_resolve'], 'N/A')
        self.assertEqual(kpis['mean_time_to_first_response'], 'N/A')
    def test_edge_cases(self):
        """Test KPI calculations with edge cases."""
        # Test with empty alert list
        empty_kpis = calculate_shift_kpis([], self.shift_start, self.shift_end)
        self.assertEqual(empty_kpis["total_alerts"], 0)
        self.assertEqual(empty_kpis["resolution_rate"], "0.0%")
        self.assertEqual(empty_kpis["mean_time_to_acknowledge"], "N/A")
    
        # Test with invalid timestamp
        invalid_alert = self.create_test_alert(
            timestamp="invalid_date"
        )
        kpis = calculate_shift_kpis([invalid_alert], self.shift_start, self.shift_end)
        self.assertEqual(kpis["mean_time_to_acknowledge"], "N/A")
        self.assertEqual(kpis["mean_time_to_resolve"], "N/A")
        self.assertEqual(kpis["mean_time_to_first_response"], "N/A")

if __name__ == '__main__':
    unittest.main()