#!/usr/bin/env python3
from __future__ import annotations

import sys
from configparser import ConfigParser
from collections import defaultdict
from datetime import date
from pathlib import Path
from time import sleep
from typing import Dict, List, Tuple, Callable, Optional
from dataclasses import dataclass
from enum import Enum

import pandas as pd
from jira import JIRA
from pydomo import Domo

from app.utils.generate_message import (
    generate_message_for_friday, 
    generate_message_for_monday_wednesday
)
from app.services.notification.send_via_graph_api import SendNotificationViaGraphAPI, ChatType
from app.services.notification.send_via_power_automate import SendNotificationViaWebhook
from app.services.data.extract import ExtractDomoDataset
from app.services.auth.get_token import GetUserToken
from app.process_ticket import TicketProcessor
from app import clients
from app.utils.logger import log


class NotificationDay(Enum):
    """Enumeration for notification days."""
    MONDAY = "monday"
    WEDNESDAY = "wednesday" 
    FRIDAY = "friday"


@dataclass(frozen=True)
class AppConstants:
    FREQUENCY_VALUE_FOR_MW: str = 'Scheduled (M,W) Notification'
    RECURRING_REPORT_DAYS: List[str] = None
    WEEKLY_REPORT_DAY: str = NotificationDay.FRIDAY.value
    DEFAULT_SLEEP_INTERVAL: int = 2
    CONFIG_FILE_PATH: str = 'config.ini'
    
    def __post_init__(self):
        object.__setattr__(
            self, 
            'RECURRING_REPORT_DAYS', 
            [NotificationDay.MONDAY.value, NotificationDay.WEDNESDAY.value]
        )


class ConfigurationManager:
    def __init__(self, config_path: str = AppConstants.CONFIG_FILE_PATH):
        self.config_path = Path(config_path)
        self._config: Optional[ConfigParser] = None
    
    @property
    def config(self) -> ConfigParser:
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> ConfigParser:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        config = ConfigParser(interpolation=None)
        config.read(self.config_path)
        return config
    
    def get_section(self, section: str) -> dict:
        if section not in self.config:
            raise KeyError(f"Configuration section '{section}' not found")
        return dict(self.config[section])


class ClientManager:
    def __init__(self, config_manager: ConfigurationManager):
        self.config_manager = config_manager
        self._jira_client: Optional[JIRA] = None
        self._domo_client: Optional[Domo] = None
    
    @property
    def jira_client(self) -> JIRA:
        if self._jira_client is None:
            jira_config = self.config_manager.get_section('JIRA')
            self._jira_client = clients.jira_client(
                jira_url=jira_config['jira_url'],
                username=jira_config['jira_username'],
                password=jira_config['jira_password']
            )
        return self._jira_client
    
    @property
    def domo_client(self) -> Domo:
        if self._domo_client is None:
            domo_config = self.config_manager.get_section('DOMO')
            self._domo_client = clients.domo_client(
                client_id=domo_config['client_id'],
                client_secret=domo_config['client_secret'],
                api_host=domo_config['api_url']
            )
        return self._domo_client


class DataManager:
    def __init__(self, client_manager: ClientManager, config_manager: ConfigurationManager):
        self.client_manager = client_manager
        self.config_manager = config_manager
    
    def upload_to_domo(self, df: pd.DataFrame, dataset_id: str) -> pd.DataFrame:
        try:
            upload_result = self.client_manager.domo_client.ds_update(dataset_id, df)
            return upload_result
        except Exception as e:
            log.error(f"Failed to upload data to DOMO dataset {dataset_id}: {e}")
            raise
    
    def group_tickets_by_auditor(self, tickets_list: List[dict]) -> Dict[Tuple[str, str], List[dict]]:
        grouped_tickets = defaultdict(list) 
        for ticket in tickets_list:
            auditor = ticket.get('Auditor')
            email = ticket.get('Email')
            
            if auditor and email:
                key = (auditor, email)
                grouped_tickets[key].append(ticket)
            else:
                log.warning(f"Ticket missing auditor or email information: {ticket}")     
        return grouped_tickets


class NotificationManager:
    def __init__(self, config_manager: ConfigurationManager, constants: AppConstants):
        self.config_manager = config_manager
        self.constants = constants
    
    def get_tickets_for_day(self, tickets_list: List[dict], day: str) -> List[dict]:
        if day in self.constants.RECURRING_REPORT_DAYS:
            filtered_tickets = [
                ticket for ticket in tickets_list 
                if ticket.get('Frequency') == self.constants.FREQUENCY_VALUE_FOR_MW
            ]
        elif day == self.constants.WEEKLY_REPORT_DAY:
            filtered_tickets = tickets_list
        else:
            filtered_tickets = []
        
        log.debug(f"Filtered {len(filtered_tickets)} tickets for {day}")
        return filtered_tickets
    
    def send_webhook_notification(
        self, 
        auditor: str, 
        auditor_email: str, 
        tickets: List[dict], 
        message_generator: Callable,
    ) -> bool:
        
        log.debug(f'Sending webhook notification to {auditor} | {auditor_email} for {len(tickets)} tickets')
        
        try:
            message = message_generator(auditor, tickets)
            sender = SendNotificationViaWebhook(
                content=message,
                auditor=auditor,
                user_email=auditor_email,
                config=self.config_manager.config
            )
            
            success = sender.send_notification()
            
            if success:
                log.info(f"Successfully sent notification to {auditor} | {auditor_email}")
            else:
                log.warning(f"Failed to send notification to {auditor} | {auditor_email}")
            
            return success
            
        except Exception as e:
            log.error(f"Error sending notification to {auditor}: {e}")
            return False
    
    def send_graph_api_notification(
        self,
        auditor: str,
        auditor_email: str,
        tickets: List[dict],
        message_generator: Callable,
        token: str
    ) -> bool:

        log.debug(f'Sending Graph API notification to {auditor} for {len(tickets)} tickets')
        
        try:
            sender = SendNotificationViaGraphAPI(
                user_email=auditor_email,
                message=message_generator(auditor, tickets),
                token=token,
                config=self.config_manager.config,
                topic=f"OCZ Testing {auditor}",
                chat_type=ChatType.GROUP,
                additional_members=[]
            )
            
            success = sender.send_notification()
            
            if success:
                log.info(f"Successfully sent Graph API notification to {auditor}")
            else:
                log.warning(f"Failed to send Graph API notification to {auditor}")
            
            return success
            
        except Exception as e:
            log.error(f"Error sending Graph API notification to {auditor}: {e}")
            return False
    
    def process_notifications(self, grouped_tickets: Dict[Tuple[str, str], List[dict]]) -> None:

        today = date.today().strftime('%A').lower()
        
        all_notification_days = self.constants.RECURRING_REPORT_DAYS + [self.constants.WEEKLY_REPORT_DAY]
        if today not in all_notification_days:
            log.info(f"No notifications scheduled for {today}")
            return
        
        message_generators = {
            **{day: generate_message_for_monday_wednesday for day in self.constants.RECURRING_REPORT_DAYS},
            self.constants.WEEKLY_REPORT_DAY: generate_message_for_friday,
        }
        
        message_generator = message_generators.get(today)
        if not message_generator:
            log.error(f"No message generator found for {today}")
            return
        
        successful_notifications = 0
        total_auditors = len(grouped_tickets)
        
        for (auditor, auditor_email), tickets_list in grouped_tickets.items():
            tickets_for_today = self.get_tickets_for_day(tickets_list, today)
            
            if not tickets_for_today:
                log.debug(f"No tickets to notify for {auditor} on {today}")
                continue
            
            try:
                success = self.send_webhook_notification(
                    auditor=auditor,
                    auditor_email=auditor_email,
                    tickets=tickets_for_today,
                    message_generator=message_generator
                )
                
                if success:
                    successful_notifications += 1
                
                sleep(self.constants.DEFAULT_SLEEP_INTERVAL)
                
            except Exception as e:
                log.error(f"Unexpected error processing notifications for {auditor}: {e}")
        
        log.info(f"Sent {successful_notifications}/{total_auditors} notifications successfully")


class TeamsNotifier:
    def __init__(self, config_path: str = AppConstants.CONFIG_FILE_PATH):
        self.constants = AppConstants()
        self.config_manager = ConfigurationManager(config_path)
        self.client_manager = ClientManager(self.config_manager)
        self.data_manager = DataManager(self.client_manager, self.config_manager)
        self.notification_manager = NotificationManager(self.config_manager, self.constants)
    
    def run(self) -> None:
        try:
            log.info("Starting Teams Notifier application")
            
            domo_config = self.config_manager.get_section('DOMO')
            dataset_extractor = ExtractDomoDataset(
                domo=self.client_manager.domo_client,
                main_dataset_id=domo_config['main_dataset_id'],
                active_auditor_list_dataset_id=domo_config['active_auditor_dataset_id']
            )
            
            active_auditors = dataset_extractor.get_active_auditor_list()
            
            # Process tickets
            ticket_processor = TicketProcessor(
                jira_client=self.client_manager.jira_client,
                active_auditor_list=active_auditors,
                config=self.config_manager.config
            )
            
            tickets_for_domo, tickets_needing_response, tickets_past_deadline = (
                ticket_processor.process_all_tickets()
            )
            
            # Combine all tickets requiring notifications
            all_notification_tickets = tickets_needing_response + tickets_past_deadline
            
            # Group tickets by auditor
            grouped_tickets = self.data_manager.group_tickets_by_auditor(all_notification_tickets)
            
            # Send notifications
            self.notification_manager.process_notifications(grouped_tickets)
            
            # Upload data to DOMO
            if tickets_for_domo:
                df = pd.DataFrame(tickets_for_domo)
                self.data_manager.upload_to_domo(df, domo_config['ocz_dataset_id'])
            else:
                log.info("No tickets to upload to DOMO")
            
            log.info("Teams Notifier application completed successfully")
            
        except Exception as e:
            log.error(f"Application failed with error: {e}")
            raise


def main() -> None:
    app = TeamsNotifier()
    app.run()



if __name__ == "__main__":
    main()
