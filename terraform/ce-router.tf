# CE Router infrastructure for all environments

module "ce_router_prod" {
  source = "./modules/ce_router"

  environment        = "prod"
  vpc_id             = module.ce_network.vpc.id
  subnet_ids         = local.subnets
  launch_template_id = aws_launch_template.ce["router"].id

  min_size         = 0
  max_size         = 20
  desired_capacity = 0
}

module "ce_router_staging" {
  source = "./modules/ce_router"

  environment        = "staging"
  vpc_id             = module.ce_network.vpc.id
  subnet_ids         = local.subnets
  launch_template_id = aws_launch_template.ce["router"].id

  min_size         = 0
  max_size         = 10
  desired_capacity = 0
}

module "ce_router_beta" {
  source = "./modules/ce_router"

  environment        = "beta"
  vpc_id             = module.ce_network.vpc.id
  subnet_ids         = local.subnets
  launch_template_id = aws_launch_template.ce["router"].id

  min_size         = 1
  max_size         = 10
  desired_capacity = 1
}

# ALB listener rules for compilation routing - COMMENTED OUT
# Will be enabled via Python commands for gradual migration

# # Production environment routing
# resource "aws_alb_listener_rule" "ce_router_compilation_prod" {
#   priority = 70
#
#   action {
#     type             = "forward"
#     target_group_arn = module.ce_router_prod.target_group_arn
#   }
#
#   condition {
#     path_pattern {
#       values = [
#         "/api/compiler/*/compile",
#         "/api/compiler/*/cmake"
#       ]
#     }
#   }
#
#   listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
# }

# # Staging environment routing
# resource "aws_alb_listener_rule" "ce_router_compilation_staging" {
#   priority = 71
#
#   action {
#     type             = "forward"
#     target_group_arn = module.ce_router_staging.target_group_arn
#   }
#
#   condition {
#     path_pattern {
#       values = [
#         "/staging/api/compiler/*/compile",
#         "/staging/api/compiler/*/cmake"
#       ]
#     }
#   }
#
#   listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
# }

# # Beta environment routing
# resource "aws_alb_listener_rule" "ce_router_compilation_beta" {
#   priority = 72
#
#   action {
#     type             = "forward"
#     target_group_arn = module.ce_router_beta.target_group_arn
#   }
#
#   condition {
#     path_pattern {
#       values = [
#         "/beta/api/compiler/*/compile",
#         "/beta/api/compiler/*/cmake"
#       ]
#     }
#   }
#
#   listener_arn = aws_alb_listener.compiler-explorer-alb-listen-https.arn
# }
