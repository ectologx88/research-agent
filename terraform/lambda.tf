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

data "aws_ssm_parameter" "newsblur_user" {
  name            = "/prod/ResearchAgent/NewsBlur_User"
  with_decryption = true
}

data "aws_ssm_parameter" "newsblur_pass" {
  name            = "/prod/ResearchAgent/NewsBlur_Pass"
  with_decryption = true
}

data "aws_ssm_parameter" "raindrop_token" {
  name            = "/prod/ResearchAgent/Raindrop_Token"
  with_decryption = true
}

data "aws_ssm_parameter" "raindrop_briefing_collection_id" {
  name            = "/prod/ResearchAgent/Raindrop_Briefing_Collection_Id"
  with_decryption = false
}

data "aws_ssm_parameter" "raindrop_aiml_collection_id" {
  name            = "/prod/ResearchAgent/Raindrop_AiMl_Collection_Id"
  with_decryption = false
}

data "aws_ssm_parameter" "raindrop_world_collection_id" {
  name            = "/prod/ResearchAgent/Raindrop_World_Collection_Id"
  with_decryption = false
}

resource "aws_lambda_function" "triage" {
  function_name = "research-agent-triage"
  role          = aws_iam_role.lambda.arn
  handler       = "src.handlers.triage_handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 180
  memory_size   = 256

  filename         = "${path.module}/../dist/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../dist/lambda.zip")

  environment {
    variables = {
      NEWSBLUR_USERNAME            = data.aws_ssm_parameter.newsblur_user.value
      NEWSBLUR_PASSWORD            = data.aws_ssm_parameter.newsblur_pass.value
      RAINDROP_TOKEN               = data.aws_ssm_parameter.raindrop_token.value
      DYNAMODB_TABLE_NAME          = aws_dynamodb_table.processing_state.name
      DYNAMODB_REGION              = "us-east-1"
      FETCH_STRATEGY               = "hours_back"
      HOURS_BACK_DEFAULT           = "12"
      MAX_STORIES_PER_RUN          = "150"
      MARK_AS_READ                 = "false"
      RAINDROP_AIML_COLLECTION_ID  = data.aws_ssm_parameter.raindrop_aiml_collection_id.value
      RAINDROP_WORLD_COLLECTION_ID = data.aws_ssm_parameter.raindrop_world_collection_id.value
      SQS_AIML_QUEUE_URL           = aws_sqs_queue.ai_ml.url
      SQS_WORLD_QUEUE_URL          = aws_sqs_queue.world.url
      NEWSBLUR_MIN_SCORE           = "1"
    }
  }

  tags = {
    Project = "research-agent"
    Phase   = "3"
  }
}

resource "aws_cloudwatch_log_group" "triage" {
  name              = "/aws/lambda/${aws_lambda_function.triage.function_name}"
  retention_in_days = 30

  tags = {
    Project = "research-agent"
  }
}

resource "aws_lambda_function" "summarizer" {
  function_name = "research-agent-summarizer"
  role          = aws_iam_role.lambda.arn
  handler       = "src.handlers.summarizer_handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 900
  memory_size   = 512

  filename         = "${path.module}/../dist/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../dist/lambda.zip")

  environment {
    variables = {
      RAINDROP_TOKEN                  = data.aws_ssm_parameter.raindrop_token.value
      DYNAMODB_TABLE_NAME             = aws_dynamodb_table.processing_state.name
      DYNAMODB_REGION                 = "us-east-1"
      BEDROCK_REGION                  = "us-east-1"
      BEDROCK_MODEL_ID                = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
      RAINDROP_BRIEFING_COLLECTION_ID = data.aws_ssm_parameter.raindrop_briefing_collection_id.value
      SQS_BRIEFING_QUEUE_URL          = aws_sqs_queue.briefing.url
    }
  }

  tags = {
    Project = "research-agent"
    Phase   = "3"
  }
}

resource "aws_cloudwatch_log_group" "summarizer" {
  name              = "/aws/lambda/${aws_lambda_function.summarizer.function_name}"
  retention_in_days = 30

  tags = {
    Project = "research-agent"
  }
}

resource "aws_lambda_function" "briefing" {
  function_name = "research-agent-briefing"
  role          = aws_iam_role.lambda.arn
  handler       = "src.handlers.briefing_handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 256

  filename         = "${path.module}/../dist/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../dist/lambda.zip")

  environment {
    variables = {
      RAINDROP_TOKEN                  = data.aws_ssm_parameter.raindrop_token.value
      DYNAMODB_TABLE_NAME             = aws_dynamodb_table.processing_state.name
      DYNAMODB_REGION                 = "us-east-1"
      BEDROCK_REGION                  = "us-east-1"
      BEDROCK_BRIEFING_MODEL_ID       = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
      RAINDROP_BRIEFING_COLLECTION_ID = data.aws_ssm_parameter.raindrop_briefing_collection_id.value
    }
  }

  tags = {
    Project = "research-agent"
    Phase   = "3"
  }
}

resource "aws_cloudwatch_log_group" "briefing" {
  name              = "/aws/lambda/${aws_lambda_function.briefing.function_name}"
  retention_in_days = 30

  tags = {
    Project = "research-agent"
  }
}

# Schedule: 6 AM and 6 PM US Central (11:00 and 23:00 UTC)
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "research-agent-schedule"
  schedule_expression = "cron(0 11,23 * * ? *)"

  tags = {
    Project = "research-agent"
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = aws_lambda_function.triage.arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.triage.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
