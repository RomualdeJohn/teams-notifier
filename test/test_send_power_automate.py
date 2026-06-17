import unittest
from unittest.mock import Mock, patch
from configparser import ConfigParser
import requests

from app.services.notification.send_via_power_automate import (
    RetryStrategy,
    SendNotificationViaWebhook
)


class TestRetryStrategy(unittest.TestCase):
    
    def test_default_initialization(self):
        """Test RetryStrategy initialization with default values."""
        retry_strategy = RetryStrategy()
        self.assertEqual(retry_strategy.max_retries, 3)
    
    def test_custom_max_retries(self):
        """Test RetryStrategy initialization with custom max_retries."""
        retry_strategy = RetryStrategy(max_retries=5)
        self.assertEqual(retry_strategy.max_retries, 5)
    
    def test_should_retry_within_limit(self):
        """Test should_retry returns True when within retry limit."""
        retry_strategy = RetryStrategy(max_retries=3)
        
        self.assertTrue(retry_strategy.should_retry(1))
        self.assertTrue(retry_strategy.should_retry(2))
        self.assertFalse(retry_strategy.should_retry(3))
        self.assertFalse(retry_strategy.should_retry(4))


class TestSendNotificationViaWebhook(unittest.TestCase):
    
    def setUp(self):
        self.config = ConfigParser()
        self.config.add_section('WEBHOOK')
        self.config.set('WEBHOOK', 'webhook_url', 'https://example.com/webhook')
        self.config.set('WEBHOOK', 'sender_email', 'sender@example.com')
        
        self.content = "<html><body>Test notification</body></html>"
        self.auditor = "test_auditor"
        self.user_email = "user@example.com"
    
    @patch('app.services.notification.send_via_power_automate.log')
    def test_validate_content_none(self, mock_log):
        """Test content validation with None content."""
        service = SendNotificationViaWebhook(
            content=None,
            auditor=self.auditor,
            user_email=self.user_email,
            config=self.config
        )
        
        result = service._validate_content()
        
        self.assertFalse(result)
        mock_log.warning.assert_called_once_with(
            f"Email content is None for auditor {self.auditor}, skipping send"
        )
    
    def test_validate_content_valid(self):
        """Test content validation with valid content."""
        service = SendNotificationViaWebhook(
            content=self.content,
            auditor=self.auditor,
            user_email=self.user_email,
            config=self.config
        )
        
        result = service._validate_content()
        
        self.assertTrue(result)
    
    @patch('app.services.notification.send_via_power_automate.requests.post')
    def test_send_via_webhook_attempt_success(self, mock_post):
        """Test successful webhook sending."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        service = SendNotificationViaWebhook(
            content=self.content,
            auditor=self.auditor,
            user_email=self.user_email,
            config=self.config
        )
        
        result = service._send_via_webhook_attempt()
        
        self.assertTrue(result)
        mock_post.assert_called_once_with(
            'https://example.com/webhook',
            json={
                "userEmail": self.user_email,
                "senderEmail": "sender@example.com",
                "message": self.content
            },
            timeout=30
        )
    
    @patch('app.services.notification.send_via_power_automate.log')
    @patch('app.services.notification.send_via_power_automate.time.sleep')
    @patch.object(SendNotificationViaWebhook, '_send_via_webhook_attempt')
    def test_send_with_retry_all_attempts_fail(self, mock_send_attempt, mock_sleep, mock_log):
        """Test all retry attempts fail."""
        mock_send_attempt.side_effect = RuntimeError("All attempts failed")
        
        service = SendNotificationViaWebhook(
            content=self.content,
            auditor=self.auditor,
            user_email=self.user_email,
            config=self.config
        )
        
        result = service._send_with_retry()
        
        self.assertFalse(result)
        self.assertEqual(mock_send_attempt.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
        mock_log.error.assert_called_with(
            f"Failed to send email for auditor {self.auditor} after 3 attempts"
        )


class TestIntegration(unittest.TestCase):
    
    def setUp(self):
        self.config = ConfigParser()
        self.config.add_section('WEBHOOK')
        self.config.set('WEBHOOK', 'webhook_url', 'https://example.com/webhook')
        self.config.set('WEBHOOK', 'sender_email', 'sender@example.com')
        
        self.content = "<html><body>Integration test notification</body></html>"
        self.auditor = "integration_auditor"
        self.user_email = "integration@example.com"
    
    @patch('app.services.notification.send_via_power_automate.requests.post')
    @patch('app.services.notification.send_via_power_automate.log')
    def test_end_to_end_success(self, mock_log, mock_post):
        """Test complete end-to-end successful notification flow."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        service = SendNotificationViaWebhook(
            content=self.content,
            auditor=self.auditor,
            user_email=self.user_email,
            config=self.config
        )
        
        result = service.send_notification()
        
        self.assertTrue(result)
        mock_post.assert_called_once()
        mock_log.debug.assert_any_call(f"Email sent successfully for auditor {self.auditor}")
    
    @patch('app.services.notification.send_via_power_automate.requests.post')
    @patch('app.services.notification.send_via_power_automate.time.sleep')
    @patch('app.services.notification.send_via_power_automate.log')
    def test_end_to_end_with_retries(self, mock_log, mock_sleep, mock_post):
        """Test complete end-to-end flow with retries."""
        mock_response_fail = Mock()
        mock_response_fail.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Error")
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.raise_for_status.return_value = None
        
        mock_post.side_effect = [mock_response_fail, mock_response_success]
        
        service = SendNotificationViaWebhook(
            content=self.content,
            auditor=self.auditor,
            user_email=self.user_email,
            config=self.config
        )
        
        result = service.send_notification()
        
        self.assertTrue(result)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(2)
        mock_log.debug.assert_any_call(f"Email sent successfully for auditor {self.auditor} on attempt 2")


if __name__ == '__main__':
    unittest.main()
