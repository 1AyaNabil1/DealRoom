#!/bin/bash
# verify_deployment.sh
set -e

SERVICE_NAME="dealroom-server"
REGION="us-central1"

echo "Fetching service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')

if [ -z "$SERVICE_URL" ]; then
    echo "ERROR: Could not find service URL for $SERVICE_NAME"
    exit 1
fi

echo "Verifying deployment at $SERVICE_URL/health..."
RESPONSE=$(curl -s "$SERVICE_URL/health")

if echo "$RESPONSE" | grep -q '"status":"ok"'; then
    echo "DEPLOYMENT VERIFIED"
    echo "Response: $RESPONSE"
else
    echo "DEPLOYMENT FAILED"
    echo "Actual response: $RESPONSE"
    exit 1
fi
