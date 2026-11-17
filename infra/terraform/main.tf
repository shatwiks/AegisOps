terraform {
  required_version = ">= 1.9.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.35"
    }
  }
}

provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context
}

resource "kubernetes_namespace" "healthcare" {
  metadata {
    name = var.healthcare_namespace
    labels = {
      "aegisops.io/owned-by" = "terraform"
      "aegisops.io/tier"     = "demo-workloads"
    }
  }
}

resource "kubernetes_namespace" "system" {
  metadata {
    name = var.system_namespace
    labels = {
      "aegisops.io/owned-by" = "terraform"
      "aegisops.io/tier"     = "telemetry"
    }
  }
}

# Least-privilege remediation ServiceAccount scoped strictly to healthcare namespace
resource "kubernetes_service_account" "remediator" {
  metadata {
    name      = "aegisops-remediator"
    namespace = kubernetes_namespace.healthcare.metadata[0].name
    labels = {
      "aegisops.io/owned-by" = "terraform"
    }
  }
}

resource "kubernetes_role" "remediator" {
  metadata {
    name      = "aegisops-remediator-role"
    namespace = kubernetes_namespace.healthcare.metadata[0].name
  }

  rule {
    api_groups = ["apps"]
    resources  = ["deployments", "deployments/scale"]
    verbs      = ["get", "list", "watch", "patch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods", "events", "services"]
    verbs      = ["get", "list", "watch"]
  }
}

resource "kubernetes_role_binding" "remediator" {
  metadata {
    name      = "aegisops-remediator-binding"
    namespace = kubernetes_namespace.healthcare.metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role.remediator.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.remediator.metadata[0].name
    namespace = kubernetes_namespace.healthcare.metadata[0].name
  }
}

resource "kubernetes_limit_range" "healthcare_limits" {
  metadata {
    name      = "aegisops-healthcare-limits"
    namespace = kubernetes_namespace.healthcare.metadata[0].name
  }

  spec {
    limit {
      type = "Container"
      default = {
        cpu    = "250m"
        memory = "256Mi"
      }
      default_request = {
        cpu    = "50m"
        memory = "64Mi"
      }
      max = {
        cpu    = "1"
        memory = "512Mi"
      }
    }
  }
}

resource "kubernetes_resource_quota" "healthcare_quota" {
  metadata {
    name      = "aegisops-healthcare-quota"
    namespace = kubernetes_namespace.healthcare.metadata[0].name
  }

  spec {
    hard = {
      "pods"                   = "24"
      "requests.cpu"           = "4"
      "requests.memory"        = "3Gi"
      "limits.cpu"             = "8"
      "limits.memory"          = "6Gi"
    }
  }
}
