resource "aws_alb" "CEConanServerAlb" {
  idle_timeout    = 60
  internal        = false
  name            = "CEConanServerAlb"
  security_groups = [
    aws_security_group.CompilerExplorerConanAlb.id
  ]
  subnets         = [
    aws_subnet.ce-1a.id,
    aws_subnet.ce-1b.id,
    aws_subnet.ce-1c.id,
    aws_subnet.ce-1d.id,
    aws_subnet.ce-1e.id,
    aws_subnet.ce-1f.id
  ]

  enable_deletion_protection = true

  access_logs {
    bucket  = aws_s3_bucket.compiler-explorer-logs.bucket
    prefix  = "elb"
    enabled = true
  }

  tags = {
    Site = "CompilerExplorer"
  }
}

resource "aws_alb_listener" "ceconan-alb-listen-http" {
  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.conan.arn
  }

  load_balancer_arn = aws_alb.CEConanServerAlb.arn
  port              = 80
  protocol          = "HTTP"
}
