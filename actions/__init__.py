"""Email command action handlers."""
from actions.base import BaseAction
from actions.add_company import AddCompanyAction
from actions.update_company import UpdateCompanyAction
from actions.generate_memos import GenerateMemosAction
from actions.regenerate_memo import RegenerateMemoAction
from actions.analyze_thread import AnalyzeThreadAction
from actions.summarize_updates import SummarizeUpdatesAction
from actions.scrape_yc import ScrapeYCAction
from actions.health_check import HealthCheckAction

__all__ = [
    'BaseAction',
    'AddCompanyAction',
    'UpdateCompanyAction',
    'GenerateMemosAction',
    'RegenerateMemoAction',
    'AnalyzeThreadAction',
    'SummarizeUpdatesAction',
    'ScrapeYCAction',
    'HealthCheckAction',
]

# Action registry for easy lookup
ACTION_REGISTRY = {
    'ADD_COMPANY': AddCompanyAction,
    'UPDATE_COMPANY': UpdateCompanyAction,
    'GENERATE_MEMOS': GenerateMemosAction,
    'REGENERATE_MEMO': RegenerateMemoAction,
    'ANALYZE_THREAD': AnalyzeThreadAction,
    'SUMMARIZE_UPDATES': SummarizeUpdatesAction,
    'SCRAPE_YC': ScrapeYCAction,
    'HEALTH_CHECK': HealthCheckAction,
}
