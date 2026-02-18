resource "aws_dynamodb_table" "processing_state" {
  name         = "newsblur-processing-state"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "record_type"
  range_key    = "identifier"

  attribute {
    name = "record_type"
    type = "S"
  }

  attribute {
    name = "identifier"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project = "research-agent"
    Phase   = "1"
    Purpose = "Minimal deduplication and state tracking"
  }
}

resource "aws_dynamodb_table" "story_staging" {
  name         = "story-staging"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "story_hash"
  range_key    = "briefing_type"

  attribute {
    name = "story_hash"
    type = "S"
  }

  attribute {
    name = "briefing_type"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_dynamodb_table" "signal_tracker" {
  name         = "signal-tracker"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "signal_key"

  attribute {
    name = "signal_key"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_dynamodb_table" "briefing_archive" {
  name         = "briefing-archive"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "briefing_date"
  range_key    = "briefing_type"

  attribute {
    name = "briefing_date"
    type = "S"
  }

  attribute {
    name = "briefing_type"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}
