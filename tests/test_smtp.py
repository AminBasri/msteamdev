import os
import smtplib
import logging
import unittest
import sys
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# It's better to import the module you are testing
from src.msteamdev.tools import notify

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from .env file for integration test
load_dotenv()

def test_smtp_connection():
    """
    Tests the SMTP connection using credentials from environment variables.
    This is an integration test and requires a live SMTP server.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass]):
        logging.warning("Skipping SMTP connection test: Missing one or more required SMTP environment variables.")
        return

    try:
        smtp_port_int = int(smtp_port)
        logging.info(f"Attempting to connect to {smtp_host}:{smtp_port_int}...")
        with smtplib.SMTP(smtp_host, smtp_port_int, timeout=10) as server:
            server.set_debuglevel(0) # Quieter output
            logging.info("Connection established. Starting TLS...")
            server.starttls()
            logging.info("TLS started. Logging in...")
            server.login(smtp_user, smtp_pass)
            logging.info("Login successful.")
        logging.info("SMTP connection test successful.")
    except (smtplib.SMTPException, ConnectionRefusedError, OSError) as e:
        logging.error(f"SMTP connection test failed: {e}")
    except ValueError:
        logging.error(f"Invalid SMTP_PORT: {smtp_port}. Must be an integer.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

class TestDynamicNotification(unittest.TestCase):
    """Unit tests for the dynamic notification logic with mocking."""

    def setUp(self):
        """Set up common test data."""
        self.alert = {"incident_number": "123", "title": "Test Alert"}
        self.subject = "Test Subject"
        self.body = "Test Body"
        # Set dummy env vars for validation
        os.environ["SMTP_HOST"] = "smtp.test.com"
        os.environ["SMTP_PORT"] = "587"
        os.environ["SMTP_USERNAME"] = "user"
        os.environ["SMTP_PASSWORD"] = "pass"
        os.environ["ALERT_EMAIL_RECIPIENTS"] = "test@example.com"
        os.environ["ROCKETCHAT_WEBHOOK_URL"] = "http://rocketchat.test.com"
        os.environ["ROCKETCHAT_WEBHOOK_TOKEN"] = "token"

    @patch('src.msteamdev.tools.notify.smtplib.SMTP')
    @patch('src.msteamdev.tools.notify.requests.post')
    def test_smtp_succeeds(self, mock_post, mock_smtp):
        """Test that when SMTP succeeds, it returns a success message."""
        # Mock a successful response from Rocket.Chat
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = notify.send_dynamic_notification(self.alert, self.subject, self.body)

        mock_smtp.assert_called_once()
        mock_post.assert_called_once()
        self.assertIn("email to 1 recipients", result)
        self.assertIn("Rocket.Chat webhook message sent", result)

    @patch('src.msteamdev.tools.notify.smtplib.SMTP')
    @patch('src.msteamdev.tools.notify.requests.post')
    def test_smtp_fails_rocketchat_succeeds(self, mock_post, mock_smtp):
        """Test fallback to Rocket.Chat when SMTP fails."""
        mock_smtp.side_effect = smtplib.SMTPException("Test SMTP Failure")
        
        # Mock a successful response from Rocket.Chat
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        result = notify.send_dynamic_notification(self.alert, self.subject, self.body)
        
        mock_smtp.assert_called_once()
        mock_post.assert_called_once()
        self.assertIn("Notification sent successfully via Rocket.Chat", result)
        self.assertIn("Email failed", result)

    @patch('src.msteamdev.tools.notify.smtplib.SMTP')
    @patch('src.msteamdev.tools.notify.requests.post')
    def test_smtp_succeeds_rocketchat_fails(self, mock_post, mock_smtp):
        """Test scenario where SMTP succeeds but Rocket.Chat fails."""
        # Mock a failed response from Rocket.Chat
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        # This test needs to call the lower-level function to properly test the logic inside send_dynamic_notification
        with patch('src.msteamdev.tools.notify.send_rocketchat_webhook_message') as mock_send_rocket:
            mock_send_rocket.return_value = False
            result = notify.send_dynamic_notification(self.alert, self.subject, self.body)

        mock_smtp.assert_called_once()
        self.assertIn("Notification sent successfully via email", result)
        self.assertIn("Rocket.Chat failed", result)

    @patch('src.msteamdev.tools.notify.smtplib.SMTP')
    @patch('src.msteamdev.tools.notify.requests.post')
    def test_both_smtp_and_rocketchat_fail(self, mock_post, mock_smtp):
        """Test that an exception is raised when both notification methods fail."""
        mock_smtp.side_effect = smtplib.SMTPException("Test SMTP Failure")
        
        # Mock a failed response from Rocket.Chat
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response
        
        with self.assertRaises(Exception) as context:
            notify.send_dynamic_notification(self.alert, self.subject, self.body)
        
        self.assertIn("Failed to send notification via both email and Rocket.Chat", str(context.exception))
        self.assertEqual(mock_smtp.call_count, 2)
        mock_post.assert_called_once()

if __name__ == "__main__":
    # Run the integration test
    test_smtp_connection()
    # Run the unit tests
    unittest.main()