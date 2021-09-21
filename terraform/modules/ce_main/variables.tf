variable "extra_environments" {
  description = "Extra environments"
  type        = map(object({
    launch_configuration = string
  }))
}

variable "vpc_id" {
  description = "VPC to create the environments in"
  type = string
}

variable "https_certificate_arn" {
  description = "ARN of the https certificate to use"
  type = string
}

variable "log_bucket" {
  description = "S3 bucket to place elb logs"
  type = string
}

variable "log_prefix" {
  description = "S3 prefix to place elb logs"
  type = string
  default = "elb"
}

variable "subnet_ids" {
  description = "A list of all the subnet IDs to supper"
  type = list(string)
}