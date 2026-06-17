import time
from configparser import ConfigParser
import requests
from app.utils.logger import log


class WebhookConfig:
    """Webhook configuration container with validation."""
    DEFAULT_TIMEOUT = 30
    DEFAULT_MAX_RETRIES = 3
    
    def __init__(self, config: ConfigParser):
        self._validate_config(config)
        self.webhook_url = config['WEBHOOK']['webhook_url']
        self.sender_email = config['WEBHOOK']['sender_email']
    
    @staticmethod
    def _validate_config(config: ConfigParser) -> None:
        """Validate that required configuration sections and keys exist."""
        if 'WEBHOOK' not in config:
            raise ValueError("Missing 'WEBHOOK' section in configuration")
        
        required_keys = ['webhook_url', 'sender_email']
        webhook_config = config['WEBHOOK']
        
        for key in required_keys:
            if key not in webhook_config or not webhook_config[key].strip():
                raise ValueError(f"Missing or empty '{key}' in WEBHOOK configuration")


class RetryStrategy:
    
    def __init__(self, max_retries: int = WebhookConfig.DEFAULT_MAX_RETRIES):
        self.max_retries = max_retries
    
    def calculate_wait_time(self, attempt: int) -> int:
        """
        Calculate wait time using exponential backoff.
        
        Args:
            attempt (int): Current attempt number (1-based)
            
        Returns:
            int: Wait time in seconds
        """
        return 2 ** attempt
    
    def should_retry(self, attempt: int) -> bool:
        """
        Determine if another retry should be attempted.
        
        Args:
            attempt (int): Current attempt number (1-based)
            
        Returns:
            bool: True if should retry, False otherwise
        """
        return attempt < self.max_retries


class SendNotificationViaWebhook:
    """
    Service for sending email notifications to trigger Power Automate flows.
    
    This class handles the complete workflow of:
    1. Validate email content
    2. Send email with retry logic
    3. Trigger Power Automate flow
    """
    
    def __init__(
        self, 
        content: str, 
        auditor: str, 
        user_email: str, 
        config: ConfigParser,
        timeout: int = WebhookConfig.DEFAULT_TIMEOUT,
        max_retries: int = WebhookConfig.DEFAULT_MAX_RETRIES
    ):
        """
        Initialize the webhook notification service.  
        
        Args:
            content (str): HTML content to send in the webhook
            auditor (str): Name/ID of the auditor for logging purposes
            user_email (str): Recipient email address
            config (ConfigParser): ConfigParser instance with webhook configuration
            timeout (int): SMTP timeout in seconds
            max_retries (int): Maximum number of retry attempts
            
        Raises:
            ValueError: If webhook configuration is invalid
        """
        self.content = content
        self.auditor = auditor
        self.user_email = user_email
        self.timeout = timeout
        
        self.webhook_config = WebhookConfig(config)
        self.retry_strategy = RetryStrategy(max_retries)

        self.payload = {
            "userEmail": user_email,
            "senderEmail": self.webhook_config.sender_email,
            "message": content,
        }
    
    def send_notification(self) -> bool:
        """
        Send webhook notification with retry logic.
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        if not self._validate_content():
            return False
        
        return self._send_with_retry()
    
    def _validate_content(self) -> bool:
        """
        Validate email content before sending.
        
        Returns:
            bool: True if content is valid, False otherwise
        """
        if self.content is None:
            log.warning(f"Email content is None for auditor {self.auditor}, skipping send")
            return False
        
        if not self.content.strip():
            log.warning(f"Email content is empty for auditor {self.auditor}, skipping send")
            return False
        
        return True
    
    def _send_with_retry(self) -> bool:
        """
        Send email with retry logic and exponential backoff.
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        for attempt in range(1, self.retry_strategy.max_retries + 1):
            try:
                log.debug(
                    f"Sending email for auditor {self.auditor} "
                    f"(attempt {attempt}/{self.retry_strategy.max_retries})"
                )
                
                if self._send_via_webhook_attempt():
                    if attempt > 1:
                        log.debug(f"Email sent successfully for auditor {self.auditor} on attempt {attempt}")
                    else:
                        log.debug(f"Email sent successfully for auditor {self.auditor}")
                    return True
                    
            except RuntimeError as e:
                log.warning(f"Attempt {attempt} failed for auditor {self.auditor}: {e}")
            except Exception as e:
                log.error(f"Unexpected error on attempt {attempt} for auditor {self.auditor}: {e}")
            
            # Wait before retry if not the last attempt
            if self.retry_strategy.should_retry(attempt):
                wait_time = self.retry_strategy.calculate_wait_time(attempt)
                log.debug(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
        
        log.error(f"Failed to send email for auditor {self.auditor} after {self.retry_strategy.max_retries} attempts")
        return False

    def _send_via_webhook_attempt(self) -> bool:
        """
        Send email via webhook.
        
        Returns:
            bool: True if email sent successfully, False otherwise
            
        Raises:
            RuntimeError: If webhook sending fails
        """
        try:
            response = requests.post(
                self.webhook_config.webhook_url, 
                json=self.payload, 
                timeout=self.timeout
            )
            
            log.debug(f"Webhook response status: {response.status_code} for auditor {self.auditor}")
            
            response.raise_for_status()
            log.debug(f"Successfully sent webhook notification for auditor: {self.auditor}")
            return True
                
        except requests.exceptions.Timeout:
            raise RuntimeError(f"Webhook request timeout ({self.timeout}s)")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"Webhook connection failed: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Webhook request failed: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected webhook error: {type(e).__name__}: {e}")

    

