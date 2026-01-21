# Deployment Guide

This guide walks through deploying the Keel memo generator to Google Cloud Run.

## Prerequisites

- Google Cloud SDK (`gcloud`) installed and configured
- A Google Cloud project with billing enabled
- Access to a Google Workspace account with Shared Drive access

## Step 1: Enable Required APIs

Enable all necessary Google Cloud APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  sheets.googleapis.com \
  drive.googleapis.com \
  docs.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  cloudbuild.googleapis.com
```

## Step 2: Set Up Firestore

Initialize Firestore in Native mode:

```bash
gcloud firestore databases create --location=us-central1
```

## Step 3: Prepare Google Workspace Resources

1. **Create a Google Sheet** with a tab named "Index" containing columns:
   - Column A: Company
   - Column B: Domain
   - Column C: Status

2. **Create a Google Docs template** with placeholders:
   - `{{COMPANY}}`
   - `{{DOMAIN}}`
   - `{{EXEC_SUMMARY}}`
   - `{{TEAM}}`
   - `{{PRODUCT}}`
   - `{{MARKET}}`
   - `{{TRACTION}}`
   - `{{RISKS}}`
   - `{{QUESTIONS}}`
   - `{{RECOMMENDATION}}`

3. **Create a Shared Drive folder** where company folders will be created.

4. **Note the IDs**:
   - Spreadsheet ID (from URL: `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/...`)
   - Template Doc ID (from URL: `https://docs.google.com/document/d/{DOC_ID}/...`)
   - Parent Folder ID (from URL: `https://drive.google.com/drive/folders/{FOLDER_ID}`)

   0ADTF8Zi3POaxUk9PVA

## Step 4: Configure Environment Variables

Set your project ID:

```bash
export PROJECT_ID="keel-485016"
gcloud config set project keel-485016
```

## Step 5: Deploy to Cloud Run

Deploy the service with environment variables:

```bash
gcloud run deploy keel-memo-generator \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT_ID=keel-485016" \
  --set-env-vars "SPREADSHEET_ID=1b8etSdkKMLsVSYQfGU6zwt4EYcJnf3WCXh_owBB3jMw" \
  --set-env-vars "DRIVE_PARENT_FOLDER_ID=0ADTF8Zi3POaxUk9PVA" \
  --set-env-vars "TEMPLATE_DOC_ID=1praAKxBxLVWsjU6Wk78kDf1epsOpE_2my03eaXJtHVY" \
  --set-env-vars "FIRESTORE_COLLECTION=processed_domains" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 540 \
  --max-instances 10
```

**Note**: Replace the placeholder IDs with your actual IDs from Step 3.

## Step 6: Configure IAM Permissions

The Cloud Run service account needs permissions to access Google Workspace resources.

### Get the Service Account Email

```bash
export SERVICE_ACCOUNT=$(gcloud run services describe keel-memo-generator \
  --region us-central1 \
  --format 'value(spec.template.spec.serviceAccountName)')

echo "Service Account: ${SERVICE_ACCOUNT}"
```

### Grant Required Permissions

```bash
# Vertex AI access
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/aiplatform.user"

# Firestore access (already has this by default for project service accounts)
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/datastore.user"
```

### Grant Google Workspace Access

In Google Workspace Admin:

1. Go to the Google Sheet and share it with the service account email (Editor access)
2. Go to the Shared Drive and share it with the service account email (Content Manager access)
3. Share the template document with the service account email (Reader access)

Alternatively, share the parent Shared Drive with the service account to grant access to all resources.

## Step 7: Test the Deployment

Get the service URL:

```bash
export SERVICE_URL=$(gcloud run services describe keel-memo-generator \
  --region us-central1 \
  --format 'value(status.url)')

echo "Service URL: ${SERVICE_URL}"
```

Test the health endpoint:

```bash
curl ${SERVICE_URL}/health
```

Trigger processing:

```bash
curl -X POST ${SERVICE_URL}/run
```

## Step 8: Set Up Cloud Scheduler (Optional)

Create a scheduled job to run processing automatically:

```bash
# Create a service account for Cloud Scheduler
gcloud iam service-accounts create cloud-scheduler-invoker \
  --display-name "Cloud Scheduler Invoker"

# Grant permission to invoke Cloud Run
gcloud run services add-iam-policy-binding keel-memo-generator \
  --region us-central1 \
  --member="serviceAccount:cloud-scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Create a daily job (runs at 9 AM UTC)
gcloud scheduler jobs create http keel-daily-processing \
  --location us-central1 \
  --schedule "0 9 * * *" \
  --uri "${SERVICE_URL}/run" \
  --http-method POST \
  --oidc-service-account-email "cloud-scheduler-invoker@${PROJECT_ID}.iam.gserviceaccount.com"
```

Test the scheduler immediately:

```bash
gcloud scheduler jobs run keel-daily-processing --location us-central1
```

## Step 9: Monitor Logs

View logs in Cloud Console or via CLI:

```bash
gcloud run services logs read keel-memo-generator \
  --region us-central1 \
  --limit 50
```

Or follow logs in real-time:

```bash
gcloud run services logs tail keel-memo-generator \
  --region us-central1
```

## Updating the Service

To deploy updates:

```bash
gcloud run deploy keel-memo-generator \
  --source . \
  --region us-central1
```

## Troubleshooting

### Permission Errors

If you see 403 errors accessing Google Workspace resources:
- Verify the service account email has access to the Sheet, Drive, and template
- Ensure Shared Drive operations include `supportsAllDrives=true` (already configured)

### Timeout Errors

If processing times out:
- Increase the Cloud Run timeout: `--timeout 900`
- Process fewer rows at once
- Consider async processing with Cloud Tasks

### Gemini API Errors

- Verify the service account has `roles/aiplatform.user` permission
- Check Vertex AI quotas and rate limits
- Review Cloud Run logs for detailed error messages
- Ensure `aiplatform.googleapis.com` API is enabled

## Cost Considerations

- **Cloud Run**: Pay per request, minimal cost for scheduled jobs
- **Firestore**: Minimal reads/writes for idempotency tracking
- **Vertex AI (Gemini)**: Charged per token usage, see Vertex AI pricing
- **Google Workspace APIs**: Free tier covers most use cases

## Security Best Practices

- Use service account authentication for all Google Cloud services
- Use least-privilege IAM permissions
- Enable Cloud Armor for DDoS protection if exposing publicly
- Consider authentication for the `/run` endpoint in production
- Regularly rotate API keys and service account keys
