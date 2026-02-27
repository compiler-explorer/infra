variable "zone" {
  description = "Route53 zone name"
  type        = string
}

variable "target_url" {
  description = "URL to redirect to"
  type        = string
}

variable "cloudfront_forward_query_string" {
  description = "Toggle forwarding of query strings for CloudFront"
  type        = bool
  default     = false
}

variable "cloudfront_wait_for_deployment" {
  description = "Toggle wait for deployment for CloudFront"
  type        = bool
  default     = false
}

variable "subdomain" {
  description = "Subdomain for the CloudFront (has to end with a dot if not empty!)"
  type        = string
  default     = ""
}
