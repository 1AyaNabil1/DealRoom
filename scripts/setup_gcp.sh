#!/bin/bash
# setup_gcp.sh
set -e

PROJECT_ID="dealroom-hackathon"
REGION="us-central1"

echo "Creating GCP project: $PROJECT_ID..."
# Note: Project IDs must be unique. This may fail if the ID is already taken.
gcloud projects create "$PROJECT_ID" || echo "Project $PROJECT_ID may already exist, proceeding..."

echo "Setting active project..."
gcloud config set project "$PROJECT_ID"

echo "Enabling Vertex AI, Cloud Run, Firestore, Cloud TTS, and Secret Manager APIs..."
gcloud services enable \
    aiplatform.googleapis.com \
    run.googleapis.com \
    firestore.googleapis.com \
    texttospeech.googleapis.com \
    secretmanager.googleapis.com

echo "Configuring default region..."
gcloud config set run/region "$REGION"

echo "SETUP COMPLETE"
