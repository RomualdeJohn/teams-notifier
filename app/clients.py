from jira import JIRA
from pydomo import Domo
from app.utils.logger import log


def jira_client(jira_url: str, username: str, password: str) -> JIRA:
    """Create a JIRA client."""
    try:
        jira_client = JIRA(options={'server': jira_url}, basic_auth=(username, password))

        return jira_client

    except Exception as e:
        log.error(f"Error creating Jira client: {e}")
        raise e

def domo_client(client_id: str, client_secret: str, api_host: str) -> Domo:
    """Create a Domo client."""
    try:

        domo_client = Domo(client_id=client_id, client_secret=client_secret, api_host=api_host)
        return domo_client

    except Exception as e:
        log.error(f"Error creating Domo client: {e}")
        raise e



