import pandas as pd
from pydomo import Domo
from app.utils.logger import log


class ExtractDomoDataset:

    def __init__(self, domo: Domo, main_dataset_id: str, active_auditor_list_dataset_id: str):
        self.domo = domo
        self.main_dataset_id = main_dataset_id
        self.active_auditor_list_dataset_id = active_auditor_list_dataset_id

    def get_raw_dataset(self) -> pd.DataFrame:
        '''Extract the raw dataset from DOMO'''

        try:

            main_dataset = self.domo.ds_get(self.main_dataset_id)

            if main_dataset is not None and not main_dataset.empty:
                log.debug(f"Successfully extracted main dataset with {len(main_dataset)} rows")

                return main_dataset
            else:
                log.warning(f"Main dataset is empty or not found")

        except Exception as e:
            log.error(f'Error in extracting data from DOMO | message: {e} | dataset_id: {self.main_dataset_id}')

    def get_active_auditor_list(self) -> list[str]:
        '''Extract the active auditor list from DOMO'''

        try:
            main_dataset = self.get_raw_dataset()
            auditor_active_list = self.domo.ds_get(self.active_auditor_list_dataset_id)

            if auditor_active_list is not None and not auditor_active_list.empty:
                auditor_active_list = auditor_active_list[
                    (auditor_active_list['is_active'] == 1) & 
                    (auditor_active_list['audit_assignment_rate'] == 1)
                ]
                active_auditor_list = auditor_active_list['long_account'].to_list()
                filter_active_auditors = main_dataset[main_dataset['assignee_name'].isin(active_auditor_list)]
                auditor_list = (filter_active_auditors['assignee_name'].unique()).tolist()
                
                auditor_list.extend(['sv-jira-ocz-bot', 'karthik.rao', 'hanae.kawagoe', 'wenping.chi', 'yulo.su'])
                
                log.debug(f"Successfully extracted auditor active list with {len(auditor_active_list)} rows")

                return auditor_list
            else:
                log.warning(f"Auditor active list is empty or not found")

        except Exception as e:
            log.error(f'Error in extracting active auditor list from DOMO | message: {e} | dataset_id: {self.active_auditor_list_dataset_id}')