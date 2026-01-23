# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Keel is a Google Cloud Run service that automates investment memo generation for venture capital deal flow. It reads companies from a Google Sheet, performs deep web research, uses Google Gemini to generate memo content, and creates structured Google Docs in a Shared Drive. It also provides an email-based interface for adding companies, updating data, and analyzing relationship threads.

## Architecture

### Core Flow
1. **Sheet Processing** (`services/sheets.py:SheetsService`) - Reads "Index" tab, identifies rows where Status is empty or "New"
2. **Idempotency Check** (`services/firestore.py:FirestoreService`) - Uses Firestore with normalized domain as key to prevent duplicate processing
3. **Drive Operations** (`services/drive.py:DriveService`) - Creates folder and blank document (requires `supportsAllDrives=true` for Shared Drive)
4. **Research** (`services/research.py:ResearchService`) - Crawls company website, performs web searches, scrapes external sources
5. **Content Generation** (`services/gemini.py:GeminiService`) - Calls Vertex AI Gemini API with research context to generate memo content
6. **Document Update** (`services/docs.py:DocsService`) - Inserts formatted markdown content into the document
7. **Status Tracking** - Updates Firestore and optionally Sheet status to "Memo Created"

### Email Agent Flow
1. **Email Processing** (`services/email_agent.py:EmailAgentService`) - Receives email via `/email` endpoint
2. **Action Detection** - Uses Gemini to determine intent (add company, generate memos, update company, etc.)
3. **Execution** - Executes the detected action using appropriate services
4. **Response** - Returns formatted response for email reply

### Key Design Decisions

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

# Email agent (simulated)
curl -X POST http://localhost:8080/email \
  -H "Content-Type: application/json" \
  -d '{"from":"user@example.com","subject":"Add company","body":"Add Acme Inc (acme.com)"}'
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

- `main.py` - Flask application with `/run`, `/email`, and `/health` endpoints
- `services/` - Service modules package
  - `__init__.py` - Re-exports all service classes for backward compatibility
  - `sheets.py` - SheetsService for Google Sheets operations
  - `firestore.py` - FirestoreService for idempotency tracking
  - `drive.py` - DriveService for folder/document creation
  - `docs.py` - DocsService for document content insertion
  - `gemini.py` - GeminiService for Gemini-powered memo generation
  - `research.py` - ResearchService for deep web research
  - `bookface.py` - BookfaceService for YC Bookface scraping
  - `email_agent.py` - EmailAgentService for email-based commands
- `config.py` - Configuration management, environment variables, Secret Manager integration
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration for Cloud Run
- `DEPLOY.md` - Comprehensive deployment guide with IAM, APIs, and Cloud Scheduler setup

## Common Modifications

### Adding New Memo Fields

Update `services/gemini.py:GeminiService.generate_memo()` prompt to request the new field. The document is created blank and content is inserted directly as formatted markdown.

### Changing Processing Logic

Main processing loop is in `main.py:run_processing()`. Each company is processed sequentially by `process_company()`. For parallel processing, consider using Cloud Tasks or Cloud Run Jobs.

### Modifying Idempotency Key

Change `services/firestore.py:FirestoreService.normalize_domain()` to use a different key format (e.g., include company name).

### Adjusting Sheet Columns

Update `services/sheets.py:SheetsService.get_rows_to_process()` to parse different columns or ranges.

### Adding Email Agent Actions

1. Add the action to `EmailAgentService.ACTIONS` dict
2. Add execution logic in `EmailAgentService._execute_action()`
3. Add response formatting in `EmailAgentService._format_response()`

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
