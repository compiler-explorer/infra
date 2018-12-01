resource "aws_dynamodb_table" "links" {
  name = "links"
  lifecycle {
    ignore_changes = [
      "read_capacity",
      "write_capacity"
    ]
  }
  // TODO: change once terraform supports on-demand pricing. We are currently set to use
  // on-demand in the UI only.
  read_capacity = 1
  write_capacity = 1
  hash_key = "prefix"
  range_key = "unique_subhash"

  attribute = [
    {
      name = "prefix"
      type = "S"
    },
    {
      name = "unique_subhash"
      type = "S"
    }
  ]

  point_in_time_recovery {
    enabled = true
  }

  tags {
    key = "Site"
    value = "CompilerExplorer"
  }
}
