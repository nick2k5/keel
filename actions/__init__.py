"""Email command action handlers."""
from typing import Dict

from actions.base import BaseAction
from actions.add_company import AddCompanyAction
from actions.update_company import UpdateCompanyAction
from actions.generate_memos import GenerateMemosAction
from actions.regenerate_memo import RegenerateMemoAction
from actions.analyze_thread import AnalyzeThreadAction
from actions.summarize_updates import SummarizeUpdatesAction
from actions.scrape_yc import ScrapeYCAction
from actions.health_check import HealthCheckAction
from actions.answer_question import AnswerQuestionAction

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
    'AnswerQuestionAction',
    'ACTION_REGISTRY',
    'get_action_descriptions',
]

# Action registry for easy lookup - single source of truth
ACTION_REGISTRY = {
    'ADD_COMPANY': AddCompanyAction,
    'UPDATE_COMPANY': UpdateCompanyAction,
    'GENERATE_MEMOS': GenerateMemosAction,
    'REGENERATE_MEMO': RegenerateMemoAction,
    'ANALYZE_THREAD': AnalyzeThreadAction,
    'SUMMARIZE_UPDATES': SummarizeUpdatesAction,
    'SCRAPE_YC': ScrapeYCAction,
    'HEALTH_CHECK': HealthCheckAction,
    'ANSWER_QUESTION': AnswerQuestionAction,
}


def get_action_descriptions() -> Dict[str, Dict[str, str]]:
    """Get action descriptions for LLM routing.

    Returns:
        Dict mapping action name to dict with 'description' key
    """
    descriptions = {
        name: {'description': cls.description}
        for name, cls in ACTION_REGISTRY.items()
    }
    # Add NONE action for when no action is needed
    descriptions['NONE'] = {'description': 'No action needed - not a valid command or unclear request'}
    return descriptions
