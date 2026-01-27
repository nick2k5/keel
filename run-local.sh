#!/bin/bash
# Run the Keel service locally

set -e

# Change to script directory
cd "$(dirname "$0")"

# Activate virtualenv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Activated virtualenv"
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Copy .env.example to .env and fill in values."
    exit 1
fi

# Use Application Default Credentials if no service account key is specified
if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "Using Application Default Credentials (gcloud auth application-default login)"
fi

# Start the Flask app
echo "Starting Keel on http://localhost:8080"
python main.py
