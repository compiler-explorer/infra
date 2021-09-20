output "vpc" {
  value = aws_vpc.CompilerExplorer
}

output "subnet" {
  value = aws_subnet.ce
}
