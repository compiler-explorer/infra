variable "environment" {
  description = "Environment name (prod, staging, beta)"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where the target group will be created"
  type        = string
}

variable "subnet_ids" {
  description = "List of subnet IDs for the Auto Scaling Group"
  type        = list(string)
}

variable "launch_template_id" {
  description = "Launch template ID for ce-router instances"
  type        = string
}

variable "min_size" {
  description = "Minimum number of instances in the ASG"
  type        = number
  default     = 2
}

variable "max_size" {
  description = "Maximum number of instances in the ASG"
  type        = number
  default     = 20
}

variable "desired_capacity" {
  description = "Desired number of instances in the ASG"
  type        = number
  default     = 3
}
