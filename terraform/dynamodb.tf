resource "aws_dynamodb_table" "links" {
  name = "links"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
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

resource "aws_dynamodb_table" "versionslog" {
  name = "versionslog"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
  }
  billing_mode   = "PAY_PER_REQUEST"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "buildId"
  range_key      = "timestamp"

  attribute {
    name = "buildId"
    type = "S"
  }
  attribute {
    name = "timestamp"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "nightly-version" {
  name = "nightly-version"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
  }
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "exe"

  attribute {
    name = "exe"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "nightly-exe" {
  name = "nightly-exe"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
  }
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "compiler-builds" {
  name = "compiler-builds"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
  }
  billing_mode   = "PAY_PER_REQUEST"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "compiler"
  range_key      = "timestamp"

  attribute {
    name = "compiler"
    type = "S"
  }
  attribute {
    name = "timestamp"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "events-connections" {
  name = "events-connections"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
  }
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "connectionId"

  attribute {
    name = "connectionId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "prod-remote-exec-archs" {
  name = "prod-remote-exec-archs"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
  }
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "triple"

  attribute {
    name = "triple"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "staging-remote-exec-archs" {
  name = "staging-remote-exec-archs"
  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity
    ]
    prevent_destroy = true
  }
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "triple"

  attribute {
    name = "triple"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_dynamodb_table" "library-build-history" {
  name         = "library-build-history"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "library"
  range_key = "compiler"

  attribute {
    name = "library"
    type = "S"
  }

  attribute {
    name = "compiler"
    type = "S"
  }
}

resource "aws_dynamodb_table" "goo_gl_links" {
  name         = "goo-gl-links"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "fragment"

  attribute {
    name = "fragment"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_dynamodb_table" "compiler_routing" {
  name         = "CompilerRouting"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "compilerId"

  attribute {
    name = "compilerId"
    type = "S"
  }

  # TTL for automatic cleanup of stale entries (optional field)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery for data protection without performance impact
  point_in_time_recovery {
    enabled = true
  }
  
  # Disable DynamoDB Streams - not needed and reduces write latency
  stream_enabled   = false
  stream_view_type = null
  
  # Table class optimized for frequent access patterns
  table_class = "STANDARD"  # Default, optimized for frequent reads/writes

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Purpose = "Compiler to queue routing mappings"
    Project = "compiler-explorer"
  }
}


# CloudWatch alarms for DynamoDB monitoring
resource "aws_cloudwatch_metric_alarm" "compiler_routing_read_throttles" {
  alarm_name          = "compiler-routing-read-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ReadThrottles"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "This metric monitors DynamoDB read throttles"
  alarm_actions       = [data.aws_sns_topic.alert.arn]

  dimensions = {
    TableName = aws_dynamodb_table.compiler_routing.name
  }

  tags = {
    Purpose = "Monitor DynamoDB performance"
    Project = "compiler-explorer"
  }
}

resource "aws_cloudwatch_metric_alarm" "compiler_routing_write_throttles" {
  alarm_name          = "compiler-routing-write-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "WriteThrottles"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "This metric monitors DynamoDB write throttles"
  alarm_actions       = [data.aws_sns_topic.alert.arn]

  dimensions = {
    TableName = aws_dynamodb_table.compiler_routing.name
  }

  tags = {
    Purpose = "Monitor DynamoDB performance"
    Project = "compiler-explorer"
  }
}

# Note: DynamoDB Accelerator (DAX) configuration 
# DAX would provide microsecond latency but requires VPC setup
# For now, focusing on DynamoDB table optimizations that can be applied immediately
