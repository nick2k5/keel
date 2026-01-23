"""Main application for processing investment memos."""
import json
import logging
import sys
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from google.auth import default
from google.cloud import secretmanager
from config import config
from services import (
    SheetsService,
    FirestoreService,
    DriveService,
    GeminiService,
    DocsService,
    EmailAgentService,
    GmailService,
    InboxSyncService
)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def get_credentials(include_gmail: bool = False):
    """Get Google Cloud credentials with required scopes.

    Args:
        include_gmail: Whether to include Gmail API scope (requires domain-wide delegation)
    """
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/documents'
    ]

    if include_gmail:
        scopes.append('https://www.googleapis.com/auth/gmail.readonly')

    # Use default credentials (service account in Cloud Run)
    credentials, project = default(scopes=scopes)
    return credentials


def get_gmail_credentials(user_email: str):
    """Get Gmail credentials with domain-wide delegation.

    This loads a dedicated service account from Secret Manager that has
    domain-wide delegation enabled for Gmail API access.

    Args:
        user_email: Email address to impersonate via delegation

    Returns:
        Credentials with delegation to the specified user
    """
    try:
        # Load service account key from Secret Manager
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{config.project_id}/secrets/keel-gmail-credentials/versions/latest"
        response = client.access_secret_version(request={"name": secret_name})
        key_data = json.loads(response.payload.data.decode('UTF-8'))

        # Create credentials with Gmail scope and delegation
        scopes = ['https://www.googleapis.com/auth/gmail.readonly']
        credentials = service_account.Credentials.from_service_account_info(
            key_data,
            scopes=scopes,
            subject=user_email  # Impersonate this user via domain-wide delegation
        )

        logger.info(f"Loaded Gmail credentials with delegation to {user_email}")
        return credentials

    except Exception as e:
        logger.error(f"Error loading Gmail credentials: {e}", exc_info=True)
        raise


def process_company(row: dict, sheets_service, firestore_service, drive_service,
                    gemini_service, docs_service) -> dict:
    """Process a single company row."""
    from services import ResearchService

    company = row['company']
    domain = row['domain']
    row_number = row['row_number']
    source = row.get('source', '')

    logger.info(f"Processing {company} ({domain})")

    try:
        # Check idempotency
        if firestore_service.is_processed(domain):
            logger.info(f"Domain {domain} already processed, skipping")
            return {
                'company': company,
                'domain': domain,
                'status': 'skipped',
                'reason': 'already_processed'
            }

        # Create folder
        folder_id = drive_service.create_folder(company, domain)

        # Create new document
        doc_id = drive_service.create_document(folder_id, company)

        # Get stored YC company data if available (from Bookface scraping)
        yc_data = firestore_service.get_yc_company_data(company)

        # Get relationship data from forwarded emails
        relationship_data = firestore_service.get_relationship_data(domain=domain, company_name=company)

        # Research the company
        research_svc = ResearchService()
        research = research_svc.research_company(company, domain, source=source)
        research_context = research_svc.format_research_context(
            research, yc_data=yc_data, relationship_data=relationship_data
        )

        # Generate memo with Gemini (with research context and web grounding)
        memo_content = gemini_service.generate_memo(company, domain, research_context=research_context)

        # Insert content into document
        docs_service.insert_text(doc_id, memo_content)

        # Mark as processed in Firestore
        firestore_service.mark_processed(domain, company, doc_id, folder_id)

        # Update Sheet status (optional)
        try:
            sheets_service.update_status(row_number, "Memo Created")
        except Exception as e:
            logger.warning(f"Failed to update sheet status: {e}")

        logger.info(f"Successfully processed {company} ({domain})")

        return {
            'company': company,
            'domain': domain,
            'status': 'success',
            'doc_id': doc_id,
            'folder_id': folder_id
        }

    except Exception as e:
        logger.error(f"Error processing {company} ({domain}): {e}", exc_info=True)
        return {
            'company': company,
            'domain': domain,
            'status': 'error',
            'error': str(e)
        }


@app.route('/run', methods=['POST'])
def run_processing():
    """Main endpoint to trigger processing."""
    logger.info("Received POST /run request")

    try:
        # Initialize credentials and services
        credentials = get_credentials()

        sheets_service = SheetsService(credentials)
        firestore_service = FirestoreService()
        drive_service = DriveService(credentials)
        gemini_service = GeminiService()
        docs_service = DocsService(credentials)

        # Get rows to process
        rows = sheets_service.get_rows_to_process()

        if not rows:
            logger.info("No rows to process")
            return jsonify({
                'status': 'success',
                'message': 'No rows to process',
                'processed': 0,
                'results': []
            }), 200

        # Process each row
        results = []
        for row in rows:
            result = process_company(
                row, sheets_service, firestore_service,
                drive_service, gemini_service, docs_service
            )
            results.append(result)

        # Count successes and errors
        successes = sum(1 for r in results if r['status'] == 'success')
        errors = sum(1 for r in results if r['status'] == 'error')
        skipped = sum(1 for r in results if r['status'] == 'skipped')

        logger.info(f"Processing complete: {successes} success, {errors} errors, {skipped} skipped")

        return jsonify({
            'status': 'success',
            'message': f'Processed {len(rows)} rows',
            'processed': successes,
            'errors': errors,
            'skipped': skipped,
            'results': results
        }), 200

    except Exception as e:
        logger.error(f"Error in /run endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/email', methods=['POST'])
def process_email():
    """Process incoming email and execute appropriate action."""
    logger.info("Received POST /email request")

    try:
        email_data = request.get_json()
        if not email_data:
            return jsonify({
                'status': 'error',
                'message': 'No email data provided'
            }), 400

        # Initialize services
        credentials = get_credentials()
        services = {
            'sheets': SheetsService(credentials),
            'firestore': FirestoreService(),
            'drive': DriveService(credentials),
            'gemini': GeminiService(),
            'docs': DocsService(credentials)
        }

        # Process email with AI agent
        email_agent = EmailAgentService()
        result = email_agent.process_email(email_data, services)

        return jsonify({
            'status': 'success',
            'action': result['decision'].get('action'),
            'reasoning': result['decision'].get('reasoning'),
            'reply_text': result['reply_text'],
            'result': result['result']
        }), 200

    except Exception as e:
        logger.error(f"Error in /email endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'reply_text': f"Sorry, I encountered an error processing your request: {str(e)}"
        }), 500


@app.route('/sync-inbox', methods=['POST'])
def sync_inbox():
    """Sync emails from Gmail inbox for research and processing."""
    logger.info("Received POST /sync-inbox request")

    try:
        data = request.get_json() or {}

        # Get parameters from request
        user_email = data.get('user_email')  # Required for service account delegation
        query = data.get('query')  # Gmail search query
        max_emails = data.get('max_emails', 50)
        days_back = data.get('days_back', 7)
        process_with_agent = data.get('process_with_agent', False)
        store_for_research = data.get('store_for_research', True)

        if not user_email:
            return jsonify({
                'status': 'error',
                'message': 'user_email is required for Gmail API access'
            }), 400

        # Get Gmail credentials with domain-wide delegation
        gmail_credentials = get_gmail_credentials(user_email)

        # Initialize services
        gmail_service = GmailService(credentials=gmail_credentials, user_email=user_email)
        firestore_service = FirestoreService()

        # Set up email agent if needed
        email_agent = None
        services = None
        if process_with_agent:
            # Get regular credentials for other Google services
            credentials = get_credentials()
            email_agent = EmailAgentService()
            services = {
                'sheets': SheetsService(credentials),
                'firestore': firestore_service,
                'drive': DriveService(credentials),
                'gemini': GeminiService(),
                'docs': DocsService(credentials)
            }

        # Create sync service and run
        sync_service = InboxSyncService(gmail_service, firestore_service, email_agent)
        result = sync_service.sync_inbox(
            query=query,
            max_emails=max_emails,
            days_back=days_back,
            process_with_agent=process_with_agent,
            store_for_research=store_for_research,
            services=services
        )

        return jsonify({
            'status': 'success',
            **result
        }), 200

    except Exception as e:
        logger.error(f"Error in /sync-inbox endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/emails/search', methods=['GET'])
def search_emails():
    """Search stored emails."""
    logger.info("Received GET /emails/search request")

    try:
        search_term = request.args.get('q', '')
        domain = request.args.get('domain')
        limit = int(request.args.get('limit', 50))

        firestore_service = FirestoreService()

        # Create a minimal gmail service just for the sync service search methods
        sync_service = InboxSyncService(None, firestore_service, None)

        if domain:
            results = sync_service.get_emails_by_domain(domain, limit=limit)
        elif search_term:
            results = sync_service.search_emails(search_term, limit=limit)
        else:
            return jsonify({
                'status': 'error',
                'message': 'Either q (search term) or domain parameter is required'
            }), 400

        return jsonify({
            'status': 'success',
            'count': len(results),
            'emails': results
        }), 200

    except Exception as e:
        logger.error(f"Error in /emails/search endpoint: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy'}), 200


@app.route('/', methods=['GET'])
def root():
    """Root endpoint."""
    return jsonify({
        'service': 'keel-memo-generator',
        'endpoints': {
            '/run': 'POST - Process companies from sheet',
            '/email': 'POST - Process email with AI agent',
            '/sync-inbox': 'POST - Sync emails from Gmail inbox',
            '/emails/search': 'GET - Search stored emails (params: q, domain, limit)',
            '/health': 'GET - Health check'
        }
    }), 200


if __name__ == '__main__':
    # For local development
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
