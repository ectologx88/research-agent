import json
from shared.logger import log

def test_emits_json_to_stdout(capsys):
    log("INFO", "test event", story_hash="abc123", routing_decision="AI_ML")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["level"] == "INFO"
    assert data["event"] == "test event"
    assert data["story_hash"] == "abc123"
    assert data["routing_decision"] == "AI_ML"
    assert "timestamp" in data

def test_level_included(capsys):
    log("WARNING", "something odd", feed_name="BBC News")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["level"] == "WARNING"
    assert data["feed_name"] == "BBC News"
