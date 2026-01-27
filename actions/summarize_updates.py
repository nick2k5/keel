"""Summarize updates action."""
import json
import logging
import re
from typing import Dict, Any, Optional, List

import vertexai
from vertexai.generative_models import GenerativeModel

from actions.base import BaseAction
from config import config

logger = logging.getLogger(__name__)


class SummarizeUpdatesAction(BaseAction):
    """Summarize update emails from a company."""

    name = 'SUMMARIZE_UPDATES'
    description = 'Summarize update emails from a company. Use when asked "how is [company] doing?"'

    def __init__(self, services: Dict[str, Any]):
        super().__init__(services)
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        company = parameters.get('company', '')
        domain = parameters.get('domain', '')

        if not company and not domain:
            return {'success': False, 'error': 'Missing company name or domain'}

        gmail = self.services.get('gmail')
        if not gmail:
            return {'success': False, 'error': 'Gmail service not available'}

        try:
            # Resolve domain from company name if needed
            resolved_domain, resolved_company = self._resolve_domain(company, domain)

            if not resolved_domain:
                return {'success': False, 'error': 'Could not determine company domain'}

            # Clean domain
            resolved_domain = re.sub(r'^https?://', '', resolved_domain.lower().strip())
            resolved_domain = re.sub(r'^www\.', '', resolved_domain)
            resolved_domain = re.sub(r'/.*$', '', resolved_domain)

            # Search for emails from this domain
            query = f'from:@{resolved_domain}'
            logger.info(f"Searching for update emails with query: {query}")
            emails = gmail.fetch_emails(query=query, max_results=100)

            if not emails:
                return {
                    'success': True,
                    'company': resolved_company,
                    'domain': resolved_domain,
                    'email_count': 0,
                    'summary': f'No update emails found from {resolved_domain}',
                    'doc_id': None
                }

            # Sort emails by date
            emails.sort(key=lambda e: e.get('parsed_date') or e.get('date', ''))

            first_date = emails[0].get('date', 'Unknown')
            last_date = emails[-1].get('date', 'Unknown')

            # Generate summary
            summary_result = self._generate_summary(emails, resolved_company, resolved_domain)

            # Create summary document
            drive = self.services['drive']
            docs = self.services['docs']

            folder_id = drive.find_existing_folder(resolved_company, resolved_domain)
            if not folder_id:
                folder_id = drive.create_folder(resolved_company, resolved_domain)

            doc_metadata = drive.service.files().create(
                body={
                    'name': 'Updates Summary',
                    'mimeType': 'application/vnd.google-apps.document',
                    'parents': [folder_id]
                },
                supportsAllDrives=True,
                fields='id'
            ).execute()

            doc_id = doc_metadata['id']

            content = self._format_summary_content(
                resolved_company, resolved_domain, emails, summary_result, first_date, last_date
            )
            docs.insert_text(doc_id, content)

            logger.info(f"Created updates summary for {resolved_company}: {len(emails)} emails")

            return {
                'success': True,
                'company': resolved_company,
                'domain': resolved_domain,
                'email_count': len(emails),
                'date_range': {'first': first_date, 'last': last_date},
                'summary': summary_result.get('summary', ''),
                'highlights': summary_result.get('highlights', []),
                'doc_id': doc_id
            }

        except Exception as e:
            logger.error(f"Error summarizing company updates: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _resolve_domain(self, company: str, domain: str) -> tuple:
        """Resolve company domain from name if needed."""
        if domain:
            return domain, company

        sheets = self.services.get('sheets')
        if sheets:
            try:
                companies = sheets.get_all_companies()
                for c in companies:
                    if c.get('company', '').lower() == company.lower():
                        return c.get('domain', ''), c.get('company', company)
            except Exception:
                pass

        # Fallback
        return f"{company.lower().replace(' ', '')}.com", company

    def _generate_summary(self, emails: List[Dict], company: str, domain: str) -> Dict[str, Any]:
        """Use Gemini to generate a summary of update emails."""
        sorted_emails = sorted(
            emails,
            key=lambda e: e.get('parsed_date') or e.get('date', ''),
            reverse=True
        )

        email_sections = []
        for i, e in enumerate(sorted_emails[:50]):
            recency_label = ""
            if i == 0:
                recency_label = "[MOST RECENT] "
            elif i < 5:
                recency_label = "[RECENT] "

            email_sections.append(
                f"{recency_label}Date: {e.get('date', 'Unknown')}\n"
                f"Subject: {e.get('subject', 'No subject')}\n\n"
                f"{e.get('body', '')[:3000]}"
            )

        emails_text = "\n\n---\n\n".join(email_sections)

        prompt = f"""Analyze these {len(emails)} emails from {company} ({domain}) and create a summary.

CRITICAL: Prioritize recent information. The MOST RECENT email represents current state.

EMAILS (most recent first):
{emails_text[:30000]}

Create a JSON response:
{{
  "summary": "2-3 paragraph executive summary focused on RECENT updates",
  "current_status": "1-2 sentence summary of where company stands NOW",
  "highlights": ["Most important recent highlight", "..."],
  "product_updates": ["Recent product update 1", "..."],
  "business_updates": ["Recent business update 1", "..."],
  "themes": ["recurring theme 1", "theme 2"],
  "sentiment": "positive/neutral/negative/mixed",
  "trajectory": "growing/stable/declining/unclear",
  "notable_metrics": [
    {{"metric": "Revenue", "value": "$X", "context": "optional", "date": "when reported"}}
  ]
}}

Focus on concrete facts and metrics. Prioritize recency.
Respond with JSON only, no markdown."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 4000,
                    "temperature": 0.2,
                }
            )

            content = response.text.strip()
            if content.startswith('```'):
                content = re.sub(r'```json?\n?', '', content)
                content = re.sub(r'```', '', content)
                content = content.strip()

            return json.loads(content)

        except Exception as e:
            logger.error(f"Error generating updates summary: {e}")
            return {
                'summary': f'Error analyzing updates: {str(e)}',
                'highlights': [],
                'product_updates': [],
                'business_updates': [],
                'themes': [],
                'sentiment': 'unknown',
                'trajectory': 'unclear',
                'notable_metrics': []
            }

    def _format_summary_content(self, company: str, domain: str, emails: List[Dict],
                                summary: Dict[str, Any], first_date: str, last_date: str) -> str:
        """Format the updates summary document content."""
        current_status = summary.get('current_status', '')
        highlights = '\n'.join(f"- {h}" for h in summary.get('highlights', [])) or "None identified"
        product_updates = '\n'.join(f"- {u}" for u in summary.get('product_updates', [])) or "None identified"
        business_updates = '\n'.join(f"- {u}" for u in summary.get('business_updates', [])) or "None identified"
        themes = ', '.join(summary.get('themes', [])) or "None identified"

        metrics_text = ""
        if summary.get('notable_metrics'):
            metrics_lines = []
            for m in summary['notable_metrics']:
                line = f"- **{m.get('metric', 'Unknown')}:** {m.get('value', 'N/A')}"
                if m.get('context'):
                    line += f" ({m.get('context')})"
                metrics_lines.append(line)
            metrics_text = '\n'.join(metrics_lines)
        else:
            metrics_text = "None identified"

        current_status_section = ""
        if current_status:
            current_status_section = f"\n## Current Status\n{current_status}\n"

        return f"""# Updates Summary: {company}

## Overview
- **Domain:** {domain}
- **Emails Analyzed:** {len(emails)}
- **Date Range:** {first_date} to {last_date}
- **Overall Sentiment:** {summary.get('sentiment', 'Unknown').title()}
- **Trajectory:** {summary.get('trajectory', 'Unknown').title()}
{current_status_section}
## Executive Summary
{summary.get('summary', 'No summary available')}

## Key Highlights
{highlights}

## Product & Feature Updates
{product_updates}

## Business Updates
{business_updates}

## Notable Metrics
{metrics_text}

## Recurring Themes
{themes}

---
*Generated from {len(emails)} update emails*
"""

    def format_response(self, result: Dict[str, Any]) -> str:
        if not result.get('success'):
            return f"Failed to summarize updates: {result.get('error', 'Unknown error')}"

        company = result.get('company', 'Unknown')
        domain = result.get('domain', '')
        email_count = result.get('email_count', 0)

        if email_count == 0:
            return f"""No update emails found from **{company}** ({domain}).

Make sure the company sends updates to updates@friale.com."""

        doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
        date_range = result.get('date_range', {})
        summary = result.get('summary', '')

        if len(summary) > 600:
            summary = summary[:600] + '...'

        highlights = result.get('highlights', [])
        highlights_text = ""
        if highlights:
            highlights_text = "\n**Highlights:**\n" + '\n'.join(f"- {h}" for h in highlights[:5])

        return f"""✓ **Updates Summary: {company}**

**Domain:** {domain}
**Emails analyzed:** {email_count}
**Date range:** {date_range.get('first', 'Unknown')} to {date_range.get('last', 'Unknown')}

**Summary:**
{summary}
{highlights_text}

**Full report:** {doc_url}"""
