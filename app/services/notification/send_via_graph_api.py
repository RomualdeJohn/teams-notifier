from __future__ import annotations

import requests
from configparser import ConfigParser
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from app.utils.logger import log


class ChatType(Enum):
    """Enumeration for Microsoft Teams chat types."""
    ONE_ON_ONE = "oneOnOne"
    GROUP = "group"
    

@dataclass
class ChatMember:
    """Represents a chat member in Microsoft Teams."""
    email: str
    roles: List[str]
    
    def to_graph_api_format(self) -> Dict[str, Any]:
        """Convert to Microsoft Graph API format."""
        return {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": self.roles,
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{self.email}')"
        }


@dataclass
class ChatConfig:
    """Configuration for chat creation."""
    chat_type: ChatType
    topic: str
    members: List[ChatMember]
    
    def to_request_body(self) -> Dict[str, Any]:
        """Convert to request body format for Graph API."""
        return {
            "chatType": self.chat_type.value,
            "topic": self.topic,
            "members": [member.to_graph_api_format() for member in self.members]
        }


class SendNotificationViaGraphAPI:
    """
    Service for sending notifications to Microsoft Teams via Graph API.
    
    This class handles the complete workflow of:
    1. Finding or creating a chat
    2. Sending messages to the chat
    3. Proper error handling and logging
    """
    
    # Constants
    MAX_CHATS_TO_FETCH = 50
    SUCCESS_STATUS_CREATED = 201
    SUCCESS_STATUS_OK = 200
    DEFAULT_MEMBER_ROLES = ["owner"]
    
    def __init__(
        self, 
        user_email: str, 
        message: str, 
        token: str, 
        config: ConfigParser, 
        topic: str,
        chat_type: ChatType = ChatType.GROUP,
        sender_email: Optional[str] = None,
        additional_members: Optional[List[str]] = None
    ) -> None:
        """
        Initialize the Teams notification service.
        
        Args:
            user_email (str): Email of the user to send notification to
            message (str): HTML message content to send
            token (str): Microsoft Graph API access token
            config (ConfigParser): Configuration parser containing API endpoints
            topic (str): Topic/title for the chat (ignored for one-on-one chats)
            chat_type (ChatType): Type of chat (GROUP or ONE_ON_ONE)
            sender_email (str): Email of the sender (required for one-on-one chats)
            additional_members (List[str]): List of additional member emails for group chats
            
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        self._validate_inputs(user_email, message, token, topic, chat_type, sender_email)
        
        self.user_email = user_email
        self.message = message
        self.topic = topic
        self.chat_type = chat_type
        self.sender_email = sender_email
        self.additional_members = additional_members or []
        self.graph_api_endpoint = self._get_graph_api_endpoint(config)
        self.headers = self._build_headers(token)
    
    def _validate_inputs(
        self, 
        user_email: str, 
        message: str, 
        token: str, 
        topic: str, 
        chat_type: ChatType, 
        sender_email: Optional[str]
    ) -> None:
        """Validate input parameters."""
        if not user_email or not user_email.strip():
            raise ValueError("User email cannot be empty")
        if not message or not message.strip():
            raise ValueError("Message cannot be empty")
        if not token or not token.strip():
            raise ValueError("Token cannot be empty")
        
        # Topic is required for group chats but not for one-on-one
        if chat_type == ChatType.GROUP and (not topic or not topic.strip()):
            raise ValueError("Topic cannot be empty for group chats")
        
        # Sender email is required for one-on-one chats
        if chat_type == ChatType.ONE_ON_ONE and (not sender_email or not sender_email.strip()):
            raise ValueError("Sender email is required for one-on-one chats")
    
    def _get_graph_api_endpoint(self, config: ConfigParser) -> str:
        """Extract and validate Graph API endpoint from config."""
        try:
            endpoint = config['MS_GRAPH_API']['graph_api_endpoint']
            if not endpoint:
                raise ValueError("Graph API endpoint not found in configuration")
            return endpoint
        except KeyError as e:
            raise ValueError(f"Missing configuration section or key: {e}")
    
    def _build_headers(self, token: str) -> Dict[str, str]:
        """Build HTTP headers for Graph API requests."""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def _create_chat_config(self) -> ChatConfig:
        """Create chat configuration based on chat type."""
        members = []
        
        if self.chat_type == ChatType.ONE_ON_ONE:
            # For one-on-one chats, add sender and recipient
            if not self.sender_email:
                raise ValueError("Sender email is required for one-on-one chats")
            
            sender_member = ChatMember(
                email=self.sender_email,
                roles=self.DEFAULT_MEMBER_ROLES
            )
            recipient_member = ChatMember(
                email=self.user_email,
                roles=self.DEFAULT_MEMBER_ROLES
            )
            members = [sender_member, recipient_member]
            
        else:  # GROUP chat
            # Add primary user
            primary_member = ChatMember(
                email=self.user_email,
                roles=self.DEFAULT_MEMBER_ROLES
            )
            members = [primary_member]
            
            # Add additional members if specified
            for email in self.additional_members:
                if email and email.strip():
                    additional_member = ChatMember(
                        email=email.strip(),
                        roles=self.DEFAULT_MEMBER_ROLES
                    )
                    members.append(additional_member)
        
        return ChatConfig(
            chat_type=self.chat_type,
            topic=self.topic if self.chat_type == ChatType.GROUP else "",
            members=members
        )
    
    def create_chat(self) -> Optional[str]:
        """
        Create a new chat in Microsoft Teams (one-on-one or group).
        
        Returns:
            str: Chat ID if successful, None otherwise
            
        Raises:
            RuntimeError: If chat creation fails
        """
        chat_type_str = "one-on-one" if self.chat_type == ChatType.ONE_ON_ONE else "group"
        identifier = f"with {self.user_email}" if self.chat_type == ChatType.ONE_ON_ONE else f"topic: {self.topic}"
        log.debug(f"Creating new {chat_type_str} chat {identifier}")
        
        chat_config = self._create_chat_config()
        request_body = chat_config.to_request_body()
        
        try:
            response = requests.post(
                f"{self.graph_api_endpoint}/chats",
                headers=self.headers,
                json=request_body,
                timeout=30
            )
            
            if response.status_code == self.SUCCESS_STATUS_CREATED:
                response_data = response.json()
                chat_id = response_data.get('id')
                
                if not chat_id:
                    raise RuntimeError("Chat ID not found in response")
                
                log.debug(f"Chat created successfully with ID: {chat_id}")
                return chat_id
            else:
                error_msg = f"Failed to create chat. Status: {response.status_code}, Response: {response.text}"
                log.error(error_msg)
                raise RuntimeError(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"Network error while creating chat: {str(e)}"
            log.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error while creating chat: {str(e)}"
            log.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _fetch_existing_chats(self) -> List[Dict[str, Any]]:
        """
        Fetch existing chats from Microsoft Teams.
        
        Returns:
            List[Dict[str, Any]]: List of chat dictionaries
            
        Raises:
            RuntimeError: If fetching chats fails
        """
        url = f"{self.graph_api_endpoint}/me/chats?$top={self.MAX_CHATS_TO_FETCH}"
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            
            if response.status_code != self.SUCCESS_STATUS_OK:
                error_msg = f"Failed to fetch chats. Status: {response.status_code}"
                log.error(error_msg)
                raise RuntimeError(error_msg)
            
            return response.json().get('value', [])
            
        except requests.RequestException as e:
            error_msg = f"Network error while fetching chats: {str(e)}"
            log.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _find_existing_chat(self, chats: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find an existing chat based on chat type and criteria.
        
        Args:
            chats (List[Dict[str, Any]]): List of chat dictionaries
            
        Returns:
            Dict[str, Any]: Chat dictionary if found, None otherwise
        """
        if self.chat_type == ChatType.GROUP:
            # For group chats, match by topic
            for chat in chats:
                if chat.get('topic') == self.topic:
                    return chat
        else:
            # For one-on-one chats, match by chat type and members
            for chat in chats:
                if chat.get('chatType') == 'oneOnOne':
                    # Additional logic could be added here to verify members
                    # For now, we'll create a new one-on-one chat each time
                    # as finding existing one-on-one chats requires member verification
                    pass
        
        return None
    
    def get_or_create_chat(self) -> str:
        """
        Get existing chat or create a new one based on chat type.
        
        Returns:
            str: Chat ID
            
        Raises:
            RuntimeError: If chat cannot be found or created
        """
        chat_type_str = "one-on-one" if self.chat_type == ChatType.ONE_ON_ONE else "group"
        identifier = f"with {self.user_email}" if self.chat_type == ChatType.ONE_ON_ONE else f"topic: {self.topic}"
        log.debug(f"Looking for existing {chat_type_str} chat {identifier}")
        
        try:
            # For one-on-one chats, we typically create a new chat each time
            # as finding existing ones requires complex member verification
            if self.chat_type == ChatType.ONE_ON_ONE:
                log.debug("Creating new one-on-one chat (existing chat lookup skipped)")
                return self.create_chat()
            
            # For group chats, try to find existing chat by topic
            existing_chats = self._fetch_existing_chats()
            target_chat = self._find_existing_chat(existing_chats)
            
            if target_chat:
                chat_id = target_chat.get('id')
                if not chat_id:
                    raise RuntimeError("Chat ID not found in existing chat")
                
                log.debug(f"Found existing group chat with topic: {self.topic}")
                return chat_id
            else:
                log.debug(f"No existing group chat found with topic: {self.topic}")
                return self.create_chat()
                
        except RuntimeError:
            raise
        except Exception as e:
            error_msg = f"Unexpected error while getting or creating chat: {str(e)}"
            log.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _build_message_body(self, message: str) -> Dict[str, Any]:
        """
        Build message body for Graph API request.
        
        Args:
            message (str): HTML message content
            
        Returns:
            Dict[str, Any]: Message body dictionary
        """
        return {
            "body": {
                "contentType": "html",
                "content": message
            }
        }
    
    def send_message_to_chat(self, message: str, chat_id: str) -> bool:
        """
        Send a message to a specific chat.
        
        Args:
            message (str): HTML message content to send
            chat_id (str): ID of the target chat
            
        Returns:
            bool: True if message sent successfully, False otherwise
            
        Raises:
            RuntimeError: If message sending fails
        """
        if not message or not message.strip():
            raise ValueError("Message cannot be empty")
        if not chat_id or not chat_id.strip():
            raise ValueError("Chat ID cannot be empty")
        
        log.debug(f"Sending message to chat ID: {chat_id}")
        
        message_body = self._build_message_body(message)
        url = f"{self.graph_api_endpoint}/chats/{chat_id}/messages"
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=message_body,
                timeout=30
            )
            
            if response.status_code == self.SUCCESS_STATUS_CREATED:
                response_data = response.json()
                message_id = response_data.get('id', 'Unknown')
                log.debug(f"Message sent successfully. Message ID: {message_id}")
                return True
            else:
                error_msg = f"Failed to send message. Status: {response.status_code}, Response: {response.text}"
                log.error(error_msg)
                raise RuntimeError(error_msg)
                
        except requests.RequestException as e:
            error_msg = f"Network error while sending message: {str(e)}"
            log.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error while sending message: {str(e)}"
            log.error(error_msg)
            raise RuntimeError(error_msg)
    
    def send_notification(self) -> bool:
        """
        Send notification to Teams chat.
        
        This is the main method that orchestrates the entire process:
        1. Get or create a chat
        2. Send the message to the chat
        
        Returns:
            bool: True if notification sent successfully, False otherwise
        """
        try:
            chat_id = self.get_or_create_chat()
            return self.send_message_to_chat(self.message, chat_id)
            
        except RuntimeError as e:
            log.error(f"Failed to send notification: {str(e)}")
            return False
        except Exception as e:
            log.error(f"Unexpected error during notification sending: {str(e)}")
            return False
