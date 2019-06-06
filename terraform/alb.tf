resource "aws_alb" "GccExplorerApp" {
  idle_timeout    = 60
  internal        = false
  name            = "GccExplorerApp"
  security_groups = [
    "${aws_security_group.CompilerExplorerAlb.id}"
  ]
  subnets         = [
    "${aws_subnet.ce-1a.id}",
    "${aws_subnet.ce-1b.id}",
    "${aws_subnet.ce-1c.id}",
    "${aws_subnet.ce-1d.id}",
    "${aws_subnet.ce-1e.id}",
    "${aws_subnet.ce-1f.id}"
  ]

  enable_deletion_protection = false

  tags {
    "Site" = "CompilerExplorer"
  }
}

resource "aws_alb_listener" "compiler-explorer-alb-listen-http" {
  default_action {
    type             = "forward"
    target_group_arn = "${aws_alb_target_group.prod.arn}"
  }

  load_balancer_arn = "${aws_alb.GccExplorerApp.arn}"
  port              = 80
  protocol          = "HTTP"
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-http-beta" {
  priority     = 1
  action {
    type             = "forward"
    target_group_arn = "${aws_alb_target_group.beta.arn}"
  }
  condition {
    field  = "path-pattern"
    values = [
      "/beta*"
    ]
  }
  listener_arn = "${aws_alb_listener.compiler-explorer-alb-listen-http.arn}"
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-http-staging" {
  priority     = 2
  action {
    type             = "forward"
    target_group_arn = "${aws_alb_target_group.staging.arn}"
  }
  condition {
    field  = "path-pattern"
    values = [
      "/staging*"
    ]
  }
  listener_arn = "${aws_alb_listener.compiler-explorer-alb-listen-http.arn}"
}

resource "aws_alb_listener" "compiler-explorer-alb-listen-https" {
  default_action {
    type             = "forward"
    target_group_arn = "${aws_alb_target_group.prod.arn}"
  }
  load_balancer_arn = "${aws_alb.GccExplorerApp.arn}"
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2015-05"
  certificate_arn   = "arn:aws:iam::052730242331:server-certificate/2016_star_godbolt_org"
}

resource "aws_lb_listener_certificate" "compiler-explorer-alb-listen-https-ce-cert" {
  listener_arn    = "${aws_alb_listener.compiler-explorer-alb-listen-https.arn}"
  certificate_arn = "arn:aws:acm:us-east-1:052730242331:certificate/7abed4ab-ecfc-4020-8f73-f255fd82f079"
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-beta" {
  priority     = 1
  action {
    type             = "forward"
    target_group_arn = "${aws_alb_target_group.beta.arn}"
  }
  condition {
    field  = "path-pattern"
    values = [
      "/beta*"
    ]
  }
  listener_arn = "${aws_alb_listener.compiler-explorer-alb-listen-https.arn}"
}

resource "aws_alb_listener_rule" "compiler-explorer-alb-listen-https-staging" {
  priority     = 2
  action {
    type             = "forward"
    target_group_arn = "${aws_alb_target_group.staging.arn}"
  }
  condition {
    field  = "path-pattern"
    values = [
      "/staging*"
    ]
  }
  listener_arn = "${aws_alb_listener.compiler-explorer-alb-listen-https.arn}"
}
