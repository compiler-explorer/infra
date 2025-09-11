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
  billing_mode   = "PROVISIONED"
  read_capacity  = 25 # Baseline for production WebSocket traffic
  write_capacity = 10 # Baseline for connection updates
  hash_key       = "connectionId"

  attribute {
    name = "connectionId"
    type = "S"
  }

  attribute {
    name = "subscription"
    type = "S"
  }

  # Global Secondary Index for efficient subscription lookups
  global_secondary_index {
    name            = "SubscriptionIndex"
    hash_key        = "subscription"
    read_capacity   = 25          # Match main table baseline
    write_capacity  = 10          # Match main table baseline
    projection_type = "KEYS_ONLY" # Only project connectionId and subscription for minimal data transfer
  }

  point_in_time_recovery {
    enabled = false
  }

  # TTL for automatic cleanup of expired GUID-sender mappings
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}

# Auto-scaling for events-connections table read capacity
resource "aws_appautoscaling_target" "events_connections_read_target" {
  max_capacity       = 100
  min_capacity       = 25
  resource_id        = "table/${aws_dynamodb_table.events-connections.name}"
  scalable_dimension = "dynamodb:table:ReadCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "events_connections_read_policy" {
  name               = "DynamoDBReadCapacityUtilization:${aws_appautoscaling_target.events_connections_read_target.resource_id}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.events_connections_read_target.resource_id
  scalable_dimension = aws_appautoscaling_target.events_connections_read_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.events_connections_read_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBReadCapacityUtilization"
    }
    target_value = 70.0 # Scale up when utilization exceeds 70%
  }
}

# Auto-scaling for events-connections table write capacity
resource "aws_appautoscaling_target" "events_connections_write_target" {
  max_capacity       = 50
  min_capacity       = 10
  resource_id        = "table/${aws_dynamodb_table.events-connections.name}"
  scalable_dimension = "dynamodb:table:WriteCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "events_connections_write_policy" {
  name               = "DynamoDBWriteCapacityUtilization:${aws_appautoscaling_target.events_connections_write_target.resource_id}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.events_connections_write_target.resource_id
  scalable_dimension = aws_appautoscaling_target.events_connections_write_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.events_connections_write_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBWriteCapacityUtilization"
    }
    target_value = 70.0 # Scale up when utilization exceeds 70%
  }
}

# Auto-scaling for SubscriptionIndex GSI read capacity
resource "aws_appautoscaling_target" "events_connections_gsi_read_target" {
  max_capacity       = 100
  min_capacity       = 25
  resource_id        = "table/${aws_dynamodb_table.events-connections.name}/index/SubscriptionIndex"
  scalable_dimension = "dynamodb:index:ReadCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "events_connections_gsi_read_policy" {
  name               = "DynamoDBReadCapacityUtilization:${aws_appautoscaling_target.events_connections_gsi_read_target.resource_id}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.events_connections_gsi_read_target.resource_id
  scalable_dimension = aws_appautoscaling_target.events_connections_gsi_read_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.events_connections_gsi_read_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBReadCapacityUtilization"
    }
    target_value = 70.0 # Scale up when utilization exceeds 70%
  }
}

# Auto-scaling for SubscriptionIndex GSI write capacity
resource "aws_appautoscaling_target" "events_connections_gsi_write_target" {
  max_capacity       = 50
  min_capacity       = 10
  resource_id        = "table/${aws_dynamodb_table.events-connections.name}/index/SubscriptionIndex"
  scalable_dimension = "dynamodb:index:WriteCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "events_connections_gsi_write_policy" {
  name               = "DynamoDBWriteCapacityUtilization:${aws_appautoscaling_target.events_connections_gsi_write_target.resource_id}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.events_connections_gsi_write_target.resource_id
  scalable_dimension = aws_appautoscaling_target.events_connections_gsi_write_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.events_connections_gsi_write_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBWriteCapacityUtilization"
    }
    target_value = 70.0 # Scale up when utilization exceeds 70%
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
  name           = "CompilerRouting"
  billing_mode   = "PROVISIONED"
  read_capacity  = 50 # Higher baseline for frequent compiler lookups
  write_capacity = 5  # Lower baseline for infrequent routing updates
  hash_key       = "compilerId"

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
  table_class = "STANDARD" # Default, optimized for frequent reads/writes

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Purpose = "Compiler to queue routing mappings"
    Project = "compiler-explorer"
  }
}

# Auto-scaling for CompilerRouting table read capacity
resource "aws_appautoscaling_target" "compiler_routing_read_target" {
  max_capacity       = 200
  min_capacity       = 50
  resource_id        = "table/${aws_dynamodb_table.compiler_routing.name}"
  scalable_dimension = "dynamodb:table:ReadCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "compiler_routing_read_policy" {
  name               = "DynamoDBReadCapacityUtilization:${aws_appautoscaling_target.compiler_routing_read_target.resource_id}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.compiler_routing_read_target.resource_id
  scalable_dimension = aws_appautoscaling_target.compiler_routing_read_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.compiler_routing_read_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBReadCapacityUtilization"
    }
    target_value = 70.0 # Scale up when utilization exceeds 70%
  }
}

# Auto-scaling for CompilerRouting table write capacity
resource "aws_appautoscaling_target" "compiler_routing_write_target" {
  max_capacity       = 25
  min_capacity       = 5
  resource_id        = "table/${aws_dynamodb_table.compiler_routing.name}"
  scalable_dimension = "dynamodb:table:WriteCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "compiler_routing_write_policy" {
  name               = "DynamoDBWriteCapacityUtilization:${aws_appautoscaling_target.compiler_routing_write_target.resource_id}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.compiler_routing_write_target.resource_id
  scalable_dimension = aws_appautoscaling_target.compiler_routing_write_target.scalable_dimension
  service_namespace  = aws_appautoscaling_target.compiler_routing_write_target.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "DynamoDBWriteCapacityUtilization"
    }
    target_value = 70.0 # Scale up when utilization exceeds 70%
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
