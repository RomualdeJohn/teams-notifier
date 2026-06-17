import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

from app.model.ticketfields import (
    NotificationFrequency,
    DateTimeParser,
    CommentProcessor,
    TicketFields
)


class TestDateTimeParser(unittest.TestCase):
    
    def test_parse_jira_datetime_with_z(self):
        """Test parsing JIRA datetime with Z suffix."""
        datetime_str = "2023-12-01T10:30:45Z"
        result = DateTimeParser.parse_jira_datetime(datetime_str)
        
        expected = datetime(2023, 12, 1, 10, 30, 45, tzinfo=timezone.utc)
        self.assertEqual(result, expected)
    
    def test_parse_jira_datetime_with_milliseconds_z(self):
        """Test parsing JIRA datetime with milliseconds and Z suffix."""
        datetime_str = "2023-12-01T10:30:45.123Z"
        result = DateTimeParser.parse_jira_datetime(datetime_str)
        
        expected = datetime(2023, 12, 1, 10, 30, 45, tzinfo=timezone.utc)
        self.assertEqual(result, expected)
    
    def test_parse_jira_datetime_with_timezone_offset(self):
        """Test parsing JIRA datetime with timezone offset."""
        datetime_str = "2023-12-01T10:30:45+0900"
        result = DateTimeParser.parse_jira_datetime(datetime_str)
        
        expected_tz = timezone(timedelta(hours=9))
        expected = datetime(2023, 12, 1, 10, 30, 45, tzinfo=expected_tz)
        self.assertEqual(result, expected)
    
    def test_parse_jira_datetime_complex_milliseconds(self):
        """Test parsing datetime with complex milliseconds."""
        datetime_str = "2023-12-01T10:30:45.123456+0900"
        result = DateTimeParser.parse_jira_datetime(datetime_str)
        
        expected_tz = timezone(timedelta(hours=9))
        expected = datetime(2023, 12, 1, 10, 30, 45, tzinfo=expected_tz)
        self.assertEqual(result, expected)


class TestCommentProcessor(unittest.TestCase):
    
    def test_clean_comment_body_normal(self):
        """Test cleaning normal comment body."""
        comment = "This is a normal comment with some    extra    spaces."
        result = CommentProcessor.clean_comment_body(comment)
        expected = "This is a normal comment with some extra spaces."
        self.assertEqual(result, expected)
    
    def test_clean_comment_body_with_newlines(self):
        """Test cleaning comment body with newlines and tabs."""
        comment = "This is a comment\nwith newlines\tand tabs\r\nand carriage returns."
        result = CommentProcessor.clean_comment_body(comment)
        expected = "This is a comment with newlines and tabs and carriage returns."
        self.assertEqual(result, expected)
    
    def test_clean_comment_body_whitespace_only(self):
        """Test cleaning comment body with only whitespace."""
        comment = "   \n\t\r\n   "
        result = CommentProcessor.clean_comment_body(comment)
        self.assertEqual(result, "")
    
    def test_clean_comment_body_truncation(self):
        """Test comment body truncation when exceeding max length."""
        long_comment = "a" * (CommentProcessor.MAX_COMMENT_LENGTH + 100)
        result = CommentProcessor.clean_comment_body(long_comment)
        
        self.assertEqual(len(result), CommentProcessor.MAX_COMMENT_LENGTH)
        self.assertTrue(result.startswith("a"))
    
    def test_is_recent_comment_recent(self):
        """Test recent comment detection for recent comments."""
        recent_date = datetime.now(timezone.utc) - timedelta(days=5)
        self.assertTrue(CommentProcessor.is_recent_comment(recent_date))
    
    def test_is_recent_comment_old(self):
        """Test recent comment detection for old comments."""
        old_date = datetime.now(timezone.utc) - timedelta(days=15)
        self.assertFalse(CommentProcessor.is_recent_comment(old_date))


class TestTicketFields(unittest.TestCase):
    """Test cases for TicketFields class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_issue = Mock()
        self.mock_fields = Mock()
        self.mock_issue.fields = self.mock_fields
        self.mock_issue.key = "TEST-123"
        
        # Setup basic field mocks
        self.mock_fields.status = Mock()
        self.mock_fields.status.name = "Open"
        
        self.mock_fields.priority = Mock()
        self.mock_fields.priority.name = "High"
        
        self.mock_fields.issuetype = Mock()
        self.mock_fields.issuetype.name = "Bug"
        
        self.mock_fields.reporter = Mock()
        self.mock_fields.reporter.displayName = "John Doe"
        self.mock_fields.reporter.emailAddress = "john.doe@example.com"
        self.mock_fields.reporter.active = True
        self.mock_fields.reporter.timeZone = "Asia/Tokyo"
        
        self.mock_fields.customfield_12923 = "2023-12-31T23:59:59Z"
        self.mock_fields.updated = "2023-12-01T10:30:45Z"
        self.mock_fields.resolution = None
        
        # Setup comment mock
        self.mock_comment = Mock()
        self.mock_comment.author = Mock()
        self.mock_comment.author.displayName = "Jane Smith"
        self.mock_comment.body = "This is a test comment"
        self.mock_comment.created = "2023-12-01T09:00:00Z"
        
        self.mock_fields.comment = Mock()
        self.mock_fields.comment.comments = [self.mock_comment]
    
    def test_ticket_fields_initialization(self):
        """Test TicketFields initialization."""
        ticket = TicketFields(self.mock_issue)
        
        self.assertEqual(ticket.key, "TEST-123")
        self.assertEqual(ticket.status, "Open")
        self.assertEqual(ticket.priority, "High")
        self.assertEqual(ticket.type, "Bug")
        self.assertEqual(ticket.auditor, "John Doe")
        self.assertEqual(ticket.email, "john.doe@example.com")
        self.assertTrue(ticket.auditor_active)
        self.assertEqual(ticket.auditor_timezone, "Asia/Tokyo")
    
    def test_get_effective_auditor_info_active(self):
        """Test effective auditor info for active auditor."""
        ticket = TicketFields(self.mock_issue)
        name, email = ticket._get_effective_auditor_info()
        
        self.assertEqual(name, "John Doe")
        self.assertEqual(email, "john.doe@example.com")
    
    def test_get_effective_auditor_info_inactive_with_manager(self):
        """Test effective auditor info for inactive auditor with manager."""
        self.mock_fields.reporter.active = False
        ticket = TicketFields(self.mock_issue)
        name, email = ticket._get_effective_auditor_info()
        
        self.assertEqual(name, "Su, Yu-Lo | Ryan | TWR")
        self.assertEqual(email, "yulo.su@rakuten.com")
    
    def test_process_comment_data_with_comments(self):
        """Test processing comment data when comments exist."""
        ticket = TicketFields(self.mock_issue)
        comment_data = ticket._process_comment_data()
        
        self.assertEqual(comment_data['LastCommentAuthor'], "Jane Smith")
        self.assertEqual(comment_data['LastComment'], "This is a test comment")
        self.assertIsInstance(comment_data['LastCommentAt'], datetime)
        self.assertIn('d', comment_data['CommentDaysAgo'])
        self.assertIsInstance(comment_data['IsRecentComment'], bool)
    
    @patch('app.model.ticketfields.needs_response_rule_based')
    def test_determine_notification_frequency_resolved(self, mock_needs_response):
        """Test notification frequency for resolved tickets."""
        self.mock_fields.resolution = Mock()
        self.mock_fields.resolution.name = "Fixed"
        
        ticket = TicketFields(self.mock_issue)
        comment_data = {}
        frequency = ticket._determine_notification_frequency(comment_data)
        
        self.assertEqual(frequency, NotificationFrequency.WEEKLY.value)
    
    @patch('app.model.ticketfields.needs_response_rule_based')
    def test_determine_notification_frequency_needs_response_recent(self, mock_needs_response):
        """Test notification frequency for tickets needing response with recent comments."""
        mock_needs_response.return_value = True
        
        ticket = TicketFields(self.mock_issue)
        comment_data = {
            'LastComment': 'Please help with this issue?',
            'IsRecentComment': True
        }
        frequency = ticket._determine_notification_frequency(comment_data)
        
        self.assertEqual(frequency, NotificationFrequency.SCHEDULED.value)
        mock_needs_response.assert_called_once_with('Please help with this issue?')
    
    @patch('app.model.ticketfields.needs_response_rule_based')
    def test_determine_notification_frequency_needs_response_old(self, mock_needs_response):
        """Test notification frequency for tickets needing response with old comments."""
        mock_needs_response.return_value = True
        
        ticket = TicketFields(self.mock_issue)
        comment_data = {
            'LastComment': 'Please help with this issue?',
            'IsRecentComment': False
        }
        frequency = ticket._determine_notification_frequency(comment_data)
        
        self.assertEqual(frequency, NotificationFrequency.WEEKLY.value)
    
    @patch('app.model.ticketfields.needs_response_rule_based')
    def test_determine_notification_frequency_no_response_needed(self, mock_needs_response):
        """Test notification frequency for tickets not needing response."""
        mock_needs_response.return_value = False
        
        ticket = TicketFields(self.mock_issue)
        comment_data = {
            'LastComment': 'Thanks for the update.',
            'IsRecentComment': True
        }
        frequency = ticket._determine_notification_frequency(comment_data)
        
        self.assertEqual(frequency, NotificationFrequency.WEEKLY.value)
    
    def test_to_dict_complete(self):
        """Test converting ticket to dictionary with all fields."""
        ticket = TicketFields(self.mock_issue)
        result = ticket.to_dict()
        
        self.assertEqual(result['Ticket'], "TEST-123")
        self.assertEqual(result['Status'], "Open")
        self.assertEqual(result['Priority'], "High")
        self.assertEqual(result['Type'], "Bug")
        self.assertEqual(result['Auditor'], "John Doe")
        self.assertEqual(result['Email'], "john.doe@example.com")
        self.assertTrue(result['IsActiveAuditor'])
        self.assertEqual(result['AuditorTimezone'], "Asia/Tokyo")
        
        self.assertIn('LastUpdated', result)
        self.assertIn('FixDeadlineAgo', result)
        self.assertIn('LastCommentAuthor', result)
        self.assertIn('Frequency', result)
    
    def test_resolution_handling(self):
        """Test handling of resolution field."""
        self.mock_fields.resolution = Mock()
        self.mock_fields.resolution.name = "Fixed"
        
        ticket = TicketFields(self.mock_issue)
        self.assertEqual(ticket.resolution, "Fixed")
        
        result = ticket.to_dict()
        self.assertEqual(result['Resolution'], "Fixed")


if __name__ == '__main__':
    unittest.main()
