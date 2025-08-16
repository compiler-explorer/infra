data "aws_backup_vault" "compiler-explorer" {
  name = "Default"
}

resource "aws_backup_plan" "compiler-explorer" {
  name = "compiler-explorer"
  rule {
    rule_name         = "compiler-explorer"
    target_vault_name = data.aws_backup_vault.compiler-explorer.name
    schedule          = "cron(0 5 ? * * *)"

    start_window      = 480
    completion_window = 10080
    lifecycle {
      cold_storage_after = 0
      delete_after       = 14
    }
  }
}

resource "aws_backup_selection" "compiler-explorer" {
  name         = "conan-server"
  iam_role_arn = "arn:aws:iam::052730242331:role/service-role/AWSBackupDefaultServiceRole"
  plan_id      = aws_backup_plan.compiler-explorer.id

  resources = ["*"]
  condition {
    string_equals {
      key   = "aws:ResourceTag/Name"
      value = "CEConanServerVol1"
    }
  }
}
