# terraform/cloudwatch.tf

# DLQ depth alarms
resource "aws_cloudwatch_metric_alarm" "briefing_dlq_depth" {
  alarm_name          = "personal-journalist-briefing-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0 # Any message in briefing DLQ is worth alerting
  alarm_description   = "A briefing failed after 3 attempts"
  dimensions          = { QueueName = aws_sqs_queue.briefing_dlq.name }
  tags                = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_cloudwatch_metric_alarm" "ai_ml_dlq_depth" {
  alarm_name          = "personal-journalist-ai-ml-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 2 # Avoid alert fatigue from transient timeouts
  alarm_description   = "Multiple AI/ML stories failed scoring after 3 attempts"
  dimensions          = { QueueName = aws_sqs_queue.ai_ml_dlq.name }
  tags                = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_cloudwatch_metric_alarm" "world_dlq_depth" {
  alarm_name          = "personal-journalist-world-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 2
  alarm_description   = "Multiple World stories failed scoring after 3 attempts"
  dimensions          = { QueueName = aws_sqs_queue.world_dlq.name }
  tags                = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

# Lambda 1 duration alarm (approaching 180s timeout)
resource "aws_cloudwatch_metric_alarm" "triage_duration" {
  alarm_name          = "personal-journalist-triage-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Maximum"
  threshold           = 55000 # milliseconds — alert before 60s
  alarm_description   = "Lambda 1 triage approaching timeout"
  dimensions          = { FunctionName = aws_lambda_function.triage.function_name }
  tags                = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

# Cost alarm — custom metric emitted by Lambda 2 and 3
resource "aws_cloudwatch_metric_alarm" "daily_api_cost" {
  alarm_name          = "personal-journalist-daily-api-cost"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "estimated_api_cost"
  namespace           = "PersonalJournalist/Cost"
  period              = 86400 # 24h
  statistic           = "Sum"
  threshold           = 3.00
  alarm_description   = "Estimated daily Anthropic API cost exceeds $3.00"
  treat_missing_data  = "notBreaching"
  tags                = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}
