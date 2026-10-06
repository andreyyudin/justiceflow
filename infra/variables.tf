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
  description = "Immutable API image reference, preferably pinned by digest."
  type        = string
}

variable "web_image" {
  description = "Immutable web image reference, preferably pinned by digest."
  type        = string
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
  description = "Approved private Ollama-compatible endpoint reachable from Azure."
  type        = string
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
  description = "Optional approved Langfuse Cloud or self-hosted endpoint."
  type        = string
  default     = ""
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}
