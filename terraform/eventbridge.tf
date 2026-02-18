# terraform/eventbridge.tf
# 11:00 UTC = 6AM CDT (summer) / 5AM CST (winter) — acceptable drift for a news briefing
# 23:00 UTC = 6PM CDT (summer) / 5PM CST (winter)

resource "aws_cloudwatch_event_rule" "morning_triage" {
  name                = "personal-journalist-morning"
  description         = "Trigger Lambda 1 triage at 6AM CDT / 5AM CST"
  schedule_expression = "cron(0 11 * * ? *)"
  state               = "ENABLED"

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_event_rule" "evening_triage" {
  name                = "personal-journalist-evening"
  description         = "Trigger Lambda 1 triage at 6PM CDT / 5PM CST"
  schedule_expression = "cron(0 23 * * ? *)"
  state               = "ENABLED"

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
