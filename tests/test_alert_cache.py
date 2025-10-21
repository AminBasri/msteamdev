import unittest
import os
import sys
import json
import tempfile
import arrow

# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from src.msteamdev.tools.alert_cache import AlertCache

class TestAlertCache(unittest.TestCase):
    def setUp(self):
        # Create a temporary log file for testing
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "test_alert_log.json")
        base_time = arrow.now()
        self.test_alerts = [
            {
                "incident_number": "1",
                "timestamp": base_time.isoformat(),
                "title": "Test Alert 1",
                "status": "open"
            },
            {
                "incident_number": "2",
                "timestamp": base_time.shift(minutes=-30).isoformat(),
                "title": "Test Alert 2",
                "status": "resolved"
            }
        ]
        
        # Write test alerts to temporary file
        with open(self.log_file, "w") as f:
            for alert in self.test_alerts:
                f.write(json.dumps(alert) + "\n")
        
        # Create cache instance with short TTL
        self.cache = AlertCache(ttl_seconds=1)
        
    def tearDown(self):
        # Clean up temporary files
        if os.path.exists(self.log_file):
            os.remove(self.log_file)
        os.rmdir(self.temp_dir)
    
    def test_initial_load(self):
        """Test that alerts are loaded correctly on first access."""
        alerts, last_update, source = self.cache.get_alerts()
        self.assertEqual(len(alerts), 2)
        self.assertEqual(source, "file_loaded")
        self.assertIsNotNone(last_update)
    
    def test_cache_ttl(self):
        """Test that cache refreshes after TTL expires."""
        # First access loads from file
        alerts1, last_update1, source1 = self.cache.get_alerts()
        self.assertEqual(source1, "file_loaded")
        
        # Immediate access should use cache
        alerts2, last_update2, source2 = self.cache.get_alerts()
        self.assertEqual(source2, "cached")
        self.assertEqual(last_update1, last_update2)
        
        # Wait for TTL to expire
        import time
        time.sleep(2)
        
        # Should reload from file
        alerts3, last_update3, source3 = self.cache.get_alerts()
        self.assertEqual(source3, "file_loaded")
        self.assertNotEqual(last_update2, last_update3)
    
    def test_force_refresh(self):
        """Test that force_refresh=True always reloads from file."""
        # Load into cache
        self.cache.get_alerts()
        
        # Force refresh should reload even if TTL hasn't expired
        alerts, last_update, source = self.cache.get_alerts(force_refresh=True)
        self.assertEqual(source, "file_loaded")
    
    def test_missing_file(self):
        """Test behavior when log file is missing."""
        # Remove the log file
        os.remove(self.log_file)
        
        alerts, last_update, source = self.cache.get_alerts()
        self.assertEqual(len(alerts), 0)
        self.assertEqual(source, "file_not_found")
    
    def test_duplicate_incident_numbers(self):
        """Test that only the latest alert for each incident is kept."""
        # Add duplicate incident with newer timestamp
        duplicate_alert = {
            "incident_number": "1",  # Same as test_alerts[0]
            "timestamp": arrow.now().shift(minutes=5).isoformat(),
            "title": "Updated Alert 1",
            "status": "resolved"
        }
        
        with open(self.log_file, "a") as f:
            f.write(json.dumps(duplicate_alert) + "\n")
        
        alerts, _, _ = self.cache.get_alerts(force_refresh=True)
        
        # Should still have 2 alerts (not 3)
        self.assertEqual(len(alerts), 2)
        
        # Find alert with incident_number "1" - should be the newer version
        alert_1 = next(a for a in alerts if a["incident_number"] == "1")
        self.assertEqual(alert_1["title"], "Updated Alert 1")
        self.assertEqual(alert_1["status"], "resolved")

if __name__ == '__main__':
    unittest.main()