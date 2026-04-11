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

data "aws_ssm_parameter" "raindrop_personal_brief_id" {
  name            = "/prod/ResearchAgent/Raindrop_Personal_Brief_Id"
  with_decryption = false
}

data "aws_ssm_parameter" "site_url" {
  name            = "/prod/ResearchAgent/Site_Url"
  with_decryption = false
}

data "aws_ssm_parameter" "brief_api_key" {
  # Value must match BRIEF_API_KEY set in AWS Amplify Environment Variables for the website
  name            = "/prod/ResearchAgent/Brief_Api_Key"
  with_decryption = true
}

data "aws_ssm_parameter" "telegram_bot_token" {
  name            = "/prod/ResearchAgent/Telegram_Bot_Token"
  with_decryption = true
}

data "aws_ssm_parameter" "telegram_chat_id" {
  name            = "/prod/ResearchAgent/Telegram_Chat_Id"
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
      DYNAMODB_REGION              = "us-east-1"
      DYNAMODB_STORY_STAGING_TABLE = aws_dynamodb_table.story_staging.name
      DYNAMODB_SIGNAL_TABLE        = aws_dynamodb_table.signal_tracker.name
      FETCH_STRATEGY               = "hours_back"
      NEWSBLUR_HOURS_BACK          = "26"
      MAX_STORIES_PER_RUN          = "150"
      MARK_AS_READ                 = "false"
      RAINDROP_AIML_COLLECTION_ID  = data.aws_ssm_parameter.raindrop_aiml_collection_id.value
      RAINDROP_WORLD_COLLECTION_ID = data.aws_ssm_parameter.raindrop_world_collection_id.value
      SQS_AIML_QUEUE_URL           = aws_sqs_queue.ai_ml.url
      SQS_WORLD_QUEUE_URL          = aws_sqs_queue.world.url
      AI_ML_RESEARCH_MAX_STORIES   = "40"
      AI_ML_RESEARCH_MIN_SCORE     = "0"
      AI_ML_COMMUNITY_MAX_STORIES  = "100"
      WORLD_NEWS_MAX_STORIES       = "50"
      WORLD_SCIENCE_MAX_STORIES    = "30"
      WORLD_TECH_MAX_STORIES       = "25"
      GENERAL_TECH_MAX_STORIES     = "60"
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
      RAINDROP_TOKEN               = data.aws_ssm_parameter.raindrop_token.value
      RAINDROP_AIML_COLLECTION_ID  = data.aws_ssm_parameter.raindrop_aiml_collection_id.value
      RAINDROP_WORLD_COLLECTION_ID = data.aws_ssm_parameter.raindrop_world_collection_id.value
      DYNAMODB_REGION              = "us-east-1"
      DYNAMODB_STORY_STAGING_TABLE = aws_dynamodb_table.story_staging.name
      BEDROCK_REGION               = "us-east-1"
      BEDROCK_SUMMARIZER_MODEL_ID  = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
      SQS_BRIEFING_QUEUE_URL       = aws_sqs_queue.briefing.url
      NEWSBLUR_USERNAME            = data.aws_ssm_parameter.newsblur_user.value
      NEWSBLUR_PASSWORD            = data.aws_ssm_parameter.newsblur_pass.value
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
  timeout       = 600
  memory_size   = 256

  filename         = "${path.module}/../dist/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/../dist/lambda.zip")

  environment {
    variables = {
      RAINDROP_TOKEN             = data.aws_ssm_parameter.raindrop_token.value
      RAINDROP_PERSONAL_BRIEF_ID = data.aws_ssm_parameter.raindrop_personal_brief_id.value
      SITE_URL                   = data.aws_ssm_parameter.site_url.value
      BRIEF_API_KEY              = data.aws_ssm_parameter.brief_api_key.value
      DYNAMODB_REGION            = "us-east-1"
      DYNAMODB_SIGNAL_TABLE      = aws_dynamodb_table.signal_tracker.name
      DYNAMODB_BRIEFING_TABLE    = aws_dynamodb_table.briefing_archive.name
      BEDROCK_REGION             = "us-east-1"
      BEDROCK_BRIEFING_MODEL_ID  = "us.anthropic.claude-sonnet-4-6"
      TELEGRAM_BOT_TOKEN         = data.aws_ssm_parameter.telegram_bot_token.value
      TELEGRAM_CHAT_ID           = data.aws_ssm_parameter.telegram_chat_id.value
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
