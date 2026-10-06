output "resource_group_name" {
  description = "Resource group containing the JusticeFlow deployment."
  value       = azurerm_resource_group.main.name
}

output "container_registry_login_server" {
  description = "Registry endpoint for publishing immutable application images."
  value       = azurerm_container_registry.main.login_server
}

output "api_url" {
  description = "Public JusticeFlow API endpoint."
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "web_url" {
  description = "Public JusticeFlow caseworker interface."
  value       = "https://${azurerm_container_app.web.ingress[0].fqdn}"
}

output "key_vault_name" {
  description = "Key Vault holding runtime secrets."
  value       = azurerm_key_vault.main.name
}

output "workload_identity_client_id" {
  description = "Managed identity used by both Container Apps."
  value       = azurerm_user_assigned_identity.workload.client_id
}
