"""Email action routing using LLM."""
import json
import logging
import re
from typing import Dict, Any

import vertexai
from vertexai.generative_models import GenerativeModel
from config import config

logger = logging.getLogger(__name__)


class EmailRouter:
    """Routes incoming emails to appropriate actions using LLM."""

    # Available actions and their descriptions
    ACTIONS = {
        'GENERATE_MEMOS': {
            'description': 'Generate investment memos for new companies in the sheet'
        },
        'ADD_COMPANY': {
            'description': 'Add a new company to the deal flow spreadsheet. Extract company name and domain from the email.'
        },
        'UPDATE_COMPANY': {
            'description': 'Update/correct a company\'s domain or name. Use when someone provides a correction like "Domain is X" or "Actually the domain is X".'
        },
        'REGENERATE_MEMO': {
            'description': 'Regenerate an investment memo for a specific company. Use when a memo needs to be redone.'
        },
        'ANALYZE_THREAD': {
            'description': 'Analyze a forwarded email thread to create a relationship timeline and summary. Use when email contains forwarded messages.'
        },
        'SUMMARIZE_UPDATES': {
            'description': 'Summarize update emails from a company. Use when asked "how is [company] doing?" or "summarize updates from [company]".'
        },
        'SCRAPE_YC': {
            'description': 'Scrape YC Bookface for companies in a specific batch and add them to the sheet. Default batch is W26.'
        },
        'HEALTH_CHECK': {
            'description': 'Check if the service is running properly'
        },
        'NONE': {
            'description': 'No action needed - not a valid command or unclear request'
        }
    }

    def __init__(self):
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

    def decide(self, email_data: Dict[str, str]) -> Dict[str, Any]:
        """Decide what action to take based on email content.

        Args:
            email_data: Dict with 'from', 'subject', 'body'

        Returns:
            Dict with 'action', 'reasoning', 'parameters', optionally 'also_do'
        """
        action_descriptions = '\n'.join(
            f"- {key}: {val['description']}"
            for key, val in self.ACTIONS.items()
        )

        prompt = f"""You are Keel, an AI assistant that processes emails and takes actions for a venture capital firm.

Available actions:
{action_descriptions}

Email:
From: {email_data.get('from', 'Unknown')}
Subject: {email_data.get('subject', 'No subject')}
Body:
{email_data.get('body', '')[:3000]}

CRITICAL: Analyze the ENTIRE email thread carefully. The email may contain:
1. Previous Keel responses (marked with ✓, **Company:**, **Domain:**, etc.)
2. User replies that CORRECT or UPDATE information
3. New commands to execute

Respond with JSON only (no markdown):
{{
  "action": "ACTION_NAME",
  "reasoning": "Brief explanation",
  "parameters": {{}},
  "also_do": null  // Optional: second action to perform after the first
}}

**HIGHEST PRIORITY - DETECTING CORRECTIONS:**
If the user provides a correction or update to information Keel previously processed, you MUST use UPDATE_COMPANY.

Correction patterns to look for:
- "Domain is https://..." or "Domain: https://..."
- "Actually the domain is..." or "Correct domain is..."
- "The website is..." or "Their site is..."
- A URL appearing right after Keel's "Company added" or "Domain:" response

**UPDATE_COMPANY:**
- Parameters: {{"company": "Company Name", "new_domain": "correct.com"}}

**ADD_COMPANY:**
- Use ONLY for adding NEW companies
- Parameters: {{"company": "Company Name", "domain": "example.com"}}
- CRITICAL: Extract company name from the MAIN body text, NOT from email signatures

**GENERATE_MEMOS:**
- Parameters: {{"force": false}} (default) or {{"force": true}} for regenerating all

**REGENERATE_MEMO:**
- Parameters: {{"domain": "example.com"}} or {{"domain": "Company Name"}}

**ANALYZE_THREAD:**
- Use for FORWARDED email threads (look for "Forwarded message", multiple From:/Date: headers)
- No parameters needed

**SUMMARIZE_UPDATES:**
- Parameters: {{"company": "Company Name", "domain": "optional.domain.com"}}

**SCRAPE_YC:**
- Parameters: {{"batch": "W26", "pages": 3}}

**HEALTH_CHECK:**
- Use for: "status", "health", "check"

**NONE:**
- Use when the request is unclear or ambiguous

Be helpful. When in doubt, check the thread for context."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 500,
                    "temperature": 0.1,
                }
            )

            content = response.text.strip()
            if content.startswith('```'):
                content = re.sub(r'```json?\n?', '', content)
                content = re.sub(r'```', '', content)
                content = content.strip()

            return json.loads(content)

        except Exception as e:
            logger.error(f"Error getting LLM decision: {e}", exc_info=True)
            return {
                'action': 'NONE',
                'reasoning': 'I had trouble understanding that request.',
                'parameters': {}
            }
