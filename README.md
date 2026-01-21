# Keel - AI-Powered Investment Memo Generator

Automated investment memo generation for venture capital deal flow, powered by Google Gemini and Google Cloud.

## Overview

Keel is a Google Cloud Run service that:
- Reads company data from a Google Sheet
- Generates structured investment memos using Google Gemini via Vertex AI
- Creates organized folders and documents in Google Drive
- Ensures idempotent processing with Firestore

## Features

- **Automated Processing**: Trigger via HTTP endpoint or Cloud Scheduler
- **AI-Generated Content**: Google Gemini creates crisp, professional VC-style memos
- **Google Workspace Integration**: Seamless integration with Sheets, Drive, and Docs
- **Idempotent Design**: Prevents duplicate processing using Firestore
- **Shared Drive Support**: Full support for Google Shared Drives
- **Structured Logging**: Detailed logs for monitoring and debugging
- **Production Ready**: Designed for Cloud Run with proper error handling and retries

## Quick Start

### Prerequisites

- Google Cloud project with billing enabled
- Google Workspace account with Shared Drive access
- `gcloud` CLI installed

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd keel
   ```

2. **Follow the deployment guide**
   See [DEPLOY.md](DEPLOY.md) for complete setup instructions including:
   - Enabling required Google Cloud APIs
   - Setting up Firestore
   - Configuring IAM permissions
   - Deploying to Cloud Run
   - Setting up Cloud Scheduler (optional)

### Configuration

Create your Google Workspace resources:

1. **Google Sheet** with "Index" tab:
   | Company | Domain | Status |
   |---------|--------|--------|
   | Acme Inc | acme.com | New |

2. **Google Docs Template** with placeholders:
   - `{{COMPANY}}`, `{{DOMAIN}}`, `{{EXEC_SUMMARY}}`
   - `{{TEAM}}`, `{{PRODUCT}}`, `{{MARKET}}`
   - `{{TRACTION}}`, `{{RISKS}}`, `{{QUESTIONS}}`, `{{RECOMMENDATION}}`

3. **Shared Drive Folder** for storing generated memos

## Usage

### Trigger Processing

```bash
curl -X POST https://your-service-url.run.app/run
```

### Response Format

```json
{
  "status": "success",
  "message": "Processed 5 rows",
  "processed": 4,
  "errors": 0,
  "skipped": 1,
  "results": [
    {
      "company": "Acme Inc",
      "domain": "acme.com",
      "status": "success",
      "doc_id": "...",
      "folder_id": "..."
    }
  ]
}
```

## Architecture

```
Google Sheet (Index) → Cloud Run Service → Google Drive (Folders + Docs)
                              ↓
                         Firestore (Idempotency)
                              ↓
                         Vertex AI Gemini (Content Generation)
```

### Processing Flow

1. Read companies from Sheet where Status is empty or "New"
2. Check Firestore to skip already-processed domains
3. Create company folder in Shared Drive
4. Copy template document into folder
5. Generate memo content with Google Gemini
6. Update document with generated content
7. Mark as processed in Firestore
8. Update Sheet status to "Memo Created"

## Development

See [CLAUDE.md](CLAUDE.md) for detailed development guidance.

### Local Development

```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account-key.json"
export GCP_PROJECT_ID="your-project-id"
export SPREADSHEET_ID="your-sheet-id"
export DRIVE_PARENT_FOLDER_ID="your-folder-id"
export TEMPLATE_DOC_ID="your-template-id"

python main.py
```

### Docker Build

```bash
docker build -t keel-memo-generator .
docker run -p 8080:8080 -e GCP_PROJECT_ID="..." keel-memo-generator
```

## Project Structure

```
keel/
├── main.py              # Flask app and orchestration
├── services.py          # Business logic (Sheets, Drive, Docs, Gemini, Firestore)
├── config.py            # Configuration management
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── DEPLOY.md           # Deployment guide
├── CLAUDE.md           # Development guidance
└── README.md           # This file
```

## Monitoring

View logs:
```bash
gcloud run services logs read keel-memo-generator --region us-central1
```

Tail logs:
```bash
gcloud run services logs tail keel-memo-generator --region us-central1
```

## Security

- API keys stored in Google Secret Manager
- Service account with least-privilege IAM permissions
- All Google Workspace resources require explicit sharing
- Structured logging for audit trails

## Cost Optimization

- Cloud Run scales to zero when idle
- Firestore charged per read/write (minimal for idempotency)
- Vertex AI (Gemini) charged per token
- Google Workspace APIs within free tier for most use cases

## License

[Your License Here]

## Support

For issues and questions, see [DEPLOY.md](DEPLOY.md) troubleshooting section.
