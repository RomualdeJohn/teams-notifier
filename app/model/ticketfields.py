from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any

from jira import JIRA

from app.utils.comment_checker import needs_response_rule_based


class NotificationFrequency(Enum):
    """Enumeration for notification frequency types."""
    SCHEDULED = "Scheduled (M,W) Notification"
    WEEKLY = "Weekly Report Notification"


@dataclass(frozen=True)
class Manager:
    """Represents a manager with name and email."""
    name: str
    email: str


class ManagerRegistry:
    """Registry for regional managers based on timezone."""
    
    _MANAGERS = {
        'Asia/Tokyo': Manager('Su, Yu-Lo | Ryan | TWR', 'yulo.su@rakuten.com'),
        'Asia/Taipei': Manager('Chi, WenPing | Peter | TWR', 'wenping.chi@rakuten.com'),
        'Asia/Kolkata': Manager('Rao, Karthik', 'karthik.rao@rakuten.com'),
    }
    
    @classmethod
    def get_manager_by_timezone(cls, timezone_str: str) -> Optional[Manager]:
        """Get manager by timezone string."""
        return cls._MANAGERS.get(timezone_str)


class DateTimeParser:
    """Utility class for parsing JIRA datetime strings."""
    
    @staticmethod
    def parse_jira_datetime(datetime_str: str) -> datetime:
        """
        Parse JIRA datetime string to datetime object.
        
        Args:
            datetime_str (str): JIRA datetime string in various formats
            
        Returns:
            datetime: Parsed datetime object with timezone info
            
        Raises:
            ValueError: If datetime string cannot be parsed
        """
        if not datetime_str:
            raise ValueError("Datetime string cannot be empty")
            
        cleaned_str = re.sub(r'\.\d+', '', datetime_str)

        if cleaned_str.endswith('Z'):
            cleaned_str = cleaned_str[:-1] + '+00:00'

        elif re.search(r'[+-]\d{4}$', cleaned_str):
            cleaned_str = cleaned_str[:-5] + cleaned_str[-5:-2] + ':' + cleaned_str[-2:]
        
        try:
            parsed_datetime = datetime.fromisoformat(cleaned_str)

            if not parsed_datetime.tzinfo:
                parsed_datetime = parsed_datetime.replace(tzinfo=timezone.utc)
            return parsed_datetime
        except ValueError as e:
            raise ValueError(f"Unable to parse datetime string '{datetime_str}': {e}")


class CommentProcessor:
    """Utility class for processing JIRA comments."""
    
    MAX_COMMENT_LENGTH = 50000
    RECENT_COMMENT_THRESHOLD_DAYS = 10
    
    @classmethod
    def clean_comment_body(cls, comment_body: str) -> str:
        """
        Clean and truncate comment body.
        
        Args:
            comment_body (str): Raw comment body text
            
        Returns:
            str: Cleaned and potentially truncated comment
        """
        if not comment_body:
            return ""
            
        cleaned = ' '.join(comment_body.split())
        
        if len(cleaned) > cls.MAX_COMMENT_LENGTH:
            cleaned = cleaned[:cls.MAX_COMMENT_LENGTH]
            
        return cleaned
    
    @classmethod
    def is_recent_comment(cls, comment_date: datetime) -> bool:
        """Check if comment is recent based on threshold."""
        if not comment_date:
            return False
        time_diff = datetime.now(timezone.utc) - comment_date
        return time_diff.days <= cls.RECENT_COMMENT_THRESHOLD_DAYS


class TicketFields:

    def __init__(self, issue: JIRA) -> None:  
        self._issue = issue
        self._extract_basic_fields()
    
    def _extract_basic_fields(self) -> None:
        """Extract basic fields from JIRA issue."""
        fields = self._issue.fields
        
        self.key = self._issue.key
        self.status = fields.status.name
        self.priority = fields.priority.name
        self.type = fields.issuetype.name
        self.auditor = fields.reporter.displayName
        self.email = fields.reporter.emailAddress
        self.auditor_active = fields.reporter.active
        self.auditor_timezone = fields.reporter.timeZone
        self.fix_deadline = fields.customfield_12923
        self.last_updated = fields.updated
        self.resolution = fields.resolution.name if fields.resolution else None
    
    def _get_effective_auditor_info(self) -> tuple[str, str]:
        """
        Get effective auditor name and email.
        
        If auditor is inactive, returns manager info based on timezone.
        
        Returns:
            tuple: (auditor_name, auditor_email)
        """
        if self.auditor_active:
            return self.auditor, self.email
            
        manager = ManagerRegistry.get_manager_by_timezone(self.auditor_timezone)
        if manager:
            return manager.name, manager.email
            
        return self.auditor, self.email
    
    def _process_comment_data(self) -> Dict[str, Any]:
        """
        Process comment-related data.
        
        Returns:
            dict: Comment-related fields
        """
        comment_data = {}
        comments = self._issue.fields.comment.comments
        
        if not comments:
            return comment_data
            
        last_comment = comments[-1]
        comment_date = DateTimeParser.parse_jira_datetime(last_comment.created)
        time_diff = datetime.now(timezone.utc) - comment_date
        
        comment_data.update({
            'LastCommentAuthor': last_comment.author.displayName,
            'LastComment': CommentProcessor.clean_comment_body(last_comment.body),
            'LastCommentAt': comment_date,
            'CommentDaysAgo': f'{time_diff.days}d',
            'IsRecentComment': CommentProcessor.is_recent_comment(comment_date)
        })
        
        return comment_data
    
    def _determine_notification_frequency(self, comment_data: Dict[str, Any]) -> str:
        """
        Determine notification frequency based on resolution and comment status.
        
        Args:
            comment_data (dict): Processed comment data
            
        Returns:
            str: Notification frequency
        """
        if self.resolution is not None:
            return NotificationFrequency.WEEKLY.value
            
        last_comment = comment_data.get('LastComment', '')
        is_recent = comment_data.get('IsRecentComment', False)
        
        if needs_response_rule_based(last_comment) and is_recent:
            return NotificationFrequency.SCHEDULED.value
        else:
            return NotificationFrequency.WEEKLY.value
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert ticket fields to dictionary format.
        
        Returns:
            dict: Dictionary containing all processed ticket fields
        """
        auditor_name, auditor_email = self._get_effective_auditor_info()
        
        ticket_data = {
            'Ticket': self.key,
            'Status': self.status,
            'Priority': self.priority,
            'Type': self.type,
            'Auditor': auditor_name,
            'Email': auditor_email,
            'IsActiveAuditor': self.auditor_active,
            'AuditorTimezone': self.auditor_timezone,
            'Resolution': self.resolution,
            'FixDeadlineDate': self.fix_deadline,
        }
        
        if self.last_updated:
            try:
                last_updated_date = DateTimeParser.parse_jira_datetime(self.last_updated)
                ticket_data['LastUpdated'] = last_updated_date.strftime('%Y-%m-%d')
            except ValueError:
                ticket_data['LastUpdated'] = None
        
        if self.fix_deadline:
            try:
                deadline_date = DateTimeParser.parse_jira_datetime(self.fix_deadline)
                time_diff = datetime.now(timezone.utc) - deadline_date
                ticket_data['FixDeadlineAgo'] = f'{time_diff.days}d'
            except ValueError:
                ticket_data['FixDeadlineAgo'] = None
        
        comment_data = self._process_comment_data()
        ticket_data.update(comment_data)
        
        ticket_data['Frequency'] = self._determine_notification_frequency(comment_data)
        
        return ticket_data
    
    def __repr__(self) -> str:
        """Return JSON representation of ticket fields."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    def __str__(self) -> str:
        """Return human-readable string representation."""
        return f"TicketFields(key={self.key}, status={self.status}, auditor={self.auditor})"
