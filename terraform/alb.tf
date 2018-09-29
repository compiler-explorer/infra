resource "aws_alb" "GccExplorerApp" {
  idle_timeout = 60
  internal = false
  name = "GccExplorerApp"
  security_groups = [
    "sg-99df30fd"]
  subnets = [
    "subnet-1bed1d42",
    "subnet-1df1e135",
    "subnet-690ed81e"]

  enable_deletion_protection = false

  tags {
    "Site" = "CompilerExplorer"
  }
}

