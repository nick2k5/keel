"""Main application for processing investment memos.

This is the refactored version using the new service architecture.
"""
import logging
import sys

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from config import config
from services import (
    ServiceFactory,
    get_gmail_credentials,
    EmailAgentService,
    GmailService,
    FirestoreService,
)
from services.google.gmail import InboxSyncService
from actions import GenerateMemosAction

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/run', methods=['POST'])
def run_processing():
    """Main endpoint to trigger memo generation."""
    logger.info("Received POST /run request")

    try:
        factory = ServiceFactory.create()
        services = factory.create_all()

        action = GenerateMemosAction(services)
        result = action.execute({'force': False})

        return jsonify({
            'status': 'success',
            'message': f"Processed {result.get('processed', 0)} companies",
            **result
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

        # Create services
        factory = ServiceFactory.create()
        services = factory.create_all()

        # Add Gmail service for SUMMARIZE_UPDATES action
        try:
            gmail_credentials = get_gmail_credentials('nick@friale.com')
            services['gmail'] = GmailService(
                credentials=gmail_credentials,
                user_email='nick@friale.com'
            )
        except Exception as e:
            logger.warning(f"Could not initialize Gmail service: {e}")

        # Process email
        email_agent = EmailAgentService(services)
        result = email_agent.process_email(email_data)

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
            'reply_text': f"Sorry, I encountered an error: {str(e)}"
        }), 500


@app.route('/sync-inbox', methods=['POST'])
def sync_inbox():
    """Sync emails from Gmail inbox for research and processing."""
    logger.info("Received POST /sync-inbox request")

    try:
        data = request.get_json() or {}

        user_email = data.get('user_email')
        query = data.get('query')
        max_emails = data.get('max_emails', 50)
        days_back = data.get('days_back', 7)
        process_with_agent = data.get('process_with_agent', False)
        store_for_research = data.get('store_for_research', True)

        if not user_email:
            return jsonify({
                'status': 'error',
                'message': 'user_email is required for Gmail API access'
            }), 400

        gmail_credentials = get_gmail_credentials(user_email)
        gmail_service = GmailService(credentials=gmail_credentials, user_email=user_email)
        firestore_service = FirestoreService()

        email_agent = None
        services = None
        if process_with_agent:
            factory = ServiceFactory.create()
            services = factory.create_all()
            email_agent = EmailAgentService(services)

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
        'version': '2.0',
        'endpoints': {
            '/run': 'POST - Process companies from sheet',
            '/email': 'POST - Process email with AI agent',
            '/sync-inbox': 'POST - Sync emails from Gmail inbox',
            '/emails/search': 'GET - Search stored emails (params: q, domain, limit)',
            '/health': 'GET - Health check'
        }
    }), 200


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
