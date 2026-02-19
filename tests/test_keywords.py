from config.keywords import get_boost_tags

def test_open_source_gets_boost():
    tags = get_boost_tags("Open-source LLM beats GPT-4 on benchmarks", [])
    assert "boost:open-source" in tags

def test_rdd_gets_long_signal():
    tags = get_boost_tags("New theory of consciousness links emergence to information", [])
    assert "long-signal:rdd" in tags

def test_user_curated_passed_through():
    tags = get_boost_tags("anything", ["boost:user-curated"])
    assert "boost:user-curated" in tags

def test_no_false_positives_on_plain_title():
    tags = get_boost_tags("Company raises Series B funding round", [])
    assert tags == []

def test_industrial_keywords_not_boosted():
    # boost:industrial no longer exists — industrial AI titles get no special tag
    tags = get_boost_tags("AI for predictive maintenance in chemical plants", [])
    assert "boost:industrial" not in tags

def test_open_source_overlap_gets_only_open_source_tag():
    # open-source + industrial phrasing → only boost:open-source (industrial tag removed)
    tags = get_boost_tags("Open-source AI for manufacturing process control", [])
    assert "boost:open-source" in tags
    assert "boost:industrial" not in tags

def test_rdd_neurodivergent_gets_long_signal():
    tags = get_boost_tags("Study links autism and cognitive flexibility in problem solving", [])
    assert "long-signal:rdd" in tags
