variable "environment" {
  description = "Environment name (e.g., beta, prod)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID for the target groups"
  type        = string
}

variable "launch_template_id" {
  description = "Launch template ID for the ASGs"
  type        = string
}

variable "subnets" {
  description = "List of subnet IDs for the ASGs"
  type        = list(string)
}

variable "asg_max_size" {
  description = "Maximum size for the Auto Scaling Groups"
  type        = number
  default     = 4
}

variable "initial_desired_capacity" {
  description = "Initial desired capacity for ASGs"
  type        = number
  default     = 0
}

variable "health_check_grace_period" {
  description = "Health check grace period in seconds"
  type        = number
  default     = 300
}

variable "default_cooldown" {
  description = "Default cooldown period in seconds"
  type        = number
  default     = 180
}

variable "enabled_metrics" {
  description = "List of metrics to enable for the ASGs"
  type        = list(string)
  default     = []
}

variable "initial_active_color" {
  description = "Initial active color (blue or green)"
  type        = string
  default     = "blue"
}
