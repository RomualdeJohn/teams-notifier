from configparser import ConfigParser
from msal import ConfidentialClientApplication
from app.utils.logger import log

class GetUserToken:
    def __init__(self, config: ConfigParser):
        self.config = config
        self.authority = f"{self.config['MS_GRAPH_API']['authority']}{self.config['MS_GRAPH_API']['tenant_id']}"
        self.scope = self.config['MS_GRAPH_API']['scope'].split()

    def get_user_token(self) -> str:
        """
        This function is used to authenticate the user using the delegated permission flow.
        It uses the username and password to authenticate the user.

        Returns: 
            str: The access token for the user.
        """

        username = self.config['MS_GRAPH_API']['username']
        password = self.config['MS_GRAPH_API']['password']
        
        try:
            app = ConfidentialClientApplication(
                client_id=self.config['MS_GRAPH_API']['client_id'],
                authority=self.authority,
                client_credential=self.config['MS_GRAPH_API']['client_secret'],
            )
            
            result = app.acquire_token_by_username_password(
                username=username,
                password=password,
                scopes=self.scope
            )
            
            log.debug(f"Authentication successful for user: {username} | Token provided.")
            return result["access_token"]

        except Exception as e:
            log.error(f"Error in authentication process for user: {username} | Message: {e}")
            return None