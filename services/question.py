"""Question answering service for open-ended questions."""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import vertexai
from vertexai.generative_models import GenerativeModel
from config import config

logger = logging.getLogger(__name__)


class QuestionService:
    """Service for answering open-ended questions by searching multiple data sources."""

    def __init__(self, services: Dict[str, Any]):
        """Initialize QuestionService with service dependencies.

        Args:
            services: Dict containing firestore, gemini, and optionally gmail services
        """
        self.firestore = services.get('firestore')
        self.gemini = services.get('gemini')
        self.gmail = services.get('gmail')

        # Initialize Vertex AI for question classification
        vertexai.init(project=config.project_id, location=config.vertex_ai_region)
        self.model = GenerativeModel("gemini-2.0-flash-001")

    def answer(self, question: str) -> Dict[str, Any]:
        """Answer an open-ended question by searching available data sources.

        Args:
            question: The user's question

        Returns:
            Dict with 'answer', 'sources_used', and 'classification'
        """
        logger.info(f"Answering question: {question[:100]}...")

        # 1. Classify the question type and extract entities
        classification = self._classify_question(question)
        logger.info(f"Question classification: {classification}")

        # 2. Gather data from relevant sources
        data = self._gather_data(classification, question)

        # 3. Synthesize an answer using Gemini
        answer = self._synthesize(question, data, classification)

        return {
            'answer': answer,
            'sources_used': data.get('sources_used', []),
            'classification': classification,
            'data_found': data.get('data_found', {})
        }

    def _classify_question(self, question: str) -> Dict[str, Any]:
        """Use Gemini to classify the question type and extract entities.

        Args:
            question: The user's question

        Returns:
            Dict with 'type' and 'entities' extracted from the question
        """
        prompt = f"""Analyze this question and classify it. Extract any mentioned entities.

Question: {question}

Respond with JSON only (no markdown):
{{
  "type": "person|company|relationship|general",
  "entities": {{
    "person": "Person's name if mentioned (null if not)",
    "company": "Company name if mentioned (null if not)",
    "domain": "Domain/website if mentioned or inferable (null if not)"
  }},
  "intent": "Brief description of what the user wants to know"
}}

Classification types:
- "person": Questions about a specific person (contact, colleague, etc.)
- "company": Questions about a company, startup, or organization
- "relationship": Questions about interaction history or relationship status
- "general": General questions not about a specific person/company

Examples:
- "What do we know about Stripe?" -> type: "company", entities: {{company: "Stripe", domain: "stripe.com"}}
- "When did I last talk to John?" -> type: "person", entities: {{person: "John"}}
- "What's our history with Acme Corp?" -> type: "relationship", entities: {{company: "Acme Corp"}}
- "What are the latest AI regulations?" -> type: "general", entities: {{}}"""

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
            logger.error(f"Error classifying question: {e}")
            return {
                'type': 'general',
                'entities': {},
                'intent': 'Unknown'
            }

    def _gather_data(self, classification: Dict[str, Any], question: str) -> Dict[str, Any]:
        """Gather data from relevant sources based on question classification.

        Args:
            classification: The question classification
            question: The original question

        Returns:
            Dict with gathered data and sources_used list
        """
        data = {
            'sources_used': [],
            'data_found': {},
            'inbox_emails': [],
            'relationship_data': None,
            'processed_company': None,
            'web_research': None
        }

        q_type = classification.get('type', 'general')
        entities = classification.get('entities', {})

        # Extract entities
        person = entities.get('person')
        company = entities.get('company')
        domain = entities.get('domain')

        # If we have a company but no domain, try to infer it
        if company and not domain:
            domain = self._infer_domain(company)

        # Gather data based on question type
        if q_type in ['company', 'relationship'] and (company or domain):
            # Check for relationship data
            rel_data = self._get_relationship_data(domain, company)
            if rel_data:
                data['relationship_data'] = rel_data
                data['sources_used'].append('relationships')
                data['data_found']['relationship'] = True

            # Check for processed company memo data
            if domain:
                processed = self._get_processed_company(domain)
                if processed:
                    data['processed_company'] = processed
                    data['sources_used'].append('processed_domains')
                    data['data_found']['memo'] = True

            # Search inbox for emails from this company's domain
            inbox_emails = self._search_inbox_by_domain(domain or company)
            if inbox_emails:
                data['inbox_emails'] = inbox_emails
                data['sources_used'].append('email_research')
                data['data_found']['emails'] = len(inbox_emails)

        elif q_type == 'person' and person:
            # Search inbox for emails from/to this person
            inbox_emails = self._search_inbox_by_person(person)
            if inbox_emails:
                data['inbox_emails'] = inbox_emails
                data['sources_used'].append('email_research')
                data['data_found']['emails'] = len(inbox_emails)

        # For general questions or when we don't have enough data, use web search
        if q_type == 'general' or not data['sources_used']:
            web_data = self._web_search(question, company)
            if web_data:
                data['web_research'] = web_data
                data['sources_used'].append('web_search')
                data['data_found']['web'] = True

        return data

    def _infer_domain(self, company: str) -> Optional[str]:
        """Try to infer a domain from a company name.

        Args:
            company: Company name

        Returns:
            Inferred domain or None
        """
        # Common patterns for company -> domain
        common_domains = {
            'stripe': 'stripe.com',
            'google': 'google.com',
            'apple': 'apple.com',
            'microsoft': 'microsoft.com',
            'amazon': 'amazon.com',
            'meta': 'meta.com',
            'facebook': 'facebook.com',
            'openai': 'openai.com',
            'anthropic': 'anthropic.com',
        }

        company_lower = company.lower().strip()
        if company_lower in common_domains:
            return common_domains[company_lower]

        # Try simple domain construction
        # Remove common suffixes and spaces
        cleaned = re.sub(r'\s*(inc\.?|llc\.?|corp\.?|co\.?)$', '', company_lower, flags=re.IGNORECASE)
        cleaned = re.sub(r'[^a-z0-9]', '', cleaned)

        if cleaned:
            return f"{cleaned}.com"

        return None

    def _get_relationship_data(self, domain: str = None, company: str = None) -> Optional[Dict[str, Any]]:
        """Get relationship data from Firestore.

        Args:
            domain: Company domain
            company: Company name

        Returns:
            Relationship data or None
        """
        if not self.firestore:
            return None

        try:
            return self.firestore.get_relationship_data(domain=domain, company_name=company)
        except Exception as e:
            logger.warning(f"Error getting relationship data: {e}")
            return None

    def _get_processed_company(self, domain: str) -> Optional[Dict[str, Any]]:
        """Get processed company data from Firestore.

        Args:
            domain: Company domain

        Returns:
            Processed company data or None
        """
        if not self.firestore:
            return None

        try:
            return self.firestore.get_processed(domain)
        except Exception as e:
            logger.warning(f"Error getting processed company: {e}")
            return None

    def _search_inbox_by_domain(self, domain_or_company: str) -> List[Dict[str, Any]]:
        """Search stored emails by domain.

        Args:
            domain_or_company: Domain or company name to search for

        Returns:
            List of matching emails
        """
        if not self.firestore:
            return []

        try:
            # Try to extract domain from input
            domain = domain_or_company.lower().strip()
            if '.' not in domain:
                domain = self._infer_domain(domain) or domain

            # Search in email_research collection
            docs = (self.firestore.db
                    .collection('email_research')
                    .where('domain', '==', domain.replace('.com', '').replace('.', ''))
                    .order_by('date', direction='DESCENDING')
                    .limit(20)
                    .stream())

            emails = [doc.to_dict() for doc in docs]

            # If no results, try searching by the full domain
            if not emails:
                docs = (self.firestore.db
                        .collection('email_research')
                        .where('domain', '==', domain)
                        .order_by('date', direction='DESCENDING')
                        .limit(20)
                        .stream())
                emails = [doc.to_dict() for doc in docs]

            return emails

        except Exception as e:
            logger.warning(f"Error searching inbox by domain: {e}")
            return []

    def _search_inbox_by_person(self, person: str) -> List[Dict[str, Any]]:
        """Search stored emails by person name.

        Args:
            person: Person name to search for

        Returns:
            List of matching emails
        """
        if not self.firestore:
            return []

        try:
            # Firestore doesn't support full-text search, so we need to fetch and filter
            docs = (self.firestore.db
                    .collection('email_research')
                    .order_by('date', direction='DESCENDING')
                    .limit(100)
                    .stream())

            person_lower = person.lower()
            matching_emails = []

            for doc in docs:
                data = doc.to_dict()
                from_field = (data.get('from') or '').lower()
                to_field = (data.get('to') or '').lower()

                if person_lower in from_field or person_lower in to_field:
                    matching_emails.append(data)
                    if len(matching_emails) >= 20:
                        break

            return matching_emails

        except Exception as e:
            logger.warning(f"Error searching inbox by person: {e}")
            return []

    def _web_search(self, question: str, company: str = None) -> Optional[Dict[str, Any]]:
        """Use Gemini for general knowledge answers (web search grounding deprecated).

        Args:
            question: The user's question
            company: Optional company name for context

        Returns:
            Research data or None
        """
        try:
            context = f"Research about {company}: " if company else ""
            prompt = f"""{context}{question}

Provide a helpful answer based on your knowledge. Include specific facts and be clear about what you know vs. what you're uncertain about."""

            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 2048,
                    "temperature": 0.3,
                }
            )

            content = response.text.strip()

            return {
                'content': content,
                'sources': []  # No grounding sources available
            }

        except Exception as e:
            logger.error(f"Error doing web research: {e}")
            return None

    def _synthesize(self, question: str, data: Dict[str, Any], classification: Dict[str, Any]) -> str:
        """Use Gemini to synthesize an answer from gathered data.

        Args:
            question: The original question
            data: Gathered data from various sources
            classification: Question classification

        Returns:
            Synthesized answer string
        """
        # Build context from gathered data
        context_parts = []

        # Add relationship data
        if data.get('relationship_data'):
            rel = data['relationship_data']
            context_parts.append("=== RELATIONSHIP DATA ===")
            if rel.get('company_name'):
                context_parts.append(f"Company: {rel['company_name']}")
            if rel.get('summary'):
                context_parts.append(f"Summary: {rel['summary']}")
            if rel.get('introducer'):
                intro = rel['introducer']
                context_parts.append(f"Introduced by: {intro.get('name', 'Unknown')} ({intro.get('email', '')})")
                if intro.get('context'):
                    context_parts.append(f"  Context: {intro['context']}")
            if rel.get('contacts'):
                context_parts.append("Key Contacts:")
                for c in rel['contacts'][:5]:
                    context_parts.append(f"  - {c.get('name', 'Unknown')} ({c.get('email', '')}) - {c.get('role', '')}")
            if rel.get('timeline'):
                context_parts.append("Timeline:")
                for t in rel['timeline'][:10]:
                    context_parts.append(f"  - {t.get('date', 'Unknown')}: {t.get('event', '')}")
            if rel.get('next_steps'):
                context_parts.append(f"Next Steps: {rel['next_steps']}")

        # Add processed company data
        if data.get('processed_company'):
            proc = data['processed_company']
            context_parts.append("\n=== PROCESSED COMPANY DATA ===")
            context_parts.append(f"Company: {proc.get('company', 'Unknown')}")
            context_parts.append(f"Domain: {proc.get('domain', 'Unknown')}")
            if proc.get('doc_id'):
                context_parts.append(f"Memo Doc ID: {proc['doc_id']}")
            if proc.get('processed_at'):
                context_parts.append(f"Memo created: {proc['processed_at']}")

        # Add email data
        if data.get('inbox_emails'):
            emails = data['inbox_emails']
            context_parts.append(f"\n=== RECENT EMAILS ({len(emails)} found) ===")
            for email in emails[:10]:
                context_parts.append(f"\nFrom: {email.get('from', 'Unknown')}")
                context_parts.append(f"Date: {email.get('date', 'Unknown')}")
                context_parts.append(f"Subject: {email.get('subject', 'No subject')}")
                snippet = email.get('snippet', email.get('body', ''))[:200]
                context_parts.append(f"Preview: {snippet}...")

        # Add web research
        if data.get('web_research'):
            web = data['web_research']
            context_parts.append("\n=== WEB RESEARCH ===")
            context_parts.append(web.get('content', ''))

        # If no data was found, note that
        if not context_parts:
            context_parts.append("No relevant data found in available sources (inbox, relationships, processed companies).")

        context = '\n'.join(context_parts)

        # Build the synthesis prompt
        prompt = f"""You are Keel, an AI assistant for a venture capital firm. Answer the following question based on the available data.

QUESTION: {question}

AVAILABLE DATA:
{context[:12000]}

INSTRUCTIONS:
1. Provide a helpful, conversational answer based on the data above
2. If relationship/email data is available, highlight key contacts and recent interactions
3. If no relevant data was found, say so honestly and suggest how to get the information
4. Be concise but informative - this is for a busy investor
5. Use markdown formatting for clarity (bold for names/important items, bullets for lists)
6. If there's a memo document, mention it and provide the link format
7. Don't make up information - only use what's in the data

Respond with a natural, helpful answer:"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 2048,
                    "temperature": 0.4,
                }
            )

            return response.text.strip()

        except Exception as e:
            logger.error(f"Error synthesizing answer: {e}")
            return f"I encountered an error while synthesizing an answer: {str(e)}"
