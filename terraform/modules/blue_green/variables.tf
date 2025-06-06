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

variable "use_mixed_instances_policy" {
  description = "Whether to use mixed instances policy (for production)"
  type        = bool
  default     = false
}

variable "mixed_instances_overrides" {
  description = "List of instance type overrides for mixed instances policy"
  type = list(object({
    instance_type = string
  }))
  default = []
}

variable "on_demand_base_capacity" {
  description = "Absolute minimum number of on-demand instances"
  type        = number
  default     = 0
}

variable "on_demand_percentage_above_base_capacity" {
  description = "Percentage of on-demand instances above base capacity"
  type        = number
  default     = 0
}

variable "spot_allocation_strategy" {
  description = "Spot allocation strategy"
  type        = string
  default     = "price-capacity-optimized"
}

variable "enable_autoscaling_policy" {
  description = "Whether to enable CPU-based auto-scaling policy"
  type        = bool
  default     = false
}

variable "autoscaling_target_cpu" {
  description = "Target CPU utilization for auto-scaling"
  type        = number
  default     = 50.0
}
