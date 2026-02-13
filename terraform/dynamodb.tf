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
