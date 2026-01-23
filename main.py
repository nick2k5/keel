"""Main application for processing investment memos."""
import logging
import sys
from flask import Flask, request, jsonify
from google.oauth2 import service_account
from google.auth import default
from config import config
from services import (
    SheetsService,
    FirestoreService,
    DriveService,
    GeminiService,
    DocsService,
    EmailAgentService
)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def get_credentials():
    """Get Google Cloud credentials with required scopes."""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/documents'
    ]

    # Use default credentials (service account in Cloud Run)
    credentials, project = default(scopes=scopes)
    return credentials


def process_company(row: dict, sheets_service, firestore_service, drive_service,
                    gemini_service, docs_service) -> dict:
    """Process a single company row."""
    company = row['company']
    domain = row['domain']
    row_number = row['row_number']

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

        # Generate memo with Gemini
        memo_content = gemini_service.generate_memo(company, domain)

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
            '/health': 'GET - Health check'
        }
    }), 200


if __name__ == '__main__':
    # For local development
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
