variable "kubeconfig_path" {
  type        = string
  default     = "~/.kube/config"
  description = "Path to kubeconfig file"
}

variable "kube_context" {
  type        = string
  default     = "kind-aegisops-local"
  description = "Explicit local kind context name"

  validation {
    condition     = var.kube_context == "kind-aegisops-local"
    error_message = "Terraform must target kind-aegisops-local only."
  }
}

variable "healthcare_namespace" {
  type    = string
  default = "aegisops-healthcare"
}

variable "system_namespace" {
  type    = string
  default = "aegisops-system"
}
