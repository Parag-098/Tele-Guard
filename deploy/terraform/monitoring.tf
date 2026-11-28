resource "aws_cloudwatch_log_group" "app" {
  name              = "/teleguard/production"
  retention_in_days = 14
}
resource "aws_sns_topic" "alarms" {
  name = "teleguard-alarms"
}
resource "aws_sns_topic_subscription" "operator" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.operations_email
}
resource "aws_budgets_budget" "demo" {
  name         = "teleguard-account-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.operations_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.operations_email]
  }
}

resource "aws_cloudwatch_log_metric_filter" "api_latency" {
  name           = "teleguard-api-latency"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ ($.request.uri = \"/api/*\") && ($.duration >= 0) }"
  metric_transformation {
    name      = "ApiDurationSeconds"
    namespace = "TeleGuard/Http"
    value     = "$.duration"
    unit      = "Seconds"
  }
}
resource "aws_cloudwatch_log_metric_filter" "api_errors" {
  name           = "teleguard-api-errors"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = "{ ($.request.uri = \"/api/*\") && ($.status >= 500) }"
  metric_transformation {
    name          = "ApiServerErrors"
    namespace     = "TeleGuard/Http"
    value         = "1"
    default_value = 0
    unit          = "Count"
  }
}
resource "aws_cloudwatch_metric_alarm" "http" {
  for_each = {
    latency = { metric = "ApiDurationSeconds", threshold = 0.5, extended_statistic = "p95", statistic = null }
    errors  = { metric = "ApiServerErrors", threshold = 5, extended_statistic = null, statistic = "Sum" }
  }
  alarm_name                            = "teleguard-http-${each.key}"
  comparison_operator                   = "GreaterThanThreshold"
  evaluation_periods                    = 3
  datapoints_to_alarm                   = 2
  period                                = 60
  namespace                             = "TeleGuard/Http"
  metric_name                           = each.value.metric
  threshold                             = each.value.threshold
  statistic                             = each.value.statistic
  extended_statistic                    = each.value.extended_statistic
  evaluate_low_sample_count_percentiles = each.value.extended_statistic == null ? null : "ignore"
  treat_missing_data                    = "notBreaching"
  alarm_actions                         = [aws_sns_topic.alarms.arn]
}
resource "aws_cloudwatch_metric_alarm" "instance" {
  alarm_name          = "teleguard-ec2-status"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  period              = 60
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  threshold           = 1
  statistic           = "Maximum"
  dimensions          = { InstanceId = aws_instance.host.id }
  treat_missing_data  = "missing"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "operations" {
  for_each = {
    readiness = { metric = "PublicReadiness", threshold = 1, operation = "LessThanThreshold", missing = "breaching" }
    worker    = { metric = "WorkerReady", threshold = 1, operation = "LessThanThreshold", missing = "breaching" }
    disk      = { metric = "DiskUsedPercent", threshold = 85, operation = "GreaterThanThreshold", missing = "missing" }
    memory    = { metric = "MemoryUsedPercent", threshold = 90, operation = "GreaterThanThreshold", missing = "missing" }
    jobs      = { metric = "OldestQueuedMinutes", threshold = 20, operation = "GreaterThanThreshold", missing = "missing" }
  }
  alarm_name          = "teleguard-${each.key}"
  comparison_operator = each.value.operation
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  period              = 60
  namespace           = "TeleGuard/Operations"
  metric_name         = each.value.metric
  threshold           = each.value.threshold
  statistic           = "Average"
  dimensions          = { InstanceId = aws_instance.host.id }
  treat_missing_data  = each.value.missing
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
