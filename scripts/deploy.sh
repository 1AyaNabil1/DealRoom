#!/bin/bash
# deploy.sh
set -e

# Override with environment variables, e.g. GCP_PROJECT_ID=my-project ./scripts/deploy.sh
PROJECT_ID="${GCP_PROJECT_ID:-dealroom-hackathon}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-dealroom-server}"
IMAGE_URL="gcr.io/$PROJECT_ID/$SERVICE_NAME"

echo "Configuring gcloud for project $PROJECT_ID..."
gcloud config set project "$PROJECT_ID"

echo "Building image using Cloud Build..."
gcloud builds submit --tag "$IMAGE_URL" .

echo "Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
    --image "$IMAGE_URL" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --min-instances 0 \
    --max-instances 3 \
    --memory 512Mi \
    --update-secrets="GOOGLE_API_KEY=dealroom-api-key:latest"

echo "Fetching service URL..."
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')

echo "DEPLOYMENT COMPLETE"
echo "Service URL: $SERVICE_URL"
