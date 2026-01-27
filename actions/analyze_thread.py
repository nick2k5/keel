"""Analyze thread action."""
import json
import logging
import re
from typing import Dict, Any, Optional, List

import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import firestore as firestore_module

from actions.base import BaseAction
from core.thread_parser import ThreadParser
from config import config

logger = logging.getLogger(__name__)


class AnalyzeThreadAction(BaseAction):
    """Analyze a forwarded email thread to create a relationship timeline."""

    name = 'ANALYZE_THREAD'
    description = 'Analyze a forwarded email thread to create a relationship timeline and summary.'

    def __init__(self, services: Dict[str, Any]):
        super().__init__(services)
        self.parser = ThreadParser()
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

    def execute(self, parameters: Dict[str, Any],
                email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        if not email_data:
            return {'success': False, 'error': 'No email data provided'}

        email_body = email_data.get('body', '')
        if not email_body:
            return {'success': False, 'error': 'No email body to analyze'}

        try:
            sheets = self.services['sheets']
            firestore = self.services['firestore']
            drive = self.services['drive']
            docs = self.services['docs']

            # Parse the email thread
            new_messages = self.parser.parse_thread(email_body)

            if not new_messages:
                return {
                    'success': False,
                    'error': 'Could not parse any emails from the forwarded thread'
                }

            # Extract domain
            domain = self.parser.extract_domain(new_messages)

            if not domain:
                return {
                    'success': False,
                    'error': 'Could not determine the domain from the email thread'
                }

            # Check for existing relationship
            existing = self._get_relationship(firestore, domain)

            if existing:
                existing_messages = existing.get('raw_messages', [])
                all_messages = self.parser.merge_messages(existing_messages, new_messages)
                doc_id = existing.get('doc_id')
                folder_id = existing.get('folder_id')
                company_name = existing.get('company_name', domain)
            else:
                all_messages = new_messages
                doc_id = None
                folder_id = None
                company_name = None

            # Generate analysis
            analysis = self._generate_analysis(all_messages, domain)

            if not company_name:
                company_name = analysis.get('company_name', domain)

            # Create or find folder
            if not folder_id:
                folder_id = drive.find_existing_folder(company_name, domain)
                if not folder_id:
                    folder_id = drive.create_folder(company_name, domain)
                    sheets.add_company(company_name, domain)

            # Create or update timeline doc
            if doc_id:
                doc_id = self._update_timeline_doc(docs, doc_id, company_name, analysis)
            else:
                doc_id = self._create_timeline_doc(drive, docs, folder_id, company_name, analysis)

            # Store in Firestore
            self._store_relationship(firestore, domain, all_messages, analysis, doc_id, folder_id, company_name)

            logger.info(f"Analyzed thread for domain {domain} ({len(all_messages)} total messages)")

            return {
                'success': True,
                'domain': domain,
                'company_name': company_name,
                'message_count': len(all_messages),
                'new_messages': len(new_messages),
                'updated': existing is not None,
                'doc_id': doc_id,
                'summary': analysis.get('summary', ''),
                'introducer': analysis.get('introducer', {})
            }

        except Exception as e:
            logger.error(f"Error analyzing thread: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _get_relationship(self, firestore, domain: str) -> Optional[Dict[str, Any]]:
        """Get existing relationship data from Firestore."""
        normalized = domain.lower().strip()
        doc_ref = firestore.db.collection('relationships').document(normalized)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def _generate_analysis(self, messages: List[Dict[str, str]], domain: str) -> Dict[str, Any]:
        """Use Gemini to generate relationship timeline and summary."""
        messages_text = "\n\n---\n\n".join([
            f"From: {m['from']}\nDate: {m['date']}\nSubject: {m['subject']}\n\n{m['body']}"
            for m in messages
        ])

        prompt = f"""Analyze this email thread with {domain} and create a relationship summary.

EMAIL THREAD:
{messages_text[:15000]}

Create a JSON response with:
{{
  "company_name": "The company name (infer from domain or emails)",
  "introducer": {{
    "name": "Name of person who made the introduction (if identifiable)",
    "email": "Their email address",
    "context": "How/why they made the introduction"
  }},
  "contacts": [
    {{"name": "Person Name", "email": "email@domain.com", "role": "Their role if mentioned"}}
  ],
  "timeline": [
    {{"date": "YYYY-MM-DD or approximate", "event": "Brief description of what happened"}}
  ],
  "summary": "2-3 paragraph summary of the relationship",
  "key_topics": ["topic1", "topic2"],
  "sentiment": "positive/neutral/negative",
  "next_steps": "Any obvious next steps or follow-ups needed"
}}

IMPORTANT: Look for introduction patterns like "introducing you to", "wanted to connect you with".
Be thorough in extracting the timeline. Sort chronologically (oldest first).
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
            logger.error(f"Error generating relationship analysis: {e}")
            return {
                'company_name': domain,
                'contacts': [],
                'timeline': [],
                'summary': f'Error analyzing thread: {str(e)}',
                'key_topics': [],
                'sentiment': 'neutral',
                'next_steps': ''
            }

    def _format_timeline_content(self, company_name: str, analysis: Dict[str, Any]) -> str:
        """Format the timeline document content."""
        introducer = analysis.get('introducer') or {}
        if introducer and introducer.get('name'):
            intro_text = f"**{introducer.get('name', 'Unknown')}**"
            if introducer.get('email'):
                intro_text += f" ({introducer.get('email')})"
            if introducer.get('context'):
                intro_text += f"\n{introducer.get('context')}"
        else:
            intro_text = "No introducer identified"

        contacts_text = "\n".join([
            f"- **{c.get('name', 'Unknown')}** ({c.get('email', '')}) - {c.get('role', 'Unknown role')}"
            for c in analysis.get('contacts', [])
        ]) or "No contacts identified"

        timeline_text = "\n".join([
            f"- **{t.get('date', 'Unknown date')}**: {t.get('event', '')}"
            for t in analysis.get('timeline', [])
        ]) or "No timeline events identified"

        topics_text = ", ".join(analysis.get('key_topics', [])) or "None identified"

        return f"""# Timeline: {company_name}

## Introduction
{intro_text}

## Contacts
{contacts_text}

## Summary
{analysis.get('summary', 'No summary available')}

## Timeline
{timeline_text}

## Key Topics
{topics_text}

## Sentiment
{analysis.get('sentiment', 'neutral').title()}

## Next Steps
{analysis.get('next_steps', 'None identified')}
"""

    def _create_timeline_doc(self, drive, docs, folder_id: str, company_name: str,
                            analysis: Dict[str, Any]) -> str:
        """Create a new Timeline doc in the company folder."""
        doc_metadata = drive.service.files().create(
            body={
                'name': 'Timeline',
                'mimeType': 'application/vnd.google-apps.document',
                'parents': [folder_id]
            },
            supportsAllDrives=True,
            fields='id'
        ).execute()

        doc_id = doc_metadata['id']
        content = self._format_timeline_content(company_name, analysis)
        docs.insert_text(doc_id, content)

        logger.info(f"Created Timeline doc {doc_id} in folder {folder_id}")
        return doc_id

    def _update_timeline_doc(self, docs, doc_id: str, company_name: str,
                            analysis: Dict[str, Any]) -> str:
        """Update an existing Timeline doc."""
        try:
            doc = docs.service.documents().get(documentId=doc_id).execute()
            content_end = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)

            if content_end > 2:
                requests = [{
                    'deleteContentRange': {
                        'range': {
                            'startIndex': 1,
                            'endIndex': content_end - 1
                        }
                    }
                }]
                docs.service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': requests}
                ).execute()

            content = self._format_timeline_content(company_name, analysis)
            docs.insert_text(doc_id, content)

            logger.info(f"Updated Timeline doc {doc_id}")
            return doc_id

        except Exception as e:
            logger.error(f"Error updating timeline doc: {e}", exc_info=True)
            raise

    def _store_relationship(self, firestore, domain: str, messages: List[Dict],
                           analysis: Dict[str, Any], doc_id: str, folder_id: str,
                           company_name: str):
        """Store relationship data in Firestore."""
        normalized = domain.lower().strip()
        doc_ref = firestore.db.collection('relationships').document(normalized)

        doc_ref.set({
            'domain': domain,
            'company_name': company_name,
            'folder_id': folder_id,
            'doc_id': doc_id,
            'introducer': analysis.get('introducer'),
            'contacts': analysis.get('contacts', []),
            'timeline': analysis.get('timeline', []),
            'summary': analysis.get('summary', ''),
            'key_topics': analysis.get('key_topics', []),
            'sentiment': analysis.get('sentiment', 'neutral'),
            'next_steps': analysis.get('next_steps', ''),
            'message_count': len(messages),
            'raw_messages': messages,
            'analyzed_at': firestore_module.SERVER_TIMESTAMP
        })

        logger.info(f"Stored relationship data for {domain}")

    def format_response(self, result: Dict[str, Any]) -> str:
        if not result.get('success'):
            return f"Failed to analyze thread: {result.get('error', 'Unknown error')}"

        doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
        summary = result.get('summary', '')
        if len(summary) > 500:
            summary = summary[:500] + '...'

        updated = result.get('updated', False)
        status = "Timeline updated!" if updated else "Timeline created!"

        introducer = result.get('introducer') or {}
        intro_text = ""
        if introducer and introducer.get('name'):
            intro_text = f"\n**Introduced by:** {introducer.get('name', 'Unknown')}"
            if introducer.get('context'):
                intro_text += f" ({introducer.get('context')})"

        if updated:
            msg_info = f"**Total messages:** {result.get('message_count', 0)} (+{result.get('new_messages', 0)} new)"
        else:
            msg_info = f"**Messages analyzed:** {result.get('message_count', 0)}"

        return f"""✓ **{status}**

**Company:** {result.get('company_name', result.get('domain'))}
**Domain:** {result.get('domain')}
{msg_info}{intro_text}

**Summary:**
{summary}

**Full timeline:** {doc_url}

Forward more threads to add to this relationship history."""
