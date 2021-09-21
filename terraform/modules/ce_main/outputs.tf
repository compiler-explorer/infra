output "prod_target_group" {
  value = aws_alb_target_group.ce["prod"]
}

output "alb" {
  value = aws_alb.GccExplorerApp
}

output "https_listener" {
  value = aws_alb_listener.compiler-explorer-alb-listen-https
}

output "sg" {
  value = aws_security_group.CompilerExplorerAlb
}
