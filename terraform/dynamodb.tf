resource "aws_dynamodb_table" "links" {
  name           = "links"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
  }
  billing_mode   = "PAY_PER_REQUEST"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "prefix"
  range_key      = "unique_subhash"

  attribute {
    name = "prefix"
    type = "S"
  }
  attribute {
    name = "unique_subhash"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}
