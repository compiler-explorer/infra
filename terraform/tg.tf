resource "aws_alb_target_group" "conan" {
  lifecycle {
    create_before_destroy = true
  }
  name                 = "ConanGroup"
  port                 = 1080
  protocol             = "HTTP"
  vpc_id               = module.ce_network.vpc.id
  deregistration_delay = 15
  health_check {
    path                = "/healthcheck"
    timeout             = 3
    unhealthy_threshold = 3
    healthy_threshold   = 2
    interval            = 5
    protocol            = "HTTP"
  }
}

resource "aws_alb_target_group_attachment" "CEConanServerTargetInstance" {
  target_group_arn = aws_alb_target_group.conan.id
  target_id        = aws_instance.ConanNode.id
  port             = 1080
}
