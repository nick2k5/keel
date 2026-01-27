"""Email agent service for AI-powered email routing."""
import json
import logging
import re
from typing import Dict, List, Optional, Any
from collections import Counter

import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import firestore as firestore_module
from config import config

from services.research import ResearchService
from services.bookface import BookfaceService

logger = logging.getLogger(__name__)


class EmailAgentService:
    """Service for processing emails with AI-powered routing."""

    # Define available actions
    ACTIONS = {
        'GENERATE_MEMOS': {
            'description': 'Generate investment memos for new companies in the sheet'
        },
        'ADD_COMPANY': {
            'description': 'Add a new company to the deal flow spreadsheet. Extract company name and domain from the email.'
        },
        'UPDATE_COMPANY': {
            'description': 'Update/correct a company\'s domain or name. Use when someone provides a correction like "Domain is X" or "Actually the domain is X" or "Correct domain: X".'
        },
        'REGENERATE_MEMO': {
            'description': 'Regenerate an investment memo for a specific company. Use when a memo needs to be redone. Extract the domain OR company name from the email.'
        },
        'ANALYZE_THREAD': {
            'description': 'Analyze a forwarded email thread to create a relationship timeline and summary. Use when email contains forwarded messages (look for "Forwarded message", "From:", date patterns, or quoted content).'
        },
        'SUMMARIZE_UPDATES': {
            'description': 'Summarize update emails from a company. Use when asked "how is [company] doing?", "summarize updates from [company/domain]", or "[company] updates".'
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

    def process_email(self, email_data: Dict[str, str], services: Dict) -> Dict[str, Any]:
        """Process an incoming email and execute the appropriate action."""
        logger.info(f"Processing email: {email_data.get('subject', 'No subject')}")

        # Get LLM decision
        decision = self._get_action_decision(email_data)
        logger.info(f"LLM decision: {decision}")

        # Execute the action
        result = self._execute_action(decision, services, email_data)

        # Format response for email reply
        response_text = self._format_response(decision, result)

        return {
            'decision': decision,
            'result': result,
            'reply_text': response_text
        }

    def _get_action_decision(self, email_data: Dict[str, str]) -> Dict[str, Any]:
        """Use Gemini to decide what action to take based on email content."""
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
- "It should be..." or "Change it to..."
- A URL appearing right after Keel's "Company added" or "Domain:" response
- User typing a URL that differs from what Keel reported

Example correction scenario:
```
Keel: ✓ Company added! Company: HCA, Domain: hca.com
User: Domain is https://www.hcahealthcare.com/
      Generate memos
```
This should be: UPDATE_COMPANY with {{"company": "HCA", "new_domain": "hcahealthcare.com"}}, also_do: GENERATE_MEMOS

**UPDATE_COMPANY:**
- Use when correcting/updating a company's domain or name
- Parameters: {{"company": "Company Name", "new_domain": "correct.com"}}
- Can include "also_do" for a follow-up action like GENERATE_MEMOS

**ADD_COMPANY:**
- Use ONLY for adding NEW companies (not corrections)
- Parameters: {{"company": "Company Name", "domain": "example.com"}}
- Common pattern: Subject says "add company" and the body contains the company name (possibly with domain)
- Example: Subject "add company", Body "Good Day" → ADD_COMPANY with {{"company": "Good Day", "domain": ""}}
- Example: Subject "add company", Body "Stripe (stripe.com)" → ADD_COMPANY with {{"company": "Stripe", "domain": "stripe.com"}}
- CRITICAL: Extract company name from the MAIN body text, NOT from email signatures
- Email signatures appear after "-- " or at the very end with sender's title/company
- The sender's own company in their signature is NOT the company to add

**GENERATE_MEMOS:**
- Use for: "run memos", "generate", "generate memos", "process"
- Parameters: {{"force": false}} (default) or {{"force": true}} for regenerating all

**REGENERATE_MEMO:**
- Use for: "regenerate memo for X", "redo X", "retry X"
- Parameters: {{"domain": "example.com"}} or {{"domain": "Company Name"}}

**ANALYZE_THREAD:**
- Use for FORWARDED email threads (look for "Forwarded message", multiple From:/Date: headers)
- No parameters needed

**SUMMARIZE_UPDATES:**
- Use for: "how is [company] doing?", "summarize updates from [company]", "[company] updates", "what's new with [company]"
- Parameters: {{"company": "Company Name", "domain": "optional.domain.com"}}
- Example: "How is Stripe doing?" → {{"company": "Stripe"}}
- Example: "Summarize updates from stripe.com" → {{"domain": "stripe.com"}}

**SCRAPE_YC:**
- Use for: "scrape YC", "import YC batch", "get W26 companies"
- Parameters: {{"batch": "W26", "pages": 3}}

**HEALTH_CHECK:**
- Use for: "status", "health", "check"

**NONE:**
- Use when the request is truly unclear or ambiguous
- Use when no actionable command is found

**CRITICAL - Email Signature Detection:**
- Signatures typically start with "-- " or appear at the very end with job titles
- Pattern: "Name\\nTitle, Company" at the end = signature, NOT the company to add
- Example signature to IGNORE: "Nick Alexander\\nManaging Partner & Co-Founder, Friale"
- The text BEFORE the signature is the actual message content
- Extract company names from the message content, NOT the signature

Be helpful. When in doubt about whether something is a correction vs new addition, check if Keel previously mentioned that company in the thread."""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": 500,
                    "temperature": 0.1,
                }
            )

            content = response.text.strip()
            # Clean markdown if present
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

    def _execute_action(self, decision: Dict[str, Any], services: Dict,
                        email_data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Execute the decided action."""
        action = decision.get('action', 'NONE')
        parameters = decision.get('parameters', {})
        also_do = decision.get('also_do')

        result = None

        if action == 'GENERATE_MEMOS':
            force = parameters.get('force', False)
            result = self._run_memo_generation(services, force=force)

        elif action == 'ADD_COMPANY':
            company = parameters.get('company', '')
            domain = parameters.get('domain', '')
            if not company and not domain:
                return {'success': False, 'error': 'Missing company name or domain'}
            # Allow adding company without domain (for YC companies)
            result = services['sheets'].add_company(company, domain)

        elif action == 'UPDATE_COMPANY':
            company = parameters.get('company', '')
            new_domain = parameters.get('new_domain', '') or parameters.get('domain', '')
            new_name = parameters.get('new_name', '')
            if not company:
                return {'success': False, 'error': 'Missing company name to update'}
            if not new_domain and not new_name:
                return {'success': False, 'error': 'Missing new domain or name to update'}
            result = services['sheets'].update_company(company, new_domain=new_domain, new_name=new_name)

        elif action == 'REGENERATE_MEMO':
            identifier = parameters.get('domain', '') or parameters.get('company', '')
            if not identifier:
                return {'success': False, 'error': 'Missing domain or company name to regenerate'}
            result = self._regenerate_memo(identifier, services)

        elif action == 'ANALYZE_THREAD':
            if not email_data:
                return {'success': False, 'error': 'No email data provided'}
            email_body = email_data.get('body', '')
            if not email_body:
                return {'success': False, 'error': 'No email body to analyze'}
            result = self._analyze_thread(email_body, services)

        elif action == 'SUMMARIZE_UPDATES':
            company = parameters.get('company', '')
            domain = parameters.get('domain', '')
            if not company and not domain:
                return {'success': False, 'error': 'Missing company name or domain'}
            result = self._summarize_company_updates(company, domain, services)

        elif action == 'SCRAPE_YC':
            batch = parameters.get('batch', 'W26')
            max_pages = parameters.get('pages', None)  # None = use default
            if max_pages is not None:
                max_pages = min(int(max_pages), 5)  # Cap at 5 pages max
            result = self._scrape_yc_batch(batch, services, max_pages=max_pages)

        elif action == 'HEALTH_CHECK':
            result = {'success': True, 'status': 'healthy', 'message': 'All systems operational'}

        else:
            return {'success': False, 'skipped': True}

        # Handle chained action (also_do)
        if also_do and result and result.get('success'):
            logger.info(f"Executing chained action: {also_do}")
            chained_decision = {'action': also_do, 'parameters': {}}

            # If we just updated a company and need to generate memo, use the updated company
            if also_do == 'GENERATE_MEMOS':
                chained_result = self._run_memo_generation(services, force=False)
            elif also_do == 'REGENERATE_MEMO' and result.get('company'):
                chained_result = self._regenerate_memo(result['company'], services)
            else:
                chained_result = self._execute_action(chained_decision, services, email_data)

            # Combine results
            result['chained_action'] = also_do
            result['chained_result'] = chained_result

        return result

    def _run_memo_generation(self, services: Dict, force: bool = False) -> Dict[str, Any]:
        """Run the memo generation process.

        Args:
            services: Dict of service instances
            force: If True, regenerate memos for ALL companies (even already processed)
        """
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            gemini = services['gemini']
            docs = services['docs']

            if force:
                # Get ALL companies from sheet (not just unprocessed)
                rows = sheets.get_all_companies()
            else:
                rows = sheets.get_rows_to_process()

            if not rows:
                return {
                    'success': True,
                    'processed': 0,
                    'skipped': 0,
                    'errors': 0,
                    'message': 'No companies to process'
                }

            results = []
            for row in rows:
                # Use company name as key if no domain
                key = row.get('domain') or row.get('company', '').lower().replace(' ', '-')
                if not key:
                    continue

                if force:
                    # Clear processed record so it will be regenerated
                    firestore_svc.clear_processed(key)
                result = self._process_single_company(row, sheets, firestore_svc, drive, gemini, docs)
                results.append(result)

            successes = sum(1 for r in results if r['status'] == 'success')
            errors = sum(1 for r in results if r['status'] == 'error')
            skipped = sum(1 for r in results if r['status'] == 'skipped')

            return {
                'success': True,
                'processed': successes,
                'skipped': skipped,
                'errors': errors,
                'results': results
            }

        except Exception as e:
            logger.error(f"Error in memo generation: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _regenerate_memo(self, identifier: str, services: Dict) -> Dict[str, Any]:
        """Regenerate a memo for a specific company (by domain or company name)."""
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            gemini = services['gemini']
            docs = services['docs']

            # Clean up identifier (could be domain or company name)
            clean_id = identifier.lower().strip()
            clean_id = re.sub(r'^https?://', '', clean_id)
            clean_id = re.sub(r'^www\.', '', clean_id)
            clean_id = re.sub(r'/.*$', '', clean_id)

            # Find the company in the sheet - try by domain first, then by name
            result = sheets.service.spreadsheets().values().get(
                spreadsheetId=sheets.spreadsheet_id,
                range='Index!A:D'
            ).execute()

            values = result.get('values', [])
            company = None
            clean_domain = None
            row_number = None
            source = ''

            # First pass: try to match by domain
            for i, row in enumerate(values[1:], start=2):
                if len(row) > 1 and row[1].strip():
                    existing_domain = row[1].lower().strip()
                    if existing_domain == clean_id:
                        company = row[0]
                        clean_domain = existing_domain
                        row_number = i
                        source = row[3].strip() if len(row) > 3 else ''
                        break

            # Second pass: try to match by company name (if no domain match)
            if not company:
                for i, row in enumerate(values[1:], start=2):
                    if len(row) > 0:
                        existing_name = row[0].lower().strip()
                        if existing_name == clean_id or existing_name == clean_id.replace('.com', '').replace('.io', '').replace('.ai', ''):
                            company = row[0]
                            clean_domain = row[1].strip() if len(row) > 1 else ''
                            row_number = i
                            source = row[3].strip() if len(row) > 3 else ''
                            break

            if not company:
                return {
                    'success': False,
                    'error': f"Company '{identifier}' not found in the sheet (searched by domain and name)"
                }

            # Use company name as key if no domain
            firestore_key = clean_domain if clean_domain else company.lower().replace(' ', '-')
            folder_domain = clean_domain if clean_domain else 'no-domain'

            # Clear the processed record
            firestore_svc.clear_processed(firestore_key)

            # Create new folder and document (reuses existing folder if found)
            folder_id = drive.create_folder(company, folder_domain)
            doc_id = drive.create_document(folder_id, company)

            # Get stored YC company data if available
            yc_data = firestore_svc.get_yc_company_data(company)

            # Get relationship data from forwarded emails
            relationship_data = firestore_svc.get_relationship_data(domain=clean_domain, company_name=company)

            # Research the company (pass source for YC-enhanced search)
            research_svc = ResearchService()
            research = research_svc.research_company(company, clean_domain, source=source)
            research_context = research_svc.format_research_context(
                research, yc_data=yc_data, relationship_data=relationship_data
            )

            # Generate new memo with research context
            memo_content = gemini.generate_memo(company, clean_domain or 'Unknown', research_context=research_context)
            docs.insert_text(doc_id, memo_content)

            # Mark as processed again
            firestore_svc.mark_processed(firestore_key, company, doc_id, folder_id)

            # Update sheet status
            try:
                sheets.update_status(row_number, "Memo Regenerated")
            except Exception:
                pass

            logger.info(f"Regenerated memo for {company} ({clean_domain or 'no domain'})")

            return {
                'success': True,
                'company': company,
                'domain': clean_domain,
                'doc_id': doc_id
            }

        except Exception as e:
            logger.error(f"Error regenerating memo: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _analyze_thread(self, email_body: str, services: Dict) -> Dict[str, Any]:
        """Analyze a forwarded email thread and create/update relationship timeline."""
        try:
            sheets = services['sheets']
            firestore_svc = services['firestore']
            drive = services['drive']
            docs = services['docs']

            # Parse the email thread to extract individual messages
            new_messages = self._parse_email_thread(email_body)

            if not new_messages:
                return {
                    'success': False,
                    'error': 'Could not parse any emails from the forwarded thread'
                }

            # Extract domain from the email addresses
            domain = self._extract_domain_from_messages(new_messages)

            if not domain:
                return {
                    'success': False,
                    'error': 'Could not determine the domain from the email thread'
                }

            # Check if we have an existing relationship record
            existing = self._get_relationship(firestore_svc, domain)

            if existing:
                # Merge new messages with existing ones
                existing_messages = existing.get('raw_messages', [])
                all_messages = self._merge_messages(existing_messages, new_messages)
                doc_id = existing.get('doc_id')
                folder_id = existing.get('folder_id')
                company_name = existing.get('company_name', domain)
            else:
                all_messages = new_messages
                doc_id = None
                folder_id = None
                company_name = None

            # Use Gemini to create timeline and summary from ALL messages
            analysis = self._generate_relationship_analysis(all_messages, domain)

            if not company_name:
                company_name = analysis.get('company_name', domain)

            # Find or create the company folder
            if not folder_id:
                folder_id = drive.find_existing_folder(company_name, domain)
                if not folder_id:
                    folder_id = drive.create_folder(company_name, domain)
                    # Ensure company exists in Index sheet
                    sheets.add_company(company_name, domain)

            # Create or update the Timeline doc
            if doc_id:
                # Update existing doc by clearing and rewriting
                doc_id = self._update_timeline_doc(docs, doc_id, company_name, analysis)
            else:
                doc_id = self._create_timeline_doc(drive, docs, folder_id, company_name, analysis)

            # Store/update in Firestore
            self._store_relationship(firestore_svc, domain, all_messages, analysis, doc_id, folder_id, company_name)

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

    def _parse_email_thread(self, email_body: str) -> List[Dict[str, str]]:
        """Parse a forwarded email thread into individual messages."""
        messages = []

        # Common patterns for forwarded email headers
        # Pattern 1: "---------- Forwarded message ---------"
        # Pattern 2: "From: ... Date: ... Subject: ..."
        # Pattern 3: "On Mon, Jan 1, 2024 at 10:00 AM Name <email> wrote:"

        # Split by forwarded message markers
        forwarded_pattern = r'-{5,}\s*Forwarded message\s*-{5,}'
        parts = re.split(forwarded_pattern, email_body, flags=re.IGNORECASE)

        # Also try splitting by "On ... wrote:" pattern
        wrote_pattern = r'On\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[^<]+<[^>]+>\s*wrote:'

        for part in parts:
            # Try to extract email metadata
            sub_messages = self._extract_messages_from_part(part)
            messages.extend(sub_messages)

        # If no messages found with standard parsing, treat as single message
        if not messages and email_body.strip():
            # Try to extract at least the from/date/subject from anywhere
            from_match = re.search(r'From:\s*([^\n]+)', email_body)
            date_match = re.search(r'Date:\s*([^\n]+)', email_body)
            subject_match = re.search(r'Subject:\s*([^\n]+)', email_body)

            messages.append({
                'from': from_match.group(1).strip() if from_match else 'Unknown',
                'date': date_match.group(1).strip() if date_match else 'Unknown',
                'subject': subject_match.group(1).strip() if subject_match else 'Unknown',
                'body': email_body.strip()
            })

        return messages

    def _extract_messages_from_part(self, text: str) -> List[Dict[str, str]]:
        """Extract individual email messages from a text block."""
        messages = []

        # Pattern for email headers block
        header_pattern = r'From:\s*([^\n]+)\n(?:.*?Date:\s*([^\n]+))?(?:.*?Subject:\s*([^\n]+))?'

        # Find all header blocks
        matches = list(re.finditer(header_pattern, text, re.DOTALL | re.IGNORECASE))

        for i, match in enumerate(matches):
            from_addr = match.group(1).strip() if match.group(1) else 'Unknown'
            date = match.group(2).strip() if match.group(2) else 'Unknown'
            subject = match.group(3).strip() if match.group(3) else 'Unknown'

            # Get body until next header or end
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()

            # Clean up body - remove quoted text markers
            body = re.sub(r'^>\s*', '', body, flags=re.MULTILINE)

            if from_addr != 'Unknown' or body:
                messages.append({
                    'from': from_addr,
                    'date': date,
                    'subject': subject,
                    'body': body[:2000]  # Limit body size
                })

        return messages

    def _extract_domain_from_messages(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """Extract the primary external domain from email messages."""
        domains = []

        for msg in messages:
            from_addr = msg.get('from', '')
            # Extract email address
            email_match = re.search(r'[\w\.-]+@([\w\.-]+)', from_addr)
            if email_match:
                domain = email_match.group(1).lower()
                # Skip common email providers and internal domains
                skip_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
                               'googlemail.com', 'icloud.com', 'me.com', 'friale.com']
                if domain not in skip_domains:
                    domains.append(domain)

        # Return most common external domain
        if domains:
            return Counter(domains).most_common(1)[0][0]
        return None

    def _generate_relationship_analysis(self, messages: List[Dict[str, str]], domain: str) -> Dict[str, Any]:
        """Use Gemini to generate relationship timeline and summary."""
        # Format messages for the prompt
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
    "context": "How/why they made the introduction (e.g., 'Mutual connection from Stanford', 'Met at TechCrunch Disrupt')"
  }},
  "contacts": [
    {{"name": "Person Name", "email": "email@domain.com", "role": "Their role if mentioned"}}
  ],
  "timeline": [
    {{"date": "YYYY-MM-DD or approximate", "event": "Brief description of what happened"}}
  ],
  "summary": "2-3 paragraph summary of the relationship: how it started, key discussions, current status",
  "key_topics": ["topic1", "topic2"],
  "sentiment": "positive/neutral/negative",
  "next_steps": "Any obvious next steps or follow-ups needed"
}}

IMPORTANT for introducer:
- Look for the FIRST email in the thread - often the introduction
- Look for phrases like "introducing you to", "wanted to connect you with", "meet [name]", "I'd like you to meet"
- The introducer is usually CC'd or is the sender of the first email if it's an intro
- If no clear introducer, set introducer to null

Be thorough in extracting the timeline. Include ALL significant touchpoints.
Sort timeline chronologically (oldest first).
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
            # Clean markdown if present
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

    def _get_relationship(self, firestore_svc, domain: str) -> Optional[Dict[str, Any]]:
        """Get existing relationship data from Firestore."""
        normalized = domain.lower().strip()
        doc_ref = firestore_svc.db.collection('relationships').document(normalized)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def _merge_messages(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """Merge new messages with existing ones, avoiding duplicates."""
        # Create a set of existing message signatures for deduplication
        existing_sigs = set()
        for msg in existing:
            sig = f"{msg.get('from', '')}|{msg.get('date', '')}|{msg.get('subject', '')}"
            existing_sigs.add(sig)

        merged = list(existing)
        for msg in new:
            sig = f"{msg.get('from', '')}|{msg.get('date', '')}|{msg.get('subject', '')}"
            if sig not in existing_sigs:
                merged.append(msg)
                existing_sigs.add(sig)

        return merged

    def _format_timeline_content(self, company_name: str, analysis: Dict[str, Any]) -> str:
        """Format the timeline document content."""
        # Introduction section
        introducer = analysis.get('introducer') or {}
        if introducer and introducer.get('name'):
            intro_text = f"**{introducer.get('name', 'Unknown')}**"
            if introducer.get('email'):
                intro_text += f" ({introducer.get('email')})"
            if introducer.get('context'):
                intro_text += f"\n{introducer.get('context')}"
        else:
            intro_text = "No introducer identified"

        # Contacts section
        contacts_text = "\n".join([
            f"- **{c.get('name', 'Unknown')}** ({c.get('email', '')}) - {c.get('role', 'Unknown role')}"
            for c in analysis.get('contacts', [])
        ]) or "No contacts identified"

        # Timeline section
        timeline_text = "\n".join([
            f"- **{t.get('date', 'Unknown date')}**: {t.get('event', '')}"
            for t in analysis.get('timeline', [])
        ]) or "No timeline events identified"

        # Topics section
        topics_text = ", ".join(analysis.get('key_topics', [])) or "None identified"

        content = f"""# Timeline: {company_name}

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
        return content

    def _create_timeline_doc(self, drive, docs, folder_id: str, company_name: str,
                            analysis: Dict[str, Any]) -> str:
        """Create a new Timeline doc in the company folder."""
        # Create document in the company folder
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
        """Update an existing Timeline doc by clearing and rewriting content."""
        try:
            # Get the document to find current content length
            doc = docs.service.documents().get(documentId=doc_id).execute()
            content_end = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)

            # Delete all content (except the implicit newline at index 1)
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

            # Insert new content
            content = self._format_timeline_content(company_name, analysis)
            docs.insert_text(doc_id, content)

            logger.info(f"Updated Timeline doc {doc_id}")
            return doc_id

        except Exception as e:
            logger.error(f"Error updating timeline doc: {e}", exc_info=True)
            raise

    def _store_relationship(self, firestore_svc, domain: str, messages: List[Dict],
                           analysis: Dict[str, Any], doc_id: str, folder_id: str,
                           company_name: str):
        """Store relationship data in Firestore."""
        normalized = domain.lower().strip()
        doc_ref = firestore_svc.db.collection('relationships').document(normalized)

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
            'raw_messages': messages,  # Store raw messages for merging later
            'analyzed_at': firestore_module.SERVER_TIMESTAMP
        })

        logger.info(f"Stored relationship data for {domain}")

    def _scrape_yc_batch(self, batch: str, services: Dict, max_pages: int = None) -> Dict[str, Any]:
        """Scrape YC Bookface for companies in a batch and add to sheet."""
        try:
            if not config.bookface_cookie:
                return {'success': False, 'error': 'Bookface cookie not configured'}

            bookface = BookfaceService(config.bookface_cookie)
            return bookface.scrape_and_add_companies(
                services['sheets'],
                batch,
                max_pages=max_pages,
                firestore_svc=services.get('firestore')
            )

        except Exception as e:
            logger.error(f"Error scraping YC batch: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _summarize_company_updates(self, company: str, domain: str, services: Dict) -> Dict[str, Any]:
        """Summarize update emails from a company.

        Args:
            company: Company name (optional if domain provided)
            domain: Company domain (optional if company provided)
            services: Dict of service instances (must include 'gmail', 'sheets', 'drive', 'docs', 'gemini')
        """
        try:
            # Resolve domain from company name if needed
            resolved_domain = domain
            resolved_company = company

            if not resolved_domain and company:
                # Look up company in sheet to get domain
                sheets = services['sheets']
                companies = sheets.get_all_companies()

                for c in companies:
                    if c.get('company', '').lower() == company.lower():
                        resolved_domain = c.get('domain', '')
                        resolved_company = c.get('company', company)
                        break

                # If still no domain, try company.com as fallback
                if not resolved_domain:
                    resolved_domain = f"{company.lower().replace(' ', '')}.com"

            if not resolved_domain:
                return {'success': False, 'error': 'Could not determine company domain'}

            # Clean domain
            resolved_domain = re.sub(r'^https?://', '', resolved_domain.lower().strip())
            resolved_domain = re.sub(r'^www\.', '', resolved_domain)
            resolved_domain = re.sub(r'/.*$', '', resolved_domain)

            # Check if gmail service is available
            gmail = services.get('gmail')
            if not gmail:
                return {'success': False, 'error': 'Gmail service not available'}

            # Build Gmail query to search for all emails from this company's domain
            query = f'from:@{resolved_domain}'

            logger.info(f"Searching for update emails with query: {query}")

            # Fetch emails via Gmail API
            emails = gmail.fetch_emails(
                query=query,
                max_results=100
            )

            if not emails:
                return {
                    'success': True,
                    'company': resolved_company,
                    'domain': resolved_domain,
                    'email_count': 0,
                    'summary': f'No update emails found from {resolved_domain}',
                    'doc_id': None
                }

            # Sort emails by date (oldest first for timeline)
            emails.sort(key=lambda e: e.get('parsed_date') or e.get('date', ''))

            # Get date range
            first_date = emails[0].get('date', 'Unknown')
            last_date = emails[-1].get('date', 'Unknown')

            # Generate summary with Gemini
            summary_result = self._generate_updates_summary(emails, resolved_company, resolved_domain)

            # Create or update the summary document
            drive = services['drive']
            docs = services['docs']

            # Find or create company folder
            folder_id = drive.find_existing_folder(resolved_company, resolved_domain)
            if not folder_id:
                folder_id = drive.create_folder(resolved_company, resolved_domain)

            # Create "Updates Summary" document
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

            # Format and insert content
            content = self._format_updates_summary_content(
                resolved_company, resolved_domain, emails, summary_result, first_date, last_date
            )
            docs.insert_text(doc_id, content)

            logger.info(f"Created updates summary for {resolved_company} ({resolved_domain}): {len(emails)} emails")

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

    def _generate_updates_summary(self, emails: List[Dict], company: str, domain: str) -> Dict[str, Any]:
        """Use Gemini to generate a summary of update emails."""
        # Sort emails by date, most recent first
        sorted_emails = sorted(
            emails,
            key=lambda e: e.get('parsed_date') or e.get('date', ''),
            reverse=True
        )

        # Format emails for the prompt - most recent first, with emphasis markers
        email_sections = []
        for i, e in enumerate(sorted_emails[:50]):  # Limit to most recent 50 emails
            recency_label = ""
            if i == 0:
                recency_label = "[MOST RECENT - PRIMARY FOCUS] "
            elif i < 5:
                recency_label = "[RECENT] "
            elif i < 15:
                recency_label = "[OLDER] "
            else:
                recency_label = "[HISTORICAL CONTEXT] "

            email_sections.append(
                f"{recency_label}Date: {e.get('date', 'Unknown')}\n"
                f"Subject: {e.get('subject', 'No subject')}\n\n"
                f"{e.get('body', '')[:3000]}"
            )

        emails_text = "\n\n---\n\n".join(email_sections)

        prompt = f"""Analyze these {len(emails)} emails from {company} ({domain}) and create a comprehensive summary of how the company is doing.

CRITICAL: Prioritize recent information heavily. The MOST RECENT email should carry the most weight in your analysis - it represents the current state of the company. Older emails provide historical context but should not overshadow recent developments.

EMAILS (ordered from most recent to oldest):
{emails_text[:30000]}

Create a JSON response with:
{{
  "summary": "2-3 paragraph executive summary focused primarily on the MOST RECENT updates. What is the company's current status? What have they accomplished recently? Use older emails only to provide context on trajectory and history.",
  "current_status": "1-2 sentence summary of where the company stands RIGHT NOW based on the most recent email(s)",
  "highlights": [
    "Most important recent highlight or achievement",
    "Second most important recent highlight",
    "..."
  ],
  "product_updates": [
    "Recent product or feature update 1",
    "..."
  ],
  "business_updates": [
    "Recent business metric, funding, hiring, or partnership update 1",
    "..."
  ],
  "themes": ["recurring theme 1", "theme 2"],
  "sentiment": "positive/neutral/negative/mixed",
  "trajectory": "growing/stable/declining/unclear",
  "notable_metrics": [
    {{"metric": "Revenue", "value": "$X", "context": "optional context", "date": "when reported"}},
    ...
  ]
}}

Focus on extracting concrete facts, metrics, and achievements. Prioritize recency. Be specific.
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
            # Clean markdown if present
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

    def _format_updates_summary_content(self, company: str, domain: str, emails: List[Dict],
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

        # Add current status section if available
        current_status_section = ""
        if current_status:
            current_status_section = f"\n## Current Status\n{current_status}\n"

        content = f"""# Updates Summary: {company}

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
        return content

    def _process_single_company(self, row: Dict, sheets, firestore_svc, drive, gemini, docs) -> Dict:
        """Process a single company row."""
        company = row['company']
        domain = row.get('domain', '')
        row_number = row['row_number']
        source = row.get('source', '')  # e.g., 'W26' for YC batch

        # Use company name as key if no domain
        firestore_key = domain if domain else company.lower().replace(' ', '-')

        try:
            if firestore_svc.is_processed(firestore_key):
                return {'company': company, 'domain': domain, 'status': 'skipped', 'reason': 'already_processed'}

            # Create folder - use company name if no domain
            folder_name_domain = domain if domain else 'no-domain'
            folder_id = drive.create_folder(company, folder_name_domain)
            doc_id = drive.create_document(folder_id, company)

            # Get stored YC company data if available (from Bookface scraping)
            yc_data = firestore_svc.get_yc_company_data(company)

            # Get relationship data from forwarded emails
            relationship_data = firestore_svc.get_relationship_data(domain=domain, company_name=company)

            # Research the company - pass source for YC-enhanced search
            research_svc = ResearchService()
            research = research_svc.research_company(company, domain, source=source)
            research_context = research_svc.format_research_context(
                research, yc_data=yc_data, relationship_data=relationship_data
            )

            # Generate memo with research context
            memo_content = gemini.generate_memo(company, domain or 'Unknown', research_context=research_context)
            docs.insert_text(doc_id, memo_content)
            firestore_svc.mark_processed(firestore_key, company, doc_id, folder_id)

            try:
                sheets.update_status(row_number, "Memo Created")
            except Exception:
                pass

            return {'company': company, 'domain': domain, 'status': 'success', 'doc_id': doc_id}

        except Exception as e:
            logger.error(f"Error processing {company}: {e}", exc_info=True)
            return {'company': company, 'domain': domain, 'status': 'error', 'error': str(e)}

    def _format_response(self, decision: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Format the response text for email reply."""
        action = decision.get('action', 'NONE')

        # Check for explicit boolean True (not truthy numbers like skipped count)
        if result.get('skipped') is True:
            actions_list = '\n'.join(
                f"• {val['description']}"
                for key, val in self.ACTIONS.items()
                if key != 'NONE'
            )
            return f"""I received your email but couldn't identify a specific action to take.

**My interpretation:** {decision.get('reasoning', 'Unknown')}

**Available commands:**
{actions_list}

Just reply with what you'd like me to do."""

        if not result.get('success'):
            return f"""I tried to run **{action}** but encountered an error:

```
{result.get('error', 'Unknown error')}
```

You might want to check the logs or try again."""

        # Success responses
        if action == 'ADD_COMPANY':
            return f"""✓ **Company added to deal flow!**

**Company:** {result.get('company')}
**Domain:** {result.get('domain') or '(none)'}

The memo will be generated on the next run. Reply "generate memos" to process it now."""

        elif action == 'UPDATE_COMPANY':
            updates_list = result.get('updates', [])
            updates_str = '\n'.join(f"  - {u}" for u in updates_list) if updates_list else "  - No changes needed"

            response = f"""✓ **Company updated!**

**Company:** {result.get('company')}
**Changes:**
{updates_str}"""

            # If there was a chained action, append its result
            chained_result = result.get('chained_result')
            if chained_result:
                chained_action = result.get('chained_action', '')
                if chained_action == 'GENERATE_MEMOS' and chained_result.get('success'):
                    processed = chained_result.get('processed', 0)
                    if processed > 0:
                        response += f"\n\n✓ **Also processed {processed} memo(s)!**"
                        if chained_result.get('results'):
                            for r in chained_result['results']:
                                if r.get('status') == 'success':
                                    doc_url = f"https://docs.google.com/document/d/{r['doc_id']}/edit"
                                    response += f"\n  → {r['company']}: {doc_url}"
                elif chained_action == 'REGENERATE_MEMO' and chained_result.get('success'):
                    doc_url = f"https://docs.google.com/document/d/{chained_result.get('doc_id')}/edit"
                    response += f"\n\n✓ **Memo regenerated:** {doc_url}"

            return response

        elif action == 'GENERATE_MEMOS':
            if result.get('processed', 0) == 0 and result.get('errors', 0) == 0:
                return "No new companies to process. All companies in the sheet have already been processed."

            details = ''
            if result.get('results'):
                detail_lines = []
                for r in result['results']:
                    if r['status'] == 'success':
                        doc_url = f"https://docs.google.com/document/d/{r['doc_id']}/edit"
                        detail_lines.append(f"• ✓ {r['company']} ({r['domain']})\n  → {doc_url}")
                    elif r['status'] == 'skipped':
                        detail_lines.append(f"• ⊘ {r['company']} - already processed")
                    else:
                        detail_lines.append(f"• ✗ {r['company']} - {r.get('error', 'error')}")
                details = '\n\n**Details:**\n' + '\n'.join(detail_lines)

            return f"""Done! Here's what happened:

✓ **Processed:** {result.get('processed', 0)}
⊘ **Skipped:** {result.get('skipped', 0)}
✗ **Errors:** {result.get('errors', 0)}
{details}

Let me know if you need anything else."""

        elif action == 'REGENERATE_MEMO':
            doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
            domain_str = result.get('domain') or '(no domain)'
            return f"""✓ **Memo regenerated!**

**Company:** {result.get('company')}
**Domain:** {domain_str}

**New memo:** {doc_url}

Let me know if you need any other changes."""

        elif action == 'ANALYZE_THREAD':
            doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
            summary = result.get('summary', '')
            # Truncate summary for email if too long
            if len(summary) > 500:
                summary = summary[:500] + '...'

            # Check if this was an update
            updated = result.get('updated', False)
            status = "Timeline updated!" if updated else "Timeline created!"

            # Introducer info
            introducer = result.get('introducer') or {}
            intro_text = ""
            if introducer and introducer.get('name'):
                intro_text = f"\n**Introduced by:** {introducer.get('name', 'Unknown')}"
                if introducer.get('context'):
                    intro_text += f" ({introducer.get('context')})"

            # Message count info
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

        elif action == 'SUMMARIZE_UPDATES':
            company = result.get('company', 'Unknown')
            domain = result.get('domain', '')
            email_count = result.get('email_count', 0)

            if email_count == 0:
                return f"""No update emails found from **{company}** ({domain}).

Make sure the company sends updates to updates@friale.com."""

            doc_url = f"https://docs.google.com/document/d/{result.get('doc_id')}/edit"
            date_range = result.get('date_range', {})
            summary = result.get('summary', '')

            # Truncate summary for email if too long
            if len(summary) > 600:
                summary = summary[:600] + '...'

            # Format highlights
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

        elif action == 'SCRAPE_YC':
            batch = result.get('batch', 'W26')
            added = result.get('added', 0)
            skipped = result.get('skipped', 0)
            errors = result.get('errors', 0)

            # List added companies (limit to first 10)
            added_companies = result.get('added_companies', [])
            if added_companies:
                companies_list = '\n'.join(f"  - {c}" for c in added_companies[:10])
                if len(added_companies) > 10:
                    companies_list += f"\n  - ... and {len(added_companies) - 10} more"
            else:
                companies_list = "  (none)"

            return f"""✓ **YC {batch} companies imported!**

**Added:** {added}
**Skipped (already exists):** {skipped}
**Errors:** {errors}

**New companies:**
{companies_list}

Reply "generate memos" to create memos for the new companies."""

        elif action == 'HEALTH_CHECK':
            return "✓ **All systems operational!** The service is running properly."

        else:
            return f"Action **{action}** completed successfully."
