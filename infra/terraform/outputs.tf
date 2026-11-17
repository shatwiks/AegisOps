output "healthcare_namespace" {
  value = kubernetes_namespace.healthcare.metadata[0].name
}

output "system_namespace" {
  value = kubernetes_namespace.system.metadata[0].name
}

output "remediator_service_account" {
  value = "${kubernetes_namespace.healthcare.metadata[0].name}:${kubernetes_service_account.remediator.metadata[0].name}"
}
