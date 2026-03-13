# main.tf
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "dealroom-hackathon"
  region  = "us-central1"
}

# Enable GCP APIs
resource "google_project_service" "run_api" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "firestore_api" {
  service            = "firestore.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "tts_api" {
  service            = "texttospeech.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "secretmanager_api" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "aiplatform_api" {
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

# Cloud Run Service
resource "google_cloud_run_service" "dealroom_server" {
  name     = "dealroom-server"
  location = "us-central1"

  template {
    spec {
      containers {
        image = "gcr.io/dealroom-hackathon/dealroom-server"
        
        resources {
          limits = {
            memory = "512Mi"
          }
        }

        env {
          name = "GOOGLE_API_KEY"
          value_from {
            secret_key_ref {
              name = "dealroom-api-key"
              key  = "latest"
            }
          }
        }
      }
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = "0"
        "autoscaling.knative.dev/maxScale" = "3"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [google_project_service.run_api]
}

# Allow unauthenticated access
resource "google_cloud_run_service_iam_member" "allow_unauthenticated" {
  location = google_cloud_run_service.dealroom_server.location
  service  = google_cloud_run_service.dealroom_server.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Firestore Database
resource "google_firestore_database" "database" {
  name        = "(default)"
  location_id = "us-central1"
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.firestore_api]
}

# Outputs
output "service_url" {
  value = google_cloud_run_service.dealroom_server.status[0].url
}
