# Dead letter queues
resource "aws_sqs_queue" "ai_ml_dlq" {
  name                      = "personal-journalist-ai-ml-dlq"
  message_retention_seconds = 604800 # 7 days
  tags                      = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_sqs_queue" "world_dlq" {
  name                      = "personal-journalist-world-dlq"
  message_retention_seconds = 604800
  tags                      = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_sqs_queue" "briefing_dlq" {
  name                      = "personal-journalist-briefing-dlq"
  message_retention_seconds = 604800
  tags                      = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_sqs_queue" "ai_ml" {
  name                       = "research-agent-ai-ml"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ai_ml_dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_sqs_queue" "world" {
  name                       = "research-agent-world"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.world_dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_sqs_queue" "briefing" {
  name                       = "research-agent-briefing"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.briefing_dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

# SQS → Lambda 2 trigger (both ai-ml and world queues trigger summarizer)
resource "aws_lambda_event_source_mapping" "summarizer_ai_ml" {
  event_source_arn = aws_sqs_queue.ai_ml.arn
  function_name    = aws_lambda_function.summarizer.arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "summarizer_world" {
  event_source_arn = aws_sqs_queue.world.arn
  function_name    = aws_lambda_function.summarizer.arn
  batch_size       = 1
}

# SQS → Lambda 3 trigger
resource "aws_lambda_event_source_mapping" "briefing" {
  event_source_arn = aws_sqs_queue.briefing.arn
  function_name    = aws_lambda_function.briefing.arn
  batch_size       = 1
}
