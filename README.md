# teams-notifier

A scheduled notification bot that monitors Jira tickets and sends reminders to auditors via Microsoft Teams. Built to reduce follow-up overhead during security audit cycles.

## What it does

The bot runs on a schedule (Mon/Wed/Fri) and checks two things:

1. **Developer response check** — finds open tickets where the last comment was left by a developer (not an auditor) and no response has been given in 3+ days
2. **Fix deadline check** — finds tickets that have gone 14+ days past their scheduled fix date without resolution

When either condition is met, it sends a formatted Teams message directly to the responsible auditor. It also syncs ticket data to a Domo dataset for reporting.

## Stack

- Python 3.12
- Jira Python SDK — ticket queries
- Microsoft Graph API — sends Teams messages (creates/reuses group chats per auditor)
- Power Automate webhooks — fallback notification path
- Domo SDK — uploads processed ticket data for dashboards
- Docker + Kubernetes — deployed as a scheduled job

## Configuration

The app reads from a `config.ini` file at runtime. You'll need sections for:

```ini
[JIRA]
jira_url =
jira_username =
jira_password =

[DOMO]
client_id =
client_secret =
api_url =
main_dataset_id =
active_auditor_dataset_id =
ocz_dataset_id =

[MS_GRAPH_API]
graph_api_endpoint =

[JQL]
jql_for_dev_check =
jql_for_fix_deadline_check =
```

## Running locally

```bash
pip install -r requirements.txt
python main.py
```

## Running with Docker

```bash
docker build -t teams-notifier .
docker run --rm -v $(pwd)/config.ini:/usr/src/sagt-teams-notification/config.ini teams-notifier
```

## Notification schedule

| Day | Behavior |
|---|---|
| Monday / Wednesday | Sends only to auditors with tickets marked for recurring follow-up |
| Friday | Sends to all auditors with pending tickets |
| Other days | No-op |

## Tests

```bash
pytest --cov=app test/
```

Please contact me if you have questions in my linkedin account https://www.linkedin.com/in/romualdebaoy/