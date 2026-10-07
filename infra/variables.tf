variable "location" {
  description = "Azure region for all JusticeFlow resources."
  type        = string
  default     = "uksouth"
}

variable "environment" {
  description = "Short deployment environment name."
  type        = string
  default     = "demo"

  validation {
    condition     = can(regex("^[a-z0-9-]{2,12}$", var.environment))
    error_message = "Environment must contain 2-12 lowercase letters, numbers, or hyphens."
  }
}

variable "name_suffix" {
  description = "Globally unique lowercase suffix used by ACR, Key Vault, and PostgreSQL."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{5,12}$", var.name_suffix))
    error_message = "Name suffix must contain 5-12 lowercase letters or numbers."
  }
}

variable "api_image" {
  description = "Immutable API image reference pinned by SHA-256 digest."
  type        = string

  validation {
    condition     = can(regex("^.+@sha256:[0-9a-f]{64}$", var.api_image))
    error_message = "API image must be an immutable reference ending in @sha256 followed by 64 lowercase hexadecimal characters."
  }
}

variable "web_image" {
  description = "Immutable web image reference pinned by SHA-256 digest."
  type        = string

  validation {
    condition     = can(regex("^.+@sha256:[0-9a-f]{64}$", var.web_image))
    error_message = "Web image must be an immutable reference ending in @sha256 followed by 64 lowercase hexadecimal characters."
  }
}

variable "postgres_administrator_login" {
  description = "PostgreSQL administrator login used only for the portfolio deployment."
  type        = string
  default     = "justiceflowadmin"
}

variable "postgres_administrator_password" {
  description = "PostgreSQL administrator password. Supply through a secured CI variable; never commit it."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.postgres_administrator_password) >= 16
    error_message = "PostgreSQL administrator password must contain at least 16 characters."
  }
}

variable "ollama_url" {
  description = "Approved private HTTPS Ollama-compatible endpoint reachable from Azure."
  type        = string

  validation {
    condition     = can(regex("^https://[^[:space:]]+$", var.ollama_url))
    error_message = "Production Ollama endpoint must be a non-empty HTTPS URL."
  }
}

variable "ollama_model" {
  description = "Model identifier exposed by the approved endpoint."
  type        = string
  default     = "qwen3:4b"
}

variable "langfuse_public_key" {
  description = "Optional Langfuse public key."
  type        = string
  sensitive   = true
  default     = ""
}

variable "langfuse_secret_key" {
  description = "Optional Langfuse secret key."
  type        = string
  sensitive   = true
  default     = ""
}

variable "langfuse_base_url" {
  description = "Optional approved HTTPS Langfuse Cloud or self-hosted endpoint."
  type        = string
  default     = ""

  validation {
    condition = (
      var.langfuse_base_url == ""
      || can(regex("^https://[^[:space:]]+$", var.langfuse_base_url))
    )
    error_message = "Langfuse endpoint must be empty or a non-empty HTTPS URL."
  }
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}

variable "oidc_issuer" {
  description = "Public OIDC issuer used to validate API access tokens."
  type        = string

  validation {
    condition     = can(regex("^https://", var.oidc_issuer))
    error_message = "Production OIDC issuer must use HTTPS."
  }
}

variable "oidc_audience" {
  description = "Audience required in JusticeFlow API access tokens."
  type        = string
  default     = "justiceflow-api"
}

variable "oidc_role_claim" {
  description = "Dotted path or literal top-level claim containing JusticeFlow roles."
  type        = string
  default     = "realm_access.roles"

  validation {
    condition     = trimspace(var.oidc_role_claim) != ""
    error_message = "OIDC role claim must not be empty."
  }
}

variable "oidc_jwks_url" {
  description = "OIDC JSON Web Key Set endpoint used by the API."
  type        = string

  validation {
    condition     = can(regex("^https://", var.oidc_jwks_url))
    error_message = "Production JWKS URL must use HTTPS."
  }
}
