from datetime import datetime, timezone
from typing import List, Dict, Tuple
from enum import Enum
from configparser import ConfigParser

from jira.client import ResultList
from jira import JIRA

from app.model.ticketfields import TicketFields
from app.utils.logger import log


class TicketType(Enum):
    """Enumeration for different types of ticket checks."""
    DEVELOPER_RESPONSE = "developer_response"
    FIX_DEADLINE = "fix_deadline"

class TicketProcessor:
    """
    Processes JIRA tickets for security audit notifications.
    
    This class handles the processing of JIRA tickets to identify:
    1. Tickets that need responses from auditors
    2. Tickets that have passed its fix deadline
    """
    
    RESPONSE_THRESHOLD_DAYS = 3
    DEADLINE_THRESHOLD_DAYS = 14
    JIRA_FIELDS = 'key,assignee,status,reporter,customfield_12923,comment,priority,issuetype,resolution,updated'
    MAX_RESULTS = 1000
    
    def __init__(self, jira_client: JIRA, active_auditor_list: List[str], config: ConfigParser) -> None:
        """
        Initialize the ticket processor.
        
        Args:
            jira_client (JIRA): Authenticated JIRA client instance
            active_auditor_list (List[str]): List of active auditor usernames
        """
        self.jira_client = jira_client
        self.active_auditor_list = active_auditor_list
        self.config = config
        self._validate_inputs()
    
    def _validate_inputs(self) -> None:
        """Validate initialization inputs."""
        if not self.jira_client:
            raise ValueError("JIRA client cannot be None")
        if not isinstance(self.active_auditor_list, list):
            raise ValueError("Active auditor list must be a list")
    
    def _is_auditor(self, author) -> bool:
        """
        Check if the comment author is an auditor.
        
        Args:
            author (JIRA): Comment author object from JIRA
            
        Returns:
            bool: True if author is auditor, False otherwise
        """
        if not author:
            return False
        
        if author.name in self.active_auditor_list:
            return True
        
        if 'CSDD' in author.displayName:
            return True
        
        auditor_service_accounts = [
            'sv-jira-ocz-bot',
            'sv-jira-csdd-bot',
        ]
        
        if author.name in auditor_service_accounts:
            return True
        
        return False
    
    def _needs_response(self, ticket_dict: Dict) -> bool:
        """
        Check if a ticket needs a response based on last comment time.
        
        Args:
            ticket_dict (Dict): Dictionary containing ticket information
            
        Returns:
            bool: True if ticket needs response, False otherwise
        """
        try:
            last_comment_time = ticket_dict.get('LastCommentAt')
            if not last_comment_time:
                log.warning(f'No latest comment time found for ticket: {ticket_dict.get("Ticket", "Unknown")}')
                return False
            
            time_diff = datetime.now(timezone.utc) - last_comment_time
            return time_diff.days > self.RESPONSE_THRESHOLD_DAYS
            
        except Exception as e:
            log.error(f'Error checking if ticket needs response: {e}')
            raise
    
    def _is_past_fix_deadline(self, fix_deadline_str: str) -> bool:
        """
        Check if a ticket is past its fix deadline.
        
        Args:
            fix_deadline_str (str): Fix deadline string in YYYY-MM-DD format
            
        Returns:
            bool: True if past deadline threshold, False otherwise
        """
        try:
            fix_deadline_date = datetime.strptime(fix_deadline_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            time_diff = datetime.now(timezone.utc) - fix_deadline_date
            return time_diff.days > self.DEADLINE_THRESHOLD_DAYS
            
        except ValueError as e:
            log.error(f'Invalid fix deadline format: {fix_deadline_str} - {e}')
            return False
    
    def _log_ticket_processing(self, issue, ticket_type: TicketType, **kwargs) -> None:
        """
        Log ticket processing information.
        
        Args:
            issue (JIRA): JIRA issue object
            ticket_type (TicketType): Type of ticket processing
            **kwargs (Dict): Additional logging parameters
        """
        base_info = f'Ticket: {issue.key} | Auditor: {issue.fields.reporter.displayName}'
        
        if ticket_type == TicketType.DEVELOPER_RESPONSE:
            last_comment_author = kwargs.get('last_comment_author')
            role = kwargs.get('role', 'Unknown')
            log.debug(f'{base_info} | Last comment by: {last_comment_author} | Role: {role}')
            
        elif ticket_type == TicketType.FIX_DEADLINE:
            fix_deadline = kwargs.get('fix_deadline')
            resolution = kwargs.get('resolution', 'Unknown')
            log.debug(f'{base_info} | Fix deadline: {fix_deadline} | Resolution: {resolution}')
    
    def process_developer_response_check(self, issues: ResultList) -> List[Dict]:
        """
        Process tickets to find those needing auditor responses to developer comments.
        
        Args:
            issues (ResultList): JIRA issues to process
            
        Returns:
            list[dict]: List of ticket dictionaries that need responses
        """
        ticket_list = []
        
        try:
            if not issues:
                log.info('No tickets found for developer response check')
                return ticket_list
            
            for issue in issues:
                if not issue.fields.comment.comments:
                    continue
                
                last_comment = issue.fields.comment.comments[-1]
                last_comment_author = last_comment.author
                
                if self._is_auditor(last_comment_author):
                    self._log_ticket_processing(
                        issue, 
                        TicketType.DEVELOPER_RESPONSE,
                        last_comment_author=last_comment_author.displayName,
                        role='Auditor'
                    )
                    continue
                
                # Process developer comment
                ticket = TicketFields(issue).to_dict()
                
                if self._needs_response(ticket):
                    ticket_list.append(ticket)
                    self._log_ticket_processing(
                        issue,
                        TicketType.DEVELOPER_RESPONSE,
                        last_comment_author=last_comment_author.displayName,
                        role='Developer'
                    )
            
            return ticket_list
            
        except Exception as e:
            log.error(f"Error processing developer response check: {e}")
            raise
    
    def process_fix_deadline_check(self, issues: ResultList) -> List[Dict]:
        """
        Process tickets to find those past its fix deadline.
        
        Args:
            issues (ResultList): JIRA issues to process
            
        Returns:
            list[dict]: List of ticket dictionaries past fix deadline
        """
        ticket_list = []
        
        try:
            if not issues:
                log.info('No tickets found for fix deadline check')
                return ticket_list
            
            for issue in issues:
                # Only process tickets from active auditors
                if issue.fields.reporter.name not in self.active_auditor_list:
                    continue
                
                fix_deadline = issue.fields.customfield_12923
                if not fix_deadline:
                    continue
                
                ticket = TicketFields(issue).to_dict()
                ticket_list.append(ticket)
                
                resolution_name = issue.fields.resolution.name if issue.fields.resolution else 'None'
                self._log_ticket_processing(
                    issue,
                    TicketType.FIX_DEADLINE,
                    fix_deadline=fix_deadline,
                    resolution=resolution_name
                )
            
            return ticket_list
            
        except Exception as e:
            log.error(f"Error processing fix deadline check: {e}")
            raise
    
    def search_issues(self, jql: str) -> ResultList:
        """
        Search for JIRA issues using JQL query.
        
        Args:
            jql (str): JQL query string
            
        Returns:
            ResultList: ResultList of JIRA issues
        """
        try:
            issues = self.jira_client.search_issues(
                jql,
                fields=self.JIRA_FIELDS,
                maxResults=self.MAX_RESULTS,
                expand='comments'
            )
            
            log.debug(f'Found {len(issues)} issues for query: {jql}')
            return issues
            
        except Exception as e:
            log.error(f"Error searching JIRA issues: {e}")
            raise
    
    def process_all_tickets(self) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        Process all ticket types and return comprehensive results.
        
        Returns:
            Tuple[List[Dict], List[Dict], List[Dict]]: Tuple containing (all_tickets, needs_response, past_deadline)
        """
        try:
            # Search for issues
            dev_check_issues = self.search_issues(self.config['JQL']['jql_for_dev_check'])
            fix_deadline_issues = self.search_issues(self.config['JQL']['jql_for_fix_deadline_check'])
            
            # Process issues
            tickets_needs_response = self.process_developer_response_check(dev_check_issues)
            tickets_past_deadline = self.process_fix_deadline_check(fix_deadline_issues)
            
            # Combine results
            all_tickets = tickets_needs_response + tickets_past_deadline
            
            log.debug(f'Processing complete: {len(tickets_needs_response)} need response, '
                    f'{len(tickets_past_deadline)} past deadline, {len(all_tickets)} total')
            
            return all_tickets, tickets_needs_response, tickets_past_deadline
            
        except Exception as e:
            log.error(f"Error processing tickets: {e}")
            raise