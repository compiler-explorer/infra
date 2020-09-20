data "aws_sns_topic" "alert" {
  name = "CompilerExplorerAlert"
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