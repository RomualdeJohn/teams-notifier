import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta
from configparser import ConfigParser
from typing import List

from jira import JIRA

from app.process_ticket import TicketProcessor


class TestTicketProcessor(unittest.TestCase):

    def setUp(self):
        self.mock_jira_client = Mock(spec=JIRA)
        self.active_auditor_list = ['auditor1', 'auditor2', 'csdd.user']
        self.mock_config = Mock(spec=ConfigParser)
        self.mock_config.__getitem__ = Mock(return_value={
            'jql_for_dev_check': 'project = TEST AND status != Done',
            'jql_for_fix_deadline_check': 'project = TEST AND fixDeadline < now()'
        })
        
        self.processor = TicketProcessor(
            jira_client=self.mock_jira_client,
            active_auditor_list=self.active_auditor_list,
            config=self.mock_config
        )
    
    def _create_mock_issue(self, 
                          key: str = 'TEST-123',
                          comments: List = None,
                          reporter_name: str = 'auditor1',
                          reporter_display_name: str = 'Test Auditor',
                          fix_deadline: str = None,
                          resolution_name: str = None) -> Mock:
        mock_issue = Mock()
        mock_issue.key = key
        
        mock_issue.fields = Mock()
        mock_issue.fields.comment = Mock()
        mock_issue.fields.comment.comments = comments or []
        
        mock_issue.fields.reporter = Mock()
        mock_issue.fields.reporter.name = reporter_name
        mock_issue.fields.reporter.displayName = reporter_display_name
        
        mock_issue.fields.customfield_12923 = fix_deadline
        
        if resolution_name:
            mock_issue.fields.resolution = Mock()
            mock_issue.fields.resolution.name = resolution_name
        else:
            mock_issue.fields.resolution = None
            
        return mock_issue
    
    def _create_mock_comment(self, 
                           author_name: str = 'developer1',
                           author_display_name: str = 'Test Developer',
                           created_days_ago: int = 5) -> Mock:
        mock_comment = Mock()
        mock_comment.author = Mock()
        mock_comment.author.name = author_name
        mock_comment.author.displayName = author_display_name
        
        created_date = datetime.now(timezone.utc) - timedelta(days=created_days_ago)
        mock_comment.created = created_date.isoformat()
        
        return mock_comment


class TestTicketProcessorHelperMethods(TestTicketProcessor):
    
    def test_is_auditor_with_active_auditor_name(self):
        """Test _is_auditor returns True for active auditor by name."""
        mock_author = Mock()
        mock_author.name = 'auditor1'
        mock_author.displayName = 'Test Auditor'
        
        result = self.processor._is_auditor(mock_author)
        self.assertTrue(result)
    
    def test_is_auditor_with_csdd_display_name(self):
        """Test _is_auditor returns True for CSDD in display name."""
        mock_author = Mock()
        mock_author.name = 'unknown.user'
        mock_author.displayName = 'John Doe | CSDD'
        
        result = self.processor._is_auditor(mock_author)
        self.assertTrue(result)
    
    def test_is_auditor_with_twr_display_name(self):
        """Test _is_auditor returns False for TWR in display name (TWR users are developers, not auditors)."""
        mock_author = Mock()
        mock_author.name = 'unknown.user'
        mock_author.displayName = 'Jane Smith | TWR'
        
        result = self.processor._is_auditor(mock_author)
        self.assertFalse(result)
    
    def test_is_auditor_with_non_auditor(self):
        """Test _is_auditor returns False for non-auditor."""
        mock_author = Mock()
        mock_author.name = 'developer1'
        mock_author.displayName = 'Regular Developer'
        
        result = self.processor._is_auditor(mock_author)
        self.assertFalse(result)
    
    def test_is_auditor_with_none_author(self):
        """Test _is_auditor returns False for None author."""
        result = self.processor._is_auditor(None)
        self.assertFalse(result)
    
    def test_is_auditor_with_service_account(self):
        """Test _is_auditor returns True for known auditor service accounts."""
        mock_author = Mock()
        mock_author.name = 'sv-jira-ocz-bot'
        mock_author.displayName = 'sv-jira-ocz-bot (R-Atlassian Service Account)'
        
        result = self.processor._is_auditor(mock_author)
        self.assertTrue(result)
        
        # Test another service account
        mock_author.name = 'sv-jira-csdd-bot'
        result = self.processor._is_auditor(mock_author)
        self.assertTrue(result)
    
    @patch('app.process_ticket.TicketFields')
    def test_needs_response_with_old_comment(self, mock_ticket_fields):
        """Test _needs_response returns True for old comments."""
        old_time = datetime.now(timezone.utc) - timedelta(days=5)
        mock_ticket_dict = {'LastCommentAt': old_time, 'Ticket': 'TEST-123'}
        
        result = self.processor._needs_response(mock_ticket_dict)
        self.assertTrue(result)
    
    @patch('app.process_ticket.TicketFields')
    def test_needs_response_with_recent_comment(self, mock_ticket_fields):
        """Test _needs_response returns False for recent comments."""
        recent_time = datetime.now(timezone.utc) - timedelta(days=1)
        mock_ticket_dict = {'LastCommentAt': recent_time, 'Ticket': 'TEST-123'}
        
        result = self.processor._needs_response(mock_ticket_dict)
        self.assertFalse(result)
    
    def test_needs_response_with_no_comment_time(self):
        """Test _needs_response returns False when no comment time exists."""
        mock_ticket_dict = {'Ticket': 'TEST-123'}
        
        with patch('app.process_ticket.log') as mock_log:
            result = self.processor._needs_response(mock_ticket_dict)
            self.assertFalse(result)
            mock_log.warning.assert_called_once()
    
    def test_is_past_fix_deadline_with_old_deadline(self):
        """Test _is_past_fix_deadline returns True for old deadlines."""
        old_deadline = (datetime.now(timezone.utc) - timedelta(days=20)).strftime('%Y-%m-%d')
        
        result = self.processor._is_past_fix_deadline(old_deadline)
        self.assertTrue(result)
    
    def test_is_past_fix_deadline_with_recent_deadline(self):
        """Test _is_past_fix_deadline returns False for recent deadlines."""
        recent_deadline = (datetime.now(timezone.utc) - timedelta(days=5)).strftime('%Y-%m-%d')
        
        result = self.processor._is_past_fix_deadline(recent_deadline)
        self.assertFalse(result)
    
    def test_is_past_fix_deadline_with_invalid_format(self):
        """Test _is_past_fix_deadline returns False for invalid date format."""
        with patch('app.process_ticket.log') as mock_log:
            result = self.processor._is_past_fix_deadline('invalid-date')
            self.assertFalse(result)
            mock_log.error.assert_called_once()


class TestTicketProcessorDeveloperResponseCheck(TestTicketProcessor):
    
    @patch('app.process_ticket.TicketFields')
    def test_process_developer_response_check_with_empty_issues(self, mock_ticket_fields):
        """Test processing empty issue list."""
        empty_issues = []
        
        with patch('app.process_ticket.log') as mock_log:
            result = self.processor.process_developer_response_check(empty_issues)
            
            self.assertEqual(result, [])
            mock_log.info.assert_called_with('No tickets found for developer response check')
    
    @patch('app.process_ticket.TicketFields')
    def test_process_developer_response_check_with_auditor_last_comment(self, mock_ticket_fields):
        """Test processing when last comment is from auditor (should skip)."""
        auditor_comment = self._create_mock_comment(
            author_name='auditor1',
            author_display_name='Test Auditor',
            created_days_ago=2
        )
        
        mock_issue = self._create_mock_issue(comments=[auditor_comment])
        issues = [mock_issue]
        
        with patch('app.process_ticket.log') as mock_log:
            result = self.processor.process_developer_response_check(issues)
            
            self.assertEqual(result, [])
            mock_log.debug.assert_called()
    
    @patch('app.process_ticket.TicketFields')
    def test_process_developer_response_check_with_developer_old_comment(self, mock_ticket_fields):
        """Test processing when developer comment needs response."""
        dev_comment = self._create_mock_comment(
            author_name='developer1',
            author_display_name='Test Developer',
            created_days_ago=5
        )
        
        mock_issue = self._create_mock_issue(comments=[dev_comment])
        issues = [mock_issue]
        
        mock_ticket_instance = Mock()
        mock_ticket_dict = {
            'Ticket': 'TEST-123',
            'LastCommentAt': datetime.now(timezone.utc) - timedelta(days=5)
        }
        mock_ticket_instance.to_dict.return_value = mock_ticket_dict
        mock_ticket_fields.return_value = mock_ticket_instance
        
        result = self.processor.process_developer_response_check(issues)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], mock_ticket_dict)
    
    @patch('app.process_ticket.TicketFields')
    def test_process_developer_response_check_with_developer_recent_comment(self, mock_ticket_fields):
        """Test processing when developer comment is recent (no response needed)."""
        dev_comment = self._create_mock_comment(
            author_name='developer1',
            author_display_name='Test Developer',
            created_days_ago=1
        )
        
        mock_issue = self._create_mock_issue(comments=[dev_comment])
        issues = [mock_issue]
        
        mock_ticket_instance = Mock()
        mock_ticket_dict = {
            'Ticket': 'TEST-123',
            'LastCommentAt': datetime.now(timezone.utc) - timedelta(days=1)
        }
        mock_ticket_instance.to_dict.return_value = mock_ticket_dict
        mock_ticket_fields.return_value = mock_ticket_instance
        
        result = self.processor.process_developer_response_check(issues)
        
        self.assertEqual(len(result), 0)
    
    def test_process_developer_response_check_with_no_comments(self):
        """Test processing issue with no comments (should skip)."""
        mock_issue = self._create_mock_issue(comments=[])
        issues = [mock_issue]
        
        result = self.processor.process_developer_response_check(issues)
        self.assertEqual(result, [])


class TestTicketProcessorFixDeadlineCheck(TestTicketProcessor):
    
    @patch('app.process_ticket.TicketFields')
    def test_process_fix_deadline_check_with_inactive_auditor(self, mock_ticket_fields):
        """Test processing skips tickets from inactive auditors."""
        mock_issue = self._create_mock_issue(
            reporter_name='inactive_auditor',
            fix_deadline='2024-01-01'
        )
        issues = [mock_issue]
        
        result = self.processor.process_fix_deadline_check(issues)
        self.assertEqual(result, [])
    
    @patch('app.process_ticket.TicketFields')
    def test_process_fix_deadline_check_with_no_deadline(self, mock_ticket_fields):
        """Test processing skips tickets with no fix deadline."""
        mock_issue = self._create_mock_issue(
            reporter_name='auditor1',
            fix_deadline=None
        )
        issues = [mock_issue]
        
        result = self.processor.process_fix_deadline_check(issues)
        self.assertEqual(result, [])
    
    @patch('app.process_ticket.TicketFields')
    def test_process_fix_deadline_check_with_valid_ticket(self, mock_ticket_fields):
        """Test processing valid ticket with deadline."""
        mock_issue = self._create_mock_issue(
            reporter_name='auditor1',
            fix_deadline='2024-01-01',
            resolution_name='Fixed'
        )
        issues = [mock_issue]
        
        mock_ticket_instance = Mock()
        mock_ticket_dict = {'Ticket': 'TEST-123', 'FixDeadlineDate': '2024-01-01'}
        mock_ticket_instance.to_dict.return_value = mock_ticket_dict
        mock_ticket_fields.return_value = mock_ticket_instance
        
        with patch('app.process_ticket.log') as mock_log:
            result = self.processor.process_fix_deadline_check(issues)
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0], mock_ticket_dict)
            mock_log.debug.assert_called()


class TestTicketProcessorIntegration(TestTicketProcessor):
    
    @patch('app.process_ticket.TicketFields')
    def test_process_all_tickets_successful(self, mock_ticket_fields):
        """Test successful processing of all ticket types."""
        dev_issues = [Mock()]
        deadline_issues = [Mock()]
        
        self.mock_jira_client.search_issues.side_effect = [dev_issues, deadline_issues]
        
        mock_ticket_instance = Mock()
        mock_ticket_dict = {'Ticket': 'TEST-123'}
        mock_ticket_instance.to_dict.return_value = mock_ticket_dict
        mock_ticket_fields.return_value = mock_ticket_instance
        
        with patch.object(self.processor, 'process_developer_response_check') as mock_dev_check, \
             patch.object(self.processor, 'process_fix_deadline_check') as mock_deadline_check:
            
            mock_dev_check.return_value = [{'Ticket': 'DEV-123'}]
            mock_deadline_check.return_value = [{'Ticket': 'DEADLINE-456'}]
            
            all_tickets, needs_response, past_deadline = self.processor.process_all_tickets()
            
            self.assertEqual(len(all_tickets), 2)
            self.assertEqual(len(needs_response), 1)
            self.assertEqual(len(past_deadline), 1)
            self.assertEqual(needs_response[0]['Ticket'], 'DEV-123')
            self.assertEqual(past_deadline[0]['Ticket'], 'DEADLINE-456')


if __name__ == '__main__':
    unittest.main()
