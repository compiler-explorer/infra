variable "domain_name" {
  description = "The domain name"
  type        = string
}

variable "cloudfront_distribution" {
  description = "The cloudfront distribution to associate with this domain"
  type        = any
}

variable "certificate" {
  description = "The certificate to associate"
  type        = any
}

variable "top_level_name" {
  description = "The name of the top level to associate"
  type        = string
  default     = ""
}

variable "wildcard" {
  description = "Whether to create a wildcard that points at the top_level_name"
  type        = bool
  default     = true
}

variable "mail" {
  description = "Whether to set up mail stuff"
  type        = bool
  default     = true
}
