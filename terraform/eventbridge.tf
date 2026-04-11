# terraform/eventbridge.tf
# Single weekday run at 13:00 UTC = 8 AM CDT / 7 AM CST
# Monday override (hours_back=74) is handled in code, not here.

resource "aws_cloudwatch_event_rule" "morning_triage" {
  name                = "personal-journalist-morning"
  description         = "Trigger triage Lambda weekdays at 13:00 UTC (8 AM CDT)"
  schedule_expression = "cron(0 13 ? * MON-FRI *)"
  state               = "ENABLED"

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_event_rule" "evening_triage" {
  name                = "personal-journalist-evening"
  description         = "DISABLED — kept as rollback lever; re-enable to restore PM run"
  schedule_expression = "cron(0 23 * * ? *)"
  state               = "DISABLED"

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_event_target" "morning_triage_target" {
  rule      = aws_cloudwatch_event_rule.morning_triage.name
  target_id = "TriageLambdaMorning"
  arn       = aws_lambda_function.triage.arn
}

resource "aws_cloudwatch_event_target" "evening_triage_target" {
  rule      = aws_cloudwatch_event_rule.evening_triage.name
  target_id = "TriageLambdaEvening"
  arn       = aws_lambda_function.triage.arn
}

resource "aws_lambda_permission" "allow_eventbridge_morning" {
  statement_id  = "AllowEventBridgeMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.triage.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.morning_triage.arn
}

resource "aws_lambda_permission" "allow_eventbridge_evening" {
  statement_id  = "AllowEventBridgeEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.triage.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.evening_triage.arn
}
