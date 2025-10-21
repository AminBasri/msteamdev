"""Advanced test cases for KPI calculations covering edge cases and complex scenarios."""

import unittest
import os
import sys
import arrow
from datetime import timezone

# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.msteamdev.daily_report import calculate_shift_kpis

class TestAdvancedKPICalculations(unittest.TestCase):
    def setUp(self):
        self.base_time = arrow.now()
        self.shift_start = self.base_time.shift(hours=-8)
        self.shift_end = self.base_time
    
    def create_test_alert(self, **kwargs):
        """Create a test alert with default values that can be overridden."""
        alert = {
            "incident_number": kwargs.get("incident_number", "1"),
            "title": kwargs.get("title", "Test Alert"),
            "severity": kwargs.get("severity", "critical"),
            "status": kwargs.get("status", "open"),
            "timestamp": kwargs.get("timestamp", self.base_time.isoformat()),
            "escalation_status": kwargs.get("escalation_status", "None"),
            "escalation_reason": kwargs.get("escalation_reason", ""),
            "metadata": {
                "acknowledged_at": None,
                "resolved_at": None,
                "first_response_at": None,
                "sla_breach_at": None
            }
        }
        # Handle metadata fields specially
        metadata_fields = ['acknowledged_at', 'resolved_at', 'first_response_at', 'sla_breach_at']
        metadata_updates = {k: kwargs.pop(k) for k in metadata_fields if k in kwargs}
        alert['metadata'].update(metadata_updates)
        
        # Update remaining fields
        alert.update(kwargs)
        return alert
    
    def test_sla_calculation_scenarios(self):
        """Test various SLA calculation scenarios."""
        alerts = [
            # Alert 1: Within SLA
            self.create_test_alert(
                incident_number="1",
                severity="critical",
                acknowledged_at=self.base_time.shift(minutes=3).isoformat(),
                resolved_at=self.base_time.shift(minutes=25).isoformat()
            ),
            # Alert 2: SLA breached
            self.create_test_alert(
                incident_number="2",
                severity="critical",
                acknowledged_at=self.base_time.shift(minutes=15).isoformat(),
                resolved_at=self.base_time.shift(minutes=120).isoformat(),
                sla_breach_at=self.base_time.shift(minutes=90).isoformat()
            ),
            # Alert 3: Still open, no SLA breach yet
            self.create_test_alert(
                incident_number="3",
                severity="critical",
                acknowledged_at=self.base_time.shift(minutes=5).isoformat()
            )
        ]
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        self.assertEqual(kpis["sla_breaches"], 1)
    
    def test_response_time_edge_cases(self):
        """Test edge cases in response time calculations."""
        def test_timing_scenarios(self):
        """Test various timing calculation scenarios."""
        alerts = [
            # Alert 1: First response before acknowledgement
            self.create_test_alert(
                incident_number="1",
                status="open",
                acknowledged_at=self.base_time.shift(minutes=3).isoformat(),
                first_response_at=self.base_time.shift(minutes=5).isoformat()
            ),
            # Alert 2: Simultaneous response and acknowledgement
            self.create_test_alert(
                incident_number="2",
                status="open",
                acknowledged_at=self.base_time.shift(minutes=4).isoformat(),
                first_response_at=self.base_time.shift(minutes=4).isoformat()
            ),
            # Alert 3: Quick resolution
            self.create_test_alert(
                incident_number="3",
                status="resolved",
                resolved_at=self.base_time.shift(minutes=10).isoformat()
            )
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        self.assertNotEqual(kpis["mean_time_to_first_response"], "N/A")
    
    def test_alert_state_transitions(self):
        """Test alerts with multiple state transitions."""
        alert_time = self.base_time
        alerts = [
            # Alert with multiple updates
            self.create_test_alert(
                incident_number="1",
                timestamp=alert_time.shift(minutes=-60).isoformat(),
                acknowledged_at=alert_time.shift(minutes=-55).isoformat(),
                first_response_at=alert_time.shift(minutes=-50).isoformat(),
                resolved_at=alert_time.shift(minutes=-30).isoformat(),
                status="resolved"
            ),
            # Alert that was reopened
            self.create_test_alert(
                incident_number="2",
                timestamp=alert_time.shift(minutes=-120).isoformat(),
                acknowledged_at=alert_time.shift(minutes=-115).isoformat(),
                resolved_at=alert_time.shift(minutes=-90).isoformat(),
                status="reopened"
            )
        ]
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        self.assertEqual(kpis["resolved_alerts"], 1)  # Only count actually resolved alerts
    
    def test_timezone_handling(self):
        """Test KPI calculations with alerts in different timezones."""
        # Alert timestamps in different timezones
        utc_time = self.base_time
        sg_time = utc_time.to('Asia/Singapore')
        ist_time = utc_time.to('Asia/Kolkata')
        
        alerts = [
            self.create_test_alert(
                incident_number="1",
                timestamp=utc_time.isoformat(),  # UTC
                acknowledged_at=utc_time.shift(minutes=5).isoformat()
            ),
            self.create_test_alert(
                incident_number="2",
                timestamp=sg_time.isoformat(),  # Singapore time
                acknowledged_at=utc_time.shift(minutes=10).isoformat()
            ),
            self.create_test_alert(
                incident_number="3",
                timestamp=ist_time.isoformat(),  # India time
                acknowledged_at=utc_time.shift(minutes=15).isoformat()
            )
        ]
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        self.assertEqual(kpis["total_alerts"], 3)
    
    def test_concurrent_alerts(self):
        """Test handling of concurrent alerts."""
        same_time = self.base_time
        alerts = [
            # Multiple alerts created at the same time
            self.create_test_alert(
                incident_number=1,
                timestamp=same_time.isoformat(),
                severity="critical"
            ),
            self.create_test_alert(
                incident_number=2,
                timestamp=same_time.isoformat(),
                severity="warning"
            ),
            self.create_test_alert(
                incident_number=3,
                timestamp=same_time.isoformat(),
                severity="critical"
            )
        ]
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        self.assertEqual(kpis["total_alerts"], 3)
    
    def test_alert_deduplication(self):
        """Test handling of duplicate alert updates."""
        alerts = [
            # Original alert
            self.create_test_alert(
                incident_number=1,
                timestamp=self.base_time.isoformat(),
                status="open"
            ),
            # Update to same alert
            self.create_test_alert(
                incident_number=1,
                timestamp=(self.base_time + timedelta(minutes=5)).isoformat(),
                status="acknowledged",
                acknowledged_at=(self.base_time + timedelta(minutes=5)).isoformat()
            ),
            # Final update
            self.create_test_alert(
                incident_number=1,
                timestamp=(self.base_time + timedelta(minutes=30)).isoformat(),
                status="resolved",
                resolved_at=(self.base_time + timedelta(minutes=30)).isoformat()
            )
        ]
        
        kpis = calculate_shift_kpis(alerts, self.shift_start, self.shift_end)
        self.assertEqual(kpis["total_alerts"], 1)  # Should count as one alert
        self.assertEqual(kpis["resolved_alerts"], 1)

if __name__ == '__main__':
    unittest.main()