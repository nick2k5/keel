# Keel Email Agent - Apps Script Setup

This script monitors the `keel@friale.com` inbox and forwards emails to the Cloud Run service for processing.

## Installation

### Step 1: Create the Apps Script Project

1. Log into `keel@friale.com` in your browser
2. Go to [script.google.com](https://script.google.com)
3. Click **New Project**
4. Name it "Keel Email Agent"

### Step 2: Add the Script Code

1. Replace the contents of `Code.gs` with `appscript/Code.gs` from this repo
2. Click **File → Save**

### Step 3: Create Time Trigger

1. Click the clock icon (⏰) **Triggers** in the left sidebar
2. Click **+ Add Trigger**
3. Configure:
   - Function: `checkForTriggerEmails`
   - Deployment: Head
   - Event source: **Time-driven**
   - Type: **Minutes timer**
   - Interval: **Every 5 minutes**
4. Click **Save**
5. Authorize when prompted

## Configuration

Update the endpoint URL in `Code.gs` if redeploying to a new project:

```javascript
const CONFIG = {
  agentEmail: 'keel@friale.com',
  endpoint: 'https://keel-memo-generator-952407610436.us-central1.run.app/email'
};
```

## How It Works

1. Script runs every 5 minutes
2. Fetches up to 10 unread emails
3. Skips emails sent by `keel@friale.com` (prevents loops)
4. Sends each email to the Cloud Run `/email` endpoint
5. Replies with the service response
6. Marks email as read and archives it

## Testing

Run `testEndpoint` from the Apps Script editor to verify connectivity.
