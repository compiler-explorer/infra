
resource "aws_autoscaling_group" "staging" {
  lifecycle {
    create_before_destroy = true
  }

  default_cooldown          = local.cooldown
  health_check_grace_period = local.grace_period
  health_check_type         = "ELB"
  launch_template {
    id      = aws_launch_template.CompilerExplorer-staging.id
    version = "$Latest"
  }
  max_size            = 4
  min_size            = 0
  name                = "staging"
  vpc_zone_identifier = local.subnets

  target_group_arns = [aws_alb_target_group.ce["staging"].arn]
}
