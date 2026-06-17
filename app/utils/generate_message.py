from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import os
import re

from app.utils.logger import log


class Constants:
    """Application constants."""
    COMMENT_MAX_LENGTH = 200
    TABLE_COLSPAN = 5
    JIRA_BASE_URL = "https://jira.rakuten-it.com/jira/browse/"
    DATETIME_FORMAT = "%Y-%m-%d %H:%M"
    
    MONDAY_WEDNESDAY_TEMPLATE = 'monday_wednesday_report_template.html'
    FRIDAY_TEMPLATE = 'friday_report_template.html'
    
    TEMPLATE_NOT_FOUND = "Template file not found."
    TEMPLATE_EMPTY = "Template file is empty."
    NO_TICKETS_MESSAGE = "No pending tickets, thanks for your support."
    ERROR_GENERATING_ROWS = "Error generating ticket rows."


class TicketType(Enum):
    """Ticket type enumeration."""
    WAITING_CSDD = "waiting_csdd"
    UNRESOLVED = "unresolved"
    PAST_DEADLINE = "past_deadline"


class NotificationType(Enum):
    """Notification type enumeration."""
    MONDAY_WEDNESDAY = "Monday/Wednesday"
    FRIDAY = "Friday"


@dataclass
class TicketData:
    """Structured ticket data for rendering."""
    ticket_id: str
    ticket_link: str
    status: str
    row_style: str
    
    developer: Optional[str] = None
    comment_date: Optional[str] = None
    developer_comment: Optional[str] = None
    
    priority: Optional[str] = None
    fix_deadline: Optional[str] = None
    fix_deadline_ago: Optional[str] = None
    resolution: Optional[str] = None

class TemplateError(Exception):
    """Custom exception for template-related errors."""
    pass


class TemplateManager:
    """Handles template loading and validation."""
    
    @staticmethod
    def load_template(template_name: str) -> str:
        """
        Load HTML template from file.
        
        Args:
            template_name: Name of the template file
            
        Returns:
            Template content as string
            
        Raises:
            TemplateError: If template cannot be loaded or is empty
        """
        template_path = os.path.join(
            os.path.dirname(__file__), '..', 'templates', template_name
        )
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if not content.strip():
                log.warning(f"Template file is empty: {template_path}")
                raise TemplateError(Constants.TEMPLATE_EMPTY)
                
            return content
            
        except FileNotFoundError:
            log.error(f"Template file not found: {template_path}")
            raise TemplateError(Constants.TEMPLATE_NOT_FOUND)
        except Exception as e:
            log.error(f"Unexpected error loading template {template_path}: {str(e)}")
            raise TemplateError(Constants.TEMPLATE_NOT_FOUND)
    
    @staticmethod
    def validate_placeholders(template_content: str, required_placeholders: List[str]) -> None:
        """
        Validate that template contains all required placeholders.
        
        Args:
            template_content: Template content to validate
            required_placeholders: List of required placeholder names
            
        Raises:
            TemplateError: If required placeholders are missing
        """
        missing_placeholders = []
        
        for placeholder in required_placeholders:
            pattern = r'\{\{' + re.escape(placeholder) + r'\}\}'
            if not re.search(pattern, template_content):
                missing_placeholders.append(placeholder)
        
        if missing_placeholders:
            log.warning(f"Template missing required placeholders: {missing_placeholders}")
            raise TemplateError(f"Missing placeholders: {missing_placeholders}")
    
    @classmethod
    def load_and_validate_template(cls, template_name: str, required_placeholders: List[str]) -> str:
        """
        Load and validate template in one operation.
        
        Args:
            template_name: Name of template file
            required_placeholders: List of required placeholders
            
        Returns:
            Validated template content
            
        Raises:
            TemplateError: If template loading or validation fails
        """
        template_content = cls.load_template(template_name)
        cls.validate_placeholders(template_content, required_placeholders)
        return template_content


class TicketFilter:
    """Handles ticket filtering and categorization."""
    
    @staticmethod
    def filter_by_criteria(tickets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Filter tickets into categories based on their properties.
        
        Args:
            tickets: List of ticket dictionaries
            
        Returns:
            Dictionary with categorized ticket lists
        """
        return {
            'waiting_csdd_reply': [
                t for t in tickets 
                if t.get('Frequency') == 'Scheduled (M,W) Notification'
            ],
            'unresolved_tickets': [
                t for t in tickets 
                if (t.get('Frequency') == 'Weekly Report Notification' 
                    and t.get('Status') in ['Reopened', 'Open', 'In Progress'])
            ],
            'past_deadline_tickets': [
                t for t in tickets 
                if t.get('Status') == 'Resolved'
            ]
        }


class DataTransformer:
    """Transforms raw ticket data for rendering."""
    
    @staticmethod
    def safe_str_conversion(value: Any, default: str = "N/A") -> str:
        """Safely convert any value to string with fallback."""
        return str(value) if value else default
    
    @staticmethod
    def format_datetime(dt: Any) -> str:
        """Format datetime consistently."""
        if isinstance(dt, datetime):
            return dt.strftime(Constants.DATETIME_FORMAT)
        return DataTransformer.safe_str_conversion(dt)
    
    @staticmethod
    def truncate_comment(comment: Any) -> str:
        """Truncate comment to maximum length."""
        if not comment:
            return "No comment"
        
        comment_str = str(comment)
        if len(comment_str) > Constants.COMMENT_MAX_LENGTH:
            return comment_str[:Constants.COMMENT_MAX_LENGTH] + "..."
        return comment_str
    
    @classmethod
    def prepare_ticket_data(cls, ticket: Dict[str, Any], ticket_type: TicketType, index: int) -> TicketData:
        """
        Transform raw ticket data into structured format for rendering.
        
        Args:
            ticket: Raw ticket dictionary
            ticket_type: Type of ticket for rendering
            index: Index for alternating row styles
            
        Returns:
            Structured ticket data
        """

        ticket_id = cls.safe_str_conversion(ticket.get("Ticket"))
        ticket_link = cls._create_ticket_link(ticket_id)
        status = cls.safe_str_conversion(ticket.get("Status"))
        row_style = cls._get_row_style(index)
        
        base_data = TicketData(
            ticket_id=ticket_id,
            ticket_link=ticket_link,
            status=status,
            row_style=row_style
        )
        
        if ticket_type == TicketType.PAST_DEADLINE:
            base_data.priority = cls.safe_str_conversion(ticket.get("Priority"))
            base_data.fix_deadline = cls.format_datetime(ticket.get("FixDeadlineDate"))
            base_data.fix_deadline_ago = cls.safe_str_conversion(ticket.get("FixDeadlineAgo"))
            base_data.resolution = cls.safe_str_conversion(ticket.get("Resolution"))
        else:
            base_data.developer = cls.safe_str_conversion(ticket.get("LastCommentAuthor"))
            base_data.comment_date = cls.format_datetime(ticket.get("LastCommentAt"))
            base_data.developer_comment = cls.truncate_comment(ticket.get("LastComment"))
        
        return base_data
    
    @staticmethod
    def _create_ticket_link(ticket_id: str) -> str:
        """Create HTML link for ticket."""
        if not ticket_id or ticket_id == "N/A":
            return "N/A"
        
        return (
            f'<a href="{Constants.JIRA_BASE_URL}{ticket_id}" '
            f'style="color: #0078d4; text-decoration: none; font-weight: bold;">'
            f'{ticket_id}</a>'
        )
    
    @staticmethod
    def _get_row_style(index: int) -> str:
        """Get alternating row style."""
        return (
            "background-color: #fafafa;" if index % 2 == 0 
            else "background-color: #ffffff;"
        )


class HTMLRenderer:
    """Handles HTML generation for tables and rows."""
    
    STANDARD_ROW_TEMPLATE = '''
        <tr style="{row_style}">
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 10%;">{ticket_link}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 15%;">{status}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 20%; word-wrap: break-word;">{developer}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 15%;">{comment_date}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 40%; word-wrap: break-word; word-break: break-word;"><em>"{developer_comment}"</em></td>
        </tr>
    '''
    
    PAST_DEADLINE_ROW_TEMPLATE = '''
        <tr style="{row_style}">
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 10%;">{ticket_link}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 15%;">{status}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 20%;">{priority}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 20%;">{resolution}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 15%;">{fix_deadline}</td>
            <td style="border: 1px solid #ddd; padding: 10px; vertical-align: top; width: 40%;">{fix_deadline_ago}</td>
        </tr>
    '''
    
    @classmethod
    def render_no_tickets_row(cls) -> str:
        """Render row for when no tickets are available."""
        return (
            f'<tr><td colspan="{Constants.TABLE_COLSPAN}" '
            f'style="border: 1px solid #ddd; padding: 10px; vertical-align: top; color: #ffffff;">'
            f'{Constants.NO_TICKETS_MESSAGE}</td></tr>'
        )
    
    @classmethod
    def render_error_row(cls) -> str:
        """Render row for error cases."""
        return (
            f'<tr><td colspan="{Constants.TABLE_COLSPAN}" '
            f'style="border: 1px solid #ddd; padding: 10px; vertical-align: top;">'
            f'{Constants.ERROR_GENERATING_ROWS}</td></tr>'
        )
    
    @classmethod
    def render_ticket_row(cls, ticket_data: TicketData, ticket_type: TicketType) -> str:
        """
        Render a single ticket row based on type.
        
        Args:
            ticket_data: Structured ticket data
            ticket_type: Type of ticket for appropriate template
            
        Returns:
            HTML string for the row
        """
        if ticket_type == TicketType.PAST_DEADLINE:
            return cls.PAST_DEADLINE_ROW_TEMPLATE.format(
                row_style=ticket_data.row_style,
                ticket_link=ticket_data.ticket_link,
                status=ticket_data.status,
                priority=ticket_data.priority,
                resolution=ticket_data.resolution,
                fix_deadline=ticket_data.fix_deadline,
                fix_deadline_ago=ticket_data.fix_deadline_ago
            ).strip()
        else:
            return cls.STANDARD_ROW_TEMPLATE.format(
                row_style=ticket_data.row_style,
                ticket_link=ticket_data.ticket_link,
                status=ticket_data.status,
                developer=ticket_data.developer,
                comment_date=ticket_data.comment_date,
                developer_comment=ticket_data.developer_comment
            ).strip()
    
    @classmethod
    def generate_table_rows(cls, tickets: List[Dict[str, Any]], ticket_type: TicketType) -> str:
        """
        Generate HTML table rows for a list of tickets.
        
        Args:
            tickets: List of ticket dictionaries
            ticket_type: Type of tickets for appropriate rendering
            
        Returns:
            HTML string containing all rows
        """
        if not tickets:
            return cls.render_no_tickets_row()
        
        try:
            rows = []
            for i, ticket in enumerate(tickets):
                if not isinstance(ticket, dict):
                    log.warning(f"Skipping invalid ticket data at index {i}: {type(ticket)}")
                    continue
                
                ticket_data = DataTransformer.prepare_ticket_data(ticket, ticket_type, i)
                row_html = cls.render_ticket_row(ticket_data, ticket_type)
                rows.append(row_html)
            
            return '\n'.join(rows)
            
        except Exception as e:
            log.error(f"Error generating table rows for {ticket_type.value}: {str(e)}")
            return cls.render_error_row()


class MessageGenerator:
    """Main class for generating notification messages."""
    
    def __init__(self):
        self.template_manager = TemplateManager()
        self.ticket_filter = TicketFilter()
        self.html_renderer = HTMLRenderer()
    
    def _replace_template_placeholders(self, template: str, replacements: Dict[str, str]) -> str:
        """Replace placeholders in template with provided values."""
        content = template
        for placeholder, value in replacements.items():
            content = content.replace(f'{{{{{placeholder}}}}}', value)
        return content
    
    def _generate_message(
        self, 
        auditor: str, 
        tickets: List[Dict[str, Any]], 
        template_name: str,
        required_sections: List[str], 
        notification_type: NotificationType
    ) -> str:
        """
        Unified message generation function.
        
        Args:
            auditor: Auditor's name
            tickets: List of tickets
            template_name: Template file name
            required_sections: Required table sections
            notification_type: Type of notification
            
        Returns:
            Generated HTML message or empty string if failed
        """
        if not tickets:
            log.debug(f"No tickets found for {notification_type.value} notification.")
            return ""
        
        # Prepare required placeholders
        required_placeholders = ['auditor', 'date', 'total_tickets'] + [
            f"{section}_rows" for section in required_sections
        ]
        
        try:
            # Load and validate template
            html_template = self.template_manager.load_and_validate_template(
                template_name, required_placeholders
            )
            
            # Filter tickets by criteria
            categorized_tickets = self.ticket_filter.filter_by_criteria(tickets)
            
            # Generate table rows for each section
            table_rows = {}
            section_to_type_mapping = {
                'waiting_csdd_reply': TicketType.WAITING_CSDD,
                'unresolved_tickets': TicketType.UNRESOLVED,
                'past_deadline_tickets': TicketType.PAST_DEADLINE
            }
            
            for section in required_sections:
                ticket_list = categorized_tickets.get(section, [])
                ticket_type = section_to_type_mapping.get(section, TicketType.WAITING_CSDD)
                table_rows[f"{section}_rows"] = self.html_renderer.generate_table_rows(
                    ticket_list, ticket_type
                )
            
            # Prepare replacements
            current_date = datetime.now().strftime("%B %d, %Y")
            replacements = {
                'auditor': auditor or "Unknown",
                'date': current_date,
                'total_tickets': str(len(tickets)),
                **table_rows
            }
            
            return self._replace_template_placeholders(html_template, replacements)
            
        except TemplateError as e:
            log.error(f"Template error for {notification_type.value} notification: {str(e)}")
            return ""
        except Exception as e:
            log.error(f"Error generating {notification_type.value} message content: {str(e)}")
            return ""
    
    def generate_monday_wednesday_message(self, auditor: str, tickets: List[Dict[str, Any]]) -> str:
        """
        Generate message for Monday/Wednesday notifications.
        
        Args:
            auditor: Auditor's name
            tickets: List of tickets
            
        Returns:
            HTML message content or empty string if failed
        """
        return self._generate_message(
            auditor=auditor,
            tickets=tickets,
            template_name=Constants.MONDAY_WEDNESDAY_TEMPLATE,
            required_sections=['waiting_csdd_reply'],
            notification_type=NotificationType.MONDAY_WEDNESDAY
        )
    
    def generate_friday_message(self, auditor: str, tickets: List[Dict[str, Any]]) -> str:
        """
        Generate message for Friday weekly notifications.
        
        Args:
            auditor: Auditor's name
            tickets: List of tickets
            
        Returns:
            HTML message content or empty string if failed
        """
        return self._generate_message(
            auditor=auditor,
            tickets=tickets,
            template_name=Constants.FRIDAY_TEMPLATE,
            required_sections=['waiting_csdd_reply', 'unresolved_tickets', 'past_deadline_tickets'],
            notification_type=NotificationType.FRIDAY
        )


def generate_message_for_monday_wednesday(auditor: str, tickets: List[Dict[str, Any]]) -> str:
    """Generate Monday/Wednesday message (backward compatibility)."""
    generator = MessageGenerator()
    return generator.generate_monday_wednesday_message(auditor, tickets)


def generate_message_for_friday(auditor: str, tickets: List[Dict[str, Any]]) -> str:
    """Generate Friday message (backward compatibility)."""
    generator = MessageGenerator()
    return generator.generate_friday_message(auditor, tickets)


