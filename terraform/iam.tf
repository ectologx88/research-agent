data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "research-agent-classifier-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = {
    Project = "research-agent"
  }
}

# CloudWatch Logs
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# DynamoDB access
data "aws_iam_policy_document" "dynamodb" {
  statement {
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:BatchGetItem",
    ]
    resources = [
      aws_dynamodb_table.processing_state.arn,
    ]
  }
}

resource "aws_iam_role_policy" "dynamodb" {
  name   = "dynamodb-access"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.dynamodb.json
}

# Bedrock access
data "aws_iam_policy_document" "bedrock" {
  statement {
    actions   = ["bedrock:InvokeModel"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "bedrock" {
  name   = "bedrock-access"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.bedrock.json
}

# SSM Parameter Store (read-only, for fetching credentials at runtime)
data "aws_iam_policy_document" "ssm" {
  statement {
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
    ]
    resources = ["arn:aws:ssm:*:*:parameter/prod/ResearchAgent/*"]
  }
}

resource "aws_iam_role_policy" "ssm" {
  name   = "ssm-read"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.ssm.json
}

# SQS access
data "aws_iam_policy_document" "sqs" {
  statement {
    actions = ["sqs:SendMessage"]
    resources = [
      aws_sqs_queue.ai_ml.arn,
      aws_sqs_queue.world.arn,
      aws_sqs_queue.briefing.arn,
    ]
  }

  statement {
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [
      aws_sqs_queue.ai_ml.arn,
      aws_sqs_queue.world.arn,
      aws_sqs_queue.briefing.arn,
    ]
  }
}

resource "aws_iam_role_policy" "sqs" {
  name   = "sqs-access"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.sqs.json
}
