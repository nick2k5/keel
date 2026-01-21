# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Keel is a Google Cloud Run service that automates investment memo generation for venture capital deal flow. It reads companies from a Google Sheet, uses Google Gemini to generate memo content, and creates structured Google Docs in a Shared Drive.

## Architecture

### Core Flow
1. **Sheet Processing** (`services.py:SheetsService`) - Reads "Index" tab, identifies rows where Status is empty or "New"
2. **Idempotency Check** (`services.py:FirestoreService`) - Uses Firestore with normalized domain as key to prevent duplicate processing
3. **Drive Operations** (`services.py:DriveService`) - Creates folder and copies template (requires `supportsAllDrives=true` for Shared Drive)
4. **Content Generation** (`services.py:GeminiService`) - Calls Vertex AI Gemini API to generate structured memo content
5. **Document Update** (`services.py:DocsService`) - Uses batchUpdate with replaceAllText to fill template placeholders
6. **Status Tracking** - Updates Firestore and optionally Sheet status to "Memo Created"

### Key Design Decisions

**Shared Drive Support**: All Drive API calls include `supportsAllDrives=true`. Without this parameter, operations on Shared Drive resources will fail with 404 errors.

**Idempotency**: Domain is normalized (lowercase, trimmed) and used as Firestore document ID. This prevents reprocessing if the service is invoked multiple times.

**Template Placeholders**: The Google Docs template must contain exact placeholders: `{{COMPANY}}`, `{{DOMAIN}}`, `{{EXEC_SUMMARY}}`, `{{TEAM}}`, `{{PRODUCT}}`, `{{MARKET}}`, `{{TRACTION}}`, `{{RISKS}}`, `{{QUESTIONS}}`, `{{RECOMMENDATION}}`.

**Structured Logging**: All operations use Python's logging module with INFO level. Logs include company/domain context for traceability.

## Development Commands

### Local Development

Run locally (requires service account credentials):
```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account-key.json"
export GCP_PROJECT_ID="your-project-id"
export SPREADSHEET_ID="your-sheet-id"
export DRIVE_PARENT_FOLDER_ID="your-folder-id"
export TEMPLATE_DOC_ID="your-template-id"

python main.py
```

Test the endpoint:
```bash
curl -X POST http://localhost:8080/run
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
  -e TEMPLATE_DOC_ID="..." \
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

- `main.py` - Flask application with `/run` endpoint and orchestration logic
- `services.py` - All business logic: Sheets, Firestore, Drive, Gemini, Docs services
- `config.py` - Configuration management, environment variables, Secret Manager integration
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration for Cloud Run
- `DEPLOY.md` - Comprehensive deployment guide with IAM, APIs, and Cloud Scheduler setup

## Common Modifications

### Adding New Memo Fields

1. Update `services.py:GeminiService.generate_memo()` prompt to request the new field
2. Add corresponding placeholder to template doc (e.g., `{{NEW_FIELD}}`)
3. Add replaceAllText request in `services.py:DocsService.update_document()`

### Changing Processing Logic

Main processing loop is in `main.py:run_processing()`. Each company is processed sequentially by `process_company()`. For parallel processing, consider using Cloud Tasks or Cloud Run Jobs.

### Modifying Idempotency Key

Change `services.py:FirestoreService.normalize_domain()` to use a different key format (e.g., include company name).

### Adjusting Sheet Columns

Update `services.py:SheetsService.get_rows_to_process()` to parse different columns or ranges.

## Environment Variables

Required:
- `GCP_PROJECT_ID` - Google Cloud project
- `SPREADSHEET_ID` - Google Sheet ID containing company data
- `DRIVE_PARENT_FOLDER_ID` - Shared Drive folder where company folders are created
- `TEMPLATE_DOC_ID` - Google Doc template ID with placeholders

Optional:
- `VERTEX_AI_REGION` - Vertex AI region (default: `us-central1`)
- `FIRESTORE_COLLECTION` - Firestore collection name (default: `processed_domains`)
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
- Service account must be granted Reader access to the template document

## Error Handling

All service methods raise exceptions on failure. The `main.py:process_company()` function catches exceptions and returns an error result without stopping the batch. Check Cloud Run logs for detailed error traces.

## Testing Changes

When modifying the service:
1. Test locally with a test spreadsheet and Shared Drive folder
2. Deploy to a staging Cloud Run service
3. Run with a small batch of test companies
4. Verify Firestore documents are created correctly
5. Check generated Google Docs for proper placeholder replacement
6. Monitor logs for errors or warnings
