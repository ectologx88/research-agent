terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = "us-east-1"
  profile = "seth-dev"
}

resource "aws_lambda_function" "classifier" {
  function_name = "research-agent-classifier"
  role          = aws_iam_role.lambda.arn
  handler       = "src.lambda_handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 256

  filename         = "${path.module}/../dist/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../dist/lambda.zip")

  environment {
    variables = {
      NEWSBLUR_USERNAME    = "PLACEHOLDER"  # override via SSM or secrets
      NEWSBLUR_PASSWORD    = "PLACEHOLDER"
      DYNAMODB_TABLE_NAME  = aws_dynamodb_table.processing_state.name
      DYNAMODB_REGION      = "us-east-1"
      BEDROCK_REGION       = "us-east-1"
      BEDROCK_MODEL_ID     = "anthropic.claude-3-5-haiku-20241022-v1:0"
      MAX_STORIES_PER_RUN  = "100"
      NEWSBLUR_MIN_SCORE   = "0"
      MARK_AS_READ         = "false"
    }
  }

  tags = {
    Project = "research-agent"
    Phase   = "1"
  }
}

resource "aws_cloudwatch_log_group" "classifier" {
  name              = "/aws/lambda/${aws_lambda_function.classifier.function_name}"
  retention_in_days = 30

  tags = {
    Project = "research-agent"
  }
}

# Optional: schedule the pipeline to run every 12 hours
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "research-agent-schedule"
  schedule_expression = "rate(12 hours)"

  tags = {
    Project = "research-agent"
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = aws_lambda_function.classifier.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.classifier.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
