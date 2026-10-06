data "azurerm_client_config" "current" {}

locals {
  prefix = "justiceflow-${var.environment}"

  common_tags = merge(
    {
      application = "justiceflow"
      environment = var.environment
      managed_by  = "terraform"
      data_class  = "synthetic"
    },
    var.tags,
  )

  database_url = "postgresql+asyncpg://${var.postgres_administrator_login}:${urlencode(var.postgres_administrator_password)}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/justiceflow"
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.common_tags
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  retention_in_days   = 30
  sku                 = "PerGB2018"
  tags                = local.common_tags
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.prefix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.common_tags
}

resource "azurerm_container_registry" "main" {
  name                          = "acrjusticeflow${var.name_suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  sku                           = "Basic"
  admin_enabled                 = false
  public_network_access_enabled = true
  tags                          = local.common_tags
}

resource "azurerm_user_assigned_identity" "workload" {
  name                = "id-${local.prefix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
}

resource "azurerm_role_assignment" "registry_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_key_vault" "main" {
  name                          = "kv-jf-${var.name_suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 7
  public_network_access_enabled = true
  tags                          = local.common_tags
}

resource "azurerm_role_assignment" "key_vault_reader" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.workload.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "deployment_key_vault_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = "psql-${local.prefix}-${var.name_suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  version                       = "16"
  administrator_login           = var.postgres_administrator_login
  administrator_password        = var.postgres_administrator_password
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  geo_redundant_backup_enabled  = false
  public_network_access_enabled = true
  zone                          = "1"
  tags                          = local.common_tags

  authentication {
    active_directory_auth_enabled = false
    password_auth_enabled         = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_postgresql_flexible_server_database" "main" {
  name      = "justiceflow"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = local.database_url
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployment_key_vault_admin]
}

resource "azurerm_key_vault_secret" "langfuse_public_key" {
  count        = var.langfuse_public_key == "" ? 0 : 1
  name         = "langfuse-public-key"
  value        = var.langfuse_public_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployment_key_vault_admin]
}

resource "azurerm_key_vault_secret" "langfuse_secret_key" {
  count        = var.langfuse_secret_key == "" ? 0 : 1
  name         = "langfuse-secret-key"
  value        = var.langfuse_secret_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployment_key_vault_admin]
}

resource "azurerm_container_app" "api" {
  name                         = "ca-${local.prefix}-api"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workload.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.workload.id
  }

  secret {
    name                = "database-url"
    identity            = azurerm_user_assigned_identity.workload.id
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
  }

  dynamic "secret" {
    for_each = var.langfuse_public_key == "" ? [] : [1]
    content {
      name                = "langfuse-public-key"
      identity            = azurerm_user_assigned_identity.workload.id
      key_vault_secret_id = azurerm_key_vault_secret.langfuse_public_key[0].versionless_id
    }
  }

  dynamic "secret" {
    for_each = var.langfuse_secret_key == "" ? [] : [1]
    content {
      name                = "langfuse-secret-key"
      identity            = azurerm_user_assigned_identity.workload.id
      key_vault_secret_id = azurerm_key_vault_secret.langfuse_secret_key[0].versionless_id
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "JUSTICEFLOW_DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name  = "JUSTICEFLOW_OLLAMA_URL"
        value = var.ollama_url
      }

      env {
        name  = "JUSTICEFLOW_OLLAMA_MODEL"
        value = var.ollama_model
      }

      env {
        name  = "JUSTICEFLOW_LANGFUSE_BASE_URL"
        value = var.langfuse_base_url
      }

      env {
        name  = "JUSTICEFLOW_LANGFUSE_ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "JUSTICEFLOW_RELEASE"
        value = "azure-${var.environment}"
      }

      dynamic "env" {
        for_each = var.langfuse_public_key == "" ? [] : [1]
        content {
          name        = "JUSTICEFLOW_LANGFUSE_PUBLIC_KEY"
          secret_name = "langfuse-public-key"
        }
      }

      dynamic "env" {
        for_each = var.langfuse_secret_key == "" ? [] : [1]
        content {
          name        = "JUSTICEFLOW_LANGFUSE_SECRET_KEY"
          secret_name = "langfuse-secret-key"
        }
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }
    }

    http_scale_rule {
      name                = "api-http"
      concurrent_requests = "50"
    }
  }

  depends_on = [
    azurerm_role_assignment.key_vault_reader,
    azurerm_role_assignment.registry_pull,
  ]
}

resource "azurerm_container_app" "web" {
  name                         = "ca-${local.prefix}-web"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.workload.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.workload.id
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    transport        = "http"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "web"
      image  = var.web_image
      cpu    = 0.25
      memory = "0.5Gi"

      liveness_probe {
        transport = "HTTP"
        port      = 3000
        path      = "/"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 3000
        path      = "/"
      }
    }

    http_scale_rule {
      name                = "web-http"
      concurrent_requests = "50"
    }
  }

  depends_on = [azurerm_role_assignment.registry_pull]
}
