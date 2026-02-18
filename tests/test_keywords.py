from config.keywords import get_boost_tags

def test_open_source_gets_boost():
    tags = get_boost_tags("Open-source LLM beats GPT-4 on benchmarks", [])
    assert "boost:open-source" in tags

def test_industrial_gets_boost():
    tags = get_boost_tags("AI for predictive maintenance in chemical plants", [])
    assert "boost:industrial" in tags

def test_rdd_gets_long_signal():
    tags = get_boost_tags("New theory of consciousness links emergence to information", [])
    assert "long-signal:rdd" in tags

def test_user_curated_passed_through():
    tags = get_boost_tags("anything", ["boost:user-curated"])
    assert "boost:user-curated" in tags

def test_no_false_positives_on_plain_title():
    tags = get_boost_tags("Company raises Series B funding round", [])
    assert tags == []

def test_overlap_produces_both_tags():
    # Intentional: open-source + industrial signals can stack
    tags = get_boost_tags("Open-source AI for manufacturing process control", [])
    assert "boost:open-source" in tags
    assert "boost:industrial" in tags
