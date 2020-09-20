data "aws_sns_topic" "alert" {
  name = "CompilerExplorerAlert"
}

locals {
  approx_monthly_budget = 550
}

resource "aws_cloudwatch_metric_alarm" "resp_90ile_15m_too_slow" {
  alarm_name          = "90ile_15m_resp_too_slow"
  alarm_description   = "Monitor site response time, 90%ile being too slow"
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  threshold           = 4
  metric_name         = "TargetResponseTime"
  namespace           = "AWS/ApplicationELB"
  extended_statistic  = "p90"
  period              = 15 * 60

  dimensions          = {
    LoadBalancer = aws_alb.GccExplorerApp.arn_suffix
  }
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}

resource "aws_cloudwatch_metric_alarm" "halfway_budget" {
  alarm_name          = "HalfBudget"
  alarm_description   = "A heads up we're halfway through the budget"
  threshold           = local.approx_monthly_budget / 2
  period              = 6 * 60 * 60
  evaluation_periods  = 1
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  dimensions          = {
    Currency = "USD"
  }
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}

resource "aws_cloudwatch_metric_alarm" "budget_hit" {
  alarm_name          = "BudgetHit"
  alarm_description   = "We've hit the budget"
  threshold           = local.approx_monthly_budget
  period              = 6 * 60 * 60
  evaluation_periods  = 1
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  comparison_operator = "GreaterThanThreshold"
  statistic           = "Maximum"
  dimensions          = {
    Currency = "USD"
  }
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}

resource "aws_cloudwatch_metric_alarm" "bankrupcy" {
  alarm_name          = "EmergencyBillingAlert"
  alarm_description   = "Is Matt about to have to sell his house?"
  threshold           = local.approx_monthly_budget * 1.5
  period              = 6 * 60 * 60
  evaluation_periods  = 1
  namespace           = "AWS/Billing"
  metric_name         = "EstimatedCharges"
  comparison_operator = "GreaterThanThreshold"
  statistic           = "Maximum"
  dimensions          = {
    Currency = "USD"
  }
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}

resource "aws_cloudwatch_metric_alarm" "cloudfront_high_5xx" {
  for_each            = {
    "godbolt.org"           = aws_cloudfront_distribution.ce-godbolt-org,
    "compiler-explorer.com" = aws_cloudfront_distribution.compiler-explorer-com,
    "godbo.lt"              = aws_cloudfront_distribution.godbo-lt,
    "ce.cdn.net"            = aws_cloudfront_distribution.static-ce-cdn-net
  }
  alarm_name          = "High5xx_${each.key}"
  alarm_description   = "Unnacceptable level of 5xx errors on ${each.key}"
  evaluation_periods  = 4
  datapoints_to_alarm = 4
  threshold           = 3
  metric_name         = "5xxErrorRate"
  namespace           = "AWS/CloudFront"
  statistic           = "Average"
  period              = 5 * 60

  dimensions          = {
    DistributionId = each.value.id
    Region         = "Global"
  }
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}


resource "aws_cloudwatch_metric_alarm" "traffic" {
  alarm_name         = "TrafficAnomaly"
  alarm_description  = "A traffic anomaly was detected (too much or too little)"
  evaluation_periods = 3
  datapoints_to_alarm = 3
  threshold_metric_id = "e1"

  metric_query {
    id          = "e1"
    expression  = "ANOMALY_DETECTION_BAND(m1)"
    label       = "RequestCount (Expected)"
    return_data = true
  }

  metric_query {
    id          = "m1"
    return_data = true
    metric {
      metric_name = "RequestCount"
      namespace   = "AWS/ApplicationELB"
      period      = 5*60
      stat        = "Sum"
      dimensions  = {
        LoadBalancer = aws_alb.GccExplorerApp.arn_suffix
      }
    }
  }

  comparison_operator = "LessThanLowerOrGreaterThanUpperThreshold"
  alarm_actions       = [data.aws_sns_topic.alert.arn]
}
