resource "aws_dynamodb_table" "classified_stories" {
  name         = "newsblur-classified-stories"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "story_hash"
  range_key    = "classified_at"

  attribute {
    name = "story_hash"
    type = "S"
  }

  attribute {
    name = "classified_at"
    type = "N"
  }

  attribute {
    name = "date"
    type = "S"
  }

  attribute {
    name = "overall_score"
    type = "N"
  }

  global_secondary_index {
    name            = "classification-by-date"
    hash_key        = "date"
    range_key       = "overall_score"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project = "research-agent"
    Phase   = "1"
  }
}
