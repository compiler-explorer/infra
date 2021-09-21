// Inputs:
// * VPC
// * Log bucket
// Some kind of mapping <->
//   prod -> target group
//   "beta" -> target group
//   "staging" -> target group etc
// target groups can be derived...
// ASGs?

module main {
  source                = "./modules/ce_main"
  vpc_id                = module.ce_network.vpc.id
  https_certificate_arn = data.aws_acm_certificate.godbolt-org-et-al.arn
  log_bucket            = aws_s3_bucket.compiler-explorer-logs.bucket
  subnet_ids            = local.all_subnet_ids
  extra_environments    = {
    "staging" = {
      launch_configuration = aws_launch_template.CompilerExplorer-staging.id
    }
    "beta"    = {
      launch_configuration = aws_launch_template.CompilerExplorer-beta.id
    }
  }
}