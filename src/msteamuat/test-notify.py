from msteam.tools.notify import send_notification

test_alert = {
    "title": "TEST ALERT",
    "severity": "critical",
    "timestamp": "2025-06-10T00:00:00Z",
    "metric": "TEST METRIC",
    "incident_number": "999"
}

send_notification(test_alert, "TEST REASON")