# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Keel is a Google Cloud Run service that automates investment memo generation for venture capital deal flow. It reads companies from a Google Sheet, performs deep web research, uses Google Gemini to generate memo content, and creates structured Google Docs in a Shared Drive. It also provides an email-based interface for adding companies, updating data, and analyzing relationship threads.

## Architecture

### Core Flow
1. **Sheet Processing** (`services/google/sheets.py:SheetsService`) - Reads "Index" tab, identifies rows where Status is empty or "New"
2. **Idempotency Check** (`services/google/firestore.py:FirestoreService`) - Uses Firestore with normalized domain as key to prevent duplicate processing
3. **Drive Operations** (`services/google/drive.py:DriveService`) - Creates folder and blank document (requires `supportsAllDrives=true` for Shared Drive)
4. **Research** (`services/research.py:ResearchService`) - Crawls company website, performs web searches, scrapes external sources
5. **Content Generation** (`services/google/gemini.py:GeminiService`) - Calls Vertex AI Gemini API with research context to generate memo content
6. **Document Update** (`services/google/docs.py:DocsService`) - Inserts formatted markdown content into the document
7. **Status Tracking** - Updates Firestore and optionally Sheet status to "Memo Created"

### Email Agent Flow
1. **Email Processing** (`services/email_agent.py:EmailAgentService`) - Receives email via `/email` endpoint
2. **Action Detection** - Uses Gemini to determine intent (add company, generate memos, update company, etc.)
3. **Execution** - Executes the detected action using appropriate services
4. **Response** - Returns formatted response for email reply

### Key Design Decisions

**Email Domain Security**: The `/email` endpoint only accepts emails from `@friale.com` senders. All other domains are rejected with 403 Forbidden. This is enforced in `main.py` before any processing occurs.

**ServiceFactory Pattern**: All Google services are instantiated via `ServiceFactory.create().create_all()` which returns a dict of initialized services. This centralizes credential management and makes testing easier.

**Action-Based Architecture**: Business logic is encapsulated in action classes (`actions/*.py`). Each action inherits from `BaseAction` and implements `execute()` and `format_response()`. The `EmailAgentService` routes emails to the appropriate action via `EmailRouter`.

**Shared Drive Support**: All Drive API calls include `supportsAllDrives=true`. Without this parameter, operations on Shared Drive resources will fail with 404 errors.

**Idempotency**: Domain is normalized (lowercase, trimmed) and used as Firestore document ID. This prevents reprocessing if the service is invoked multiple times.

**Deep Research**: Before generating memos, the service crawls the company website, performs multiple search queries, and scrapes relevant external sources (TechCrunch, Crunchbase, etc.) to gather comprehensive context.

**Structured Logging**: All operations use Python's logging module with INFO level. Logs include company/domain context for traceability.

## Development Commands

### Local Development

Run locally (requires service account credentials):
```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account-key.json"
export GCP_PROJECT_ID="your-project-id"
export SPREADSHEET_ID="your-sheet-id"
export DRIVE_PARENT_FOLDER_ID="your-folder-id"

python main.py
```

Test the endpoints:
```bash
# Run memo generation
curl -X POST http://localhost:8080/run

# Health check
curl http://localhost:8080/health

# Email agent (must be from @friale.com)
curl -X POST http://localhost:8080/email \
  -H "Content-Type: application/json" \
  -d '{"from":"nick@friale.com","subject":"Add company","body":"Add Acme Inc (acme.com)"}'
```

### Build and Test Docker Image

Build locally:
```bash
docker build -t keel-memo-generator .
```

Run container:
```bash
docker run -p 8080:8080 \
  -e GCP_PROJECT_ID="..." \
  -e SPREADSHEET_ID="..." \
  -e DRIVE_PARENT_FOLDER_ID="..." \
  keel-memo-generator
```

### Deploy to Cloud Run

Deploy with source:
```bash
gcloud run deploy keel-memo-generator \
  --source . \
  --region us-central1 \
  --set-env-vars "GCP_PROJECT_ID=your-project-id,SPREADSHEET_ID=...,..."
```

View logs:
```bash
gcloud run services logs read keel-memo-generator --region us-central1 --limit 50
```

Tail logs in real-time:
```bash
gcloud run services logs tail keel-memo-generator --region us-central1
```

### Invoke Service

```bash
SERVICE_URL=$(gcloud run services describe keel-memo-generator --region us-central1 --format 'value(status.url)')
curl -X POST ${SERVICE_URL}/run
```

## File Structure

- `main.py` - Flask application with `/run`, `/email`, `/sync-inbox`, and `/health` endpoints
- `config.py` - Configuration management, environment variables, Secret Manager integration
- `actions/` - Business logic actions (one class per action)
  - `__init__.py` - ACTIONS registry and exports
  - `base.py` - BaseAction class that all actions inherit from
  - `add_company.py` - AddCompanyAction
  - `analyze_thread.py` - AnalyzeThreadAction for relationship timeline extraction
  - `generate_memos.py` - GenerateMemosAction for batch memo generation
  - `health_check.py` - HealthCheckAction
  - `regenerate_memo.py` - RegenerateMemoAction
  - `scrape_yc.py` - ScrapeYCAction for YC Bookface imports
  - `summarize_updates.py` - SummarizeUpdatesAction for email digests
  - `update_company.py` - UpdateCompanyAction
- `core/` - Core infrastructure
  - `email_router.py` - EmailRouter for routing emails to actions via Gemini
- `services/` - Service layer
  - `__init__.py` - ServiceFactory and re-exports for backward compatibility
  - `email_agent.py` - EmailAgentService (thin wrapper that delegates to actions)
  - `research.py` - ResearchService for deep web research
  - `bookface.py` - BookfaceService for YC Bookface scraping
  - `google/` - Google API services
    - `credentials.py` - Credential management and ServiceFactory
    - `sheets.py` - SheetsService for Google Sheets operations
    - `firestore.py` - FirestoreService for idempotency tracking
    - `drive.py` - DriveService for folder/document creation
    - `docs.py` - DocsService for document content insertion
    - `gemini.py` - GeminiService for Gemini-powered content generation
    - `gmail.py` - GmailService and InboxSyncService for Gmail API
- `tests/` - Test suite (pytest)
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration for Cloud Run
- `DEPLOY.md` - Comprehensive deployment guide with IAM, APIs, and Cloud Scheduler setup

## Common Modifications

### Adding New Memo Fields

Update `services/google/gemini.py:GeminiService.generate_memo()` prompt to request the new field. The document is created blank and content is inserted directly as formatted markdown.

### Changing Processing Logic

Memo generation logic is in `actions/generate_memos.py:GenerateMemosAction`. The `/run` endpoint instantiates this action via `ServiceFactory`. For parallel processing, consider using Cloud Tasks or Cloud Run Jobs.

### Modifying Idempotency Key

Change `services/google/firestore.py:FirestoreService.normalize_domain()` to use a different key format (e.g., include company name).

### Adjusting Sheet Columns

Update `services/google/sheets.py:SheetsService.get_rows_to_process()` to parse different columns or ranges.

### Adding Email Agent Actions

1. Create a new action class in `actions/` inheriting from `BaseAction`
2. Implement `execute(self, params: dict) -> dict` with business logic
3. Implement `format_response(self, result: dict) -> str` for email reply text
4. Register the action in `actions/__init__.py` ACTIONS dict with name, description, and class

## Environment Variables

Required:
- `GCP_PROJECT_ID` - Google Cloud project
- `SPREADSHEET_ID` - Google Sheet ID containing company data
- `DRIVE_PARENT_FOLDER_ID` - Shared Drive folder where company folders are created

Optional:
- `VERTEX_AI_REGION` - Vertex AI region (default: `us-central1`)
- `FIRESTORE_COLLECTION` - Firestore collection name (default: `processed_domains`)
- `SERPER_API_KEY` - Serper.dev API key for Google search (enables web search in research)
- `BOOKFACE_COOKIE` - YC Bookface session cookie (enables YC batch scraping)
- `LINKEDIN_COOKIE` - LinkedIn session cookie (enables LinkedIn profile scraping)
- `PORT` - Server port (default: 8080)

## Google Cloud Dependencies

**Required APIs**:
- Cloud Run API
- Google Sheets API
- Google Drive API
- Google Docs API
- Firestore API
- Vertex AI API

**IAM Requirements**:
- Service account needs `roles/aiplatform.user` for Vertex AI
- Service account needs `roles/datastore.user` for Firestore
- Service account must be granted Editor access to the Google Sheet
- Service account must be granted Content Manager access to the Shared Drive

## Email Agent Commands

The `/email` endpoint accepts POST requests with email data and executes commands:

- **GENERATE_MEMOS** - "run memos", "generate", "process" → Generate memos for unprocessed companies
- **ADD_COMPANY** - "add [company] ([domain])" → Add a new company to the sheet
- **UPDATE_COMPANY** - "domain is [url]" → Update/correct a company's domain
- **REGENERATE_MEMO** - "regenerate [company/domain]" → Regenerate a specific memo
- **ANALYZE_THREAD** - (forwarded email) → Create relationship timeline from email thread
- **SCRAPE_YC** - "scrape YC [batch]" → Import companies from YC Bookface
- **HEALTH_CHECK** - "status", "health" → Check service health

## Gmail Inbox Sync

The `/sync-inbox` endpoint syncs emails from a Gmail inbox for research and processing.

### Setup Requirements

1. **Enable Gmail API** in your GCP project:
   ```bash
   gcloud services enable gmail.googleapis.com
   ```

2. **Configure Domain-Wide Delegation** (for service account access):
   - Go to Google Workspace Admin Console → Security → API Controls → Domain-wide Delegation
   - Add the service account's Client ID
   - Add scope: `https://www.googleapis.com/auth/gmail.readonly`

### Usage

```bash
curl -X POST ${SERVICE_URL}/sync-inbox \
  -H "Content-Type: application/json" \
  -d '{
    "user_email": "nick@friale.com",
    "query": "from:@stripe.com",
    "max_emails": 50,
    "days_back": 30,
    "store_for_research": true,
    "process_with_agent": false
  }'
```

### Parameters

- `user_email` (required) - Gmail address to sync from
- `query` - Gmail search query (e.g., "from:someone@example.com", "subject:intro")
- `max_emails` - Maximum emails to fetch (default: 50)
- `days_back` - How many days back to look (default: 7)
- `store_for_research` - Store emails in Firestore for research (default: true)
- `process_with_agent` - Process each email through EmailAgentService (default: false)

### Search Stored Emails

```bash
# Search by domain
curl "${SERVICE_URL}/emails/search?domain=stripe.com&limit=20"

# Search by term
curl "${SERVICE_URL}/emails/search?q=introduction&limit=20"
```

### Firestore Collections

- `processed_emails` - Tracks which email IDs have been processed
- `email_research` - Stores email content indexed by sender domain

## Error Handling

All service methods raise exceptions on failure. The `main.py:process_company()` function catches exceptions and returns an error result without stopping the batch. Check Cloud Run logs for detailed error traces.

## Testing Changes

When modifying the service:
1. Test locally with a test spreadsheet and Shared Drive folder
2. Deploy to a staging Cloud Run service
3. Run with a small batch of test companies
4. Verify Firestore documents are created correctly
5. Check generated Google Docs for proper content
6. Monitor logs for errors or warnings

Run tests:
```bash
source venv/bin/activate && pytest
```
