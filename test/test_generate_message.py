import unittest
from unittest.mock import patch
from datetime import datetime

from app.utils.generate_message import (
    Constants,
    TicketType,
    NotificationType,
    TicketData,
    TemplateManager,
    TicketFilter,
    DataTransformer,
    HTMLRenderer,
    MessageGenerator,
)


class TestTicketData(unittest.TestCase):
    
    def test_ticket_data_creation(self):
        """Test TicketData creation with required fields."""
        ticket_data = TicketData(
            ticket_id="TEST-123",
            ticket_link="<a href='...'>TEST-123</a>",
            status="Open",
            row_style="background-color: #fafafa;"
        )
        
        self.assertEqual(ticket_data.ticket_id, "TEST-123")
        self.assertEqual(ticket_data.ticket_link, "<a href='...'>TEST-123</a>")
        self.assertEqual(ticket_data.status, "Open")
        self.assertEqual(ticket_data.row_style, "background-color: #fafafa;")
        
        # Test optional fields default to None
        self.assertIsNone(ticket_data.developer)
        self.assertIsNone(ticket_data.comment_date)
        self.assertIsNone(ticket_data.developer_comment)
        self.assertIsNone(ticket_data.priority)
        self.assertIsNone(ticket_data.fix_deadline)
        self.assertIsNone(ticket_data.fix_deadline_ago)
        self.assertIsNone(ticket_data.resolution)


class TestTicketFilter(unittest.TestCase):
    
    def setUp(self):
        self.ticket_filter = TicketFilter()
        self.sample_tickets = [
            {
                'Ticket': 'TEST-001',
                'Frequency': 'Scheduled (M,W) Notification',
                'Status': 'Open'
            },
            {
                'Ticket': 'TEST-002',
                'Frequency': 'Weekly Report Notification',
                'Status': 'Open'
            },
            {
                'Ticket': 'TEST-003',
                'Frequency': 'Weekly Report Notification',
                'Status': 'Resolved'
            },
            {
                'Ticket': 'TEST-004',
                'Frequency': 'Scheduled (M,W) Notification',
                'Status': 'Closed'
            }
        ]
    
    def test_filter_by_criteria(self):
        """Test ticket filtering by criteria."""
        result = self.ticket_filter.filter_by_criteria(self.sample_tickets)
        
        self.assertIn('waiting_csdd_reply', result)
        self.assertIn('unresolved_tickets', result)
        self.assertIn('past_deadline_tickets', result)
        
        waiting_tickets = result['waiting_csdd_reply']
        self.assertEqual(len(waiting_tickets), 2)
        self.assertEqual(waiting_tickets[0]['Ticket'], 'TEST-001')
        self.assertEqual(waiting_tickets[1]['Ticket'], 'TEST-004')
        
        unresolved_tickets = result['unresolved_tickets']
        self.assertEqual(len(unresolved_tickets), 1)
        self.assertEqual(unresolved_tickets[0]['Ticket'], 'TEST-002')
        
        past_deadline_tickets = result['past_deadline_tickets']
        self.assertEqual(len(past_deadline_tickets), 1)
        self.assertEqual(past_deadline_tickets[0]['Ticket'], 'TEST-003')


class TestDataTransformer(unittest.TestCase):
    
    def setUp(self):
        self.transformer = DataTransformer()
    
    def test_safe_str_conversion(self):
        """Test safe string conversion."""
        self.assertEqual(self.transformer.safe_str_conversion("test"), "test")
        self.assertEqual(self.transformer.safe_str_conversion(123), "123")
        self.assertEqual(self.transformer.safe_str_conversion(None), "N/A")
        self.assertEqual(self.transformer.safe_str_conversion(""), "N/A")
        self.assertEqual(self.transformer.safe_str_conversion(False), "N/A") 
        self.assertEqual(self.transformer.safe_str_conversion(0), "N/A") 
        self.assertEqual(self.transformer.safe_str_conversion(True), "True") 
        self.assertEqual(self.transformer.safe_str_conversion(1), "1") 
        
        self.assertEqual(self.transformer.safe_str_conversion(None, "Custom"), "Custom")
    
    def test_format_datetime(self):
        """Test datetime formatting."""
        dt = datetime(2024, 1, 15, 10, 30)
        result = self.transformer.format_datetime(dt)
        self.assertEqual(result, "2024-01-15 10:30")
        
        result = self.transformer.format_datetime("2024-01-15")
        self.assertEqual(result, "2024-01-15")
        
        result = self.transformer.format_datetime(None)
        self.assertEqual(result, "N/A")
        
        result = self.transformer.format_datetime("")
        self.assertEqual(result, "N/A")
    
    def test_prepare_ticket_data_waiting_csdd(self):
        """Test ticket data preparation for waiting CSDD tickets."""
        ticket = {
            "Ticket": "TEST-123",
            "Status": "Open",
            "LastCommentAuthor": "John Doe",
            "LastCommentAt": datetime(2024, 1, 15, 10, 30),
            "LastComment": "This is a test comment"
        }
        
        result = self.transformer.prepare_ticket_data(ticket, TicketType.WAITING_CSDD, 0)
        
        self.assertEqual(result.ticket_id, "TEST-123")
        self.assertIn("TEST-123", result.ticket_link)
        self.assertEqual(result.status, "Open")
        self.assertEqual(result.row_style, "background-color: #fafafa;")
        self.assertEqual(result.developer, "John Doe")
        self.assertEqual(result.comment_date, "2024-01-15 10:30")
        self.assertEqual(result.developer_comment, "This is a test comment")
        
        self.assertIsNone(result.priority)
        self.assertIsNone(result.fix_deadline)
        self.assertIsNone(result.fix_deadline_ago)
        self.assertIsNone(result.resolution)
    
    def test_prepare_ticket_data_past_deadline(self):
        """Test ticket data preparation for past deadline tickets."""
        ticket = {
            "Ticket": "TEST-456",
            "Status": "Resolved",
            "Priority": "High",
            "FixDeadlineDate": datetime(2024, 1, 10, 9, 0),
            "FixDeadlineAgo": "5 days ago",
            "Resolution": "Fixed"
        }
        
        result = self.transformer.prepare_ticket_data(ticket, TicketType.PAST_DEADLINE, 1)
        
        self.assertEqual(result.ticket_id, "TEST-456")
        self.assertEqual(result.status, "Resolved")
        self.assertEqual(result.row_style, "background-color: #ffffff;")
        self.assertEqual(result.priority, "High")
        self.assertEqual(result.fix_deadline, "2024-01-10 09:00")
        self.assertEqual(result.fix_deadline_ago, "5 days ago")
        self.assertEqual(result.resolution, "Fixed")
        
        self.assertIsNone(result.developer)
        self.assertIsNone(result.comment_date)
        self.assertIsNone(result.developer_comment)


class TestHTMLRenderer(unittest.TestCase):
    
    def setUp(self):
        self.renderer = HTMLRenderer()
        self.sample_ticket_data = TicketData(
            ticket_id="TEST-123",
            ticket_link='<a href="...">TEST-123</a>',
            status="Open",
            row_style="background-color: #fafafa;",
            developer="John Doe",
            comment_date="2024-01-15 10:30",
            developer_comment="Test comment"
        )
        self.sample_past_deadline_data = TicketData(
            ticket_id="TEST-456",
            ticket_link='<a href="...">TEST-456</a>',
            status="Resolved",
            row_style="background-color: #ffffff;",
            priority="High",
            fix_deadline="2024-01-10 09:00",
            fix_deadline_ago="5 days ago",
            resolution="Fixed"
        )
    
    
    def test_render_ticket_row_standard(self):
        """Test rendering standard ticket row."""
        result = self.renderer.render_ticket_row(self.sample_ticket_data, TicketType.WAITING_CSDD)
        
        self.assertIn("TEST-123", result)
        self.assertIn("Open", result)
        self.assertIn("John Doe", result)
        self.assertIn("2024-01-15 10:30", result)
        self.assertIn("Test comment", result)
        self.assertIn("background-color: #fafafa;", result)
        self.assertIn('<tr', result)
        self.assertIn('</tr>', result)
    
    def test_render_ticket_row_past_deadline(self):
        """Test rendering past deadline ticket row."""
        result = self.renderer.render_ticket_row(self.sample_past_deadline_data, TicketType.PAST_DEADLINE)
        
        self.assertIn("TEST-456", result)
        self.assertIn("Resolved", result)
        self.assertIn("High", result)
        self.assertIn("2024-01-10 09:00", result)
        self.assertIn("5 days ago", result)
        self.assertIn("Fixed", result)
        self.assertIn("background-color: #ffffff;", result)
        self.assertIn('<tr', result)
        self.assertIn('</tr>', result)
    
    def test_generate_table_rows_valid_tickets(self):
        """Test generating table rows with valid tickets."""
        tickets = [
            {
                "Ticket": "TEST-001",
                "Status": "Open",
                "LastCommentAuthor": "John Doe",
                "LastCommentAt": "2024-01-15 10:30",
                "LastComment": "Comment 1"
            },
            {
                "Ticket": "TEST-002",
                "Status": "In Progress",
                "LastCommentAuthor": "Jane Smith",
                "LastCommentAt": "2024-01-16 11:00",
                "LastComment": "Comment 2"
            }
        ]
        
        result = self.renderer.generate_table_rows(tickets, TicketType.WAITING_CSDD)
        
        self.assertIn("TEST-001", result)
        self.assertIn("TEST-002", result)
        self.assertIn("John Doe", result)
        self.assertIn("Jane Smith", result)
        self.assertIn("Comment 1", result)
        self.assertIn("Comment 2", result)
        
        self.assertEqual(result.count('<tr'), 2)


class TestMessageGenerator(unittest.TestCase):
    
    def setUp(self):
        self.generator = MessageGenerator()
        self.sample_tickets = [
            {
                'Ticket': 'TEST-001',
                'Frequency': 'Scheduled (M,W) Notification',
                'Status': 'Open',
                'LastCommentAuthor': 'John Doe',
                'LastCommentAt': '2024-01-15 10:30',
                'LastComment': 'Test comment 1'
            },
            {
                'Ticket': 'TEST-002',
                'Frequency': 'Weekly Report Notification',
                'Status': 'In Progress',
                'LastCommentAuthor': 'Jane Smith',
                'LastCommentAt': '2024-01-16 11:00',
                'LastComment': 'Test comment 2'
            }
        ]
    
    @patch.object(TemplateManager, 'load_and_validate_template')
    @patch.object(TicketFilter, 'filter_by_criteria')
    @patch.object(HTMLRenderer, 'generate_table_rows')
    def test_generate_message_success(self, mock_generate_rows, mock_filter, mock_load_template):
        """Test successful message generation."""
        mock_load_template.return_value = "<html>{{auditor}} has {{total_tickets}} tickets. {{waiting_csdd_reply_rows}}</html>"
        mock_filter.return_value = {
            'waiting_csdd_reply': [self.sample_tickets[0]],
            'unresolved_tickets': [],
            'past_deadline_tickets': []
        }
        mock_generate_rows.return_value = "<tr>Test row</tr>"
        
        result = self.generator._generate_message(
            auditor="John Doe",
            tickets=self.sample_tickets,
            template_name="test_template.html",
            required_sections=['waiting_csdd_reply'],
            notification_type=NotificationType.MONDAY_WEDNESDAY
        )
        
        self.assertIn("John Doe", result)
        self.assertIn("2", result)
        self.assertIn("<tr>Test row</tr>", result)
        
        mock_load_template.assert_called_once()
        mock_filter.assert_called_once_with(self.sample_tickets)
        mock_generate_rows.assert_called_once()
    
    @patch.object(MessageGenerator, '_generate_message')
    def test_generate_monday_wednesday_message(self, mock_generate):
        """Test Monday/Wednesday message generation."""
        mock_generate.return_value = "<html>Monday/Wednesday message</html>"
        
        result = self.generator.generate_monday_wednesday_message("John Doe", self.sample_tickets)
        
        self.assertEqual(result, "<html>Monday/Wednesday message</html>")
        mock_generate.assert_called_once_with(
            auditor="John Doe",
            tickets=self.sample_tickets,
            template_name=Constants.MONDAY_WEDNESDAY_TEMPLATE,
            required_sections=['waiting_csdd_reply'],
            notification_type=NotificationType.MONDAY_WEDNESDAY
        )
    
    @patch.object(MessageGenerator, '_generate_message')
    def test_generate_friday_message(self, mock_generate):
        """Test Friday message generation."""
        mock_generate.return_value = "<html>Friday message</html>"
        
        result = self.generator.generate_friday_message("John Doe", self.sample_tickets)
        
        self.assertEqual(result, "<html>Friday message</html>")
        mock_generate.assert_called_once_with(
            auditor="John Doe",
            tickets=self.sample_tickets,
            template_name=Constants.FRIDAY_TEMPLATE,
            required_sections=['waiting_csdd_reply', 'unresolved_tickets', 'past_deadline_tickets'],
            notification_type=NotificationType.FRIDAY
        )


if __name__ == '__main__':
    unittest.main()
