import pytest
from agent.normalisation.schemas import SourceItem, SourceTier
from agent.scoring.scorer import score_item
from datetime import datetime, timezone

# ── Test fixtures ────────────────────────────────────────────────────────────

HIGH_SIGNAL = SourceItem(
    id="test-001",
    title="GPT-4.1 now generally available with 1M context window",
    source_name="OpenAI API Changelog",
    source_tier=SourceTier.TIER1,
    published_at=datetime.now(timezone.utc),
    canonical_url="https://platform.openai.com/docs/changelog",
    raw_content=(
        "OpenAI has released GPT-4.1, now generally available to all API users. "
        "The model supports a 1 million token context window and is priced lower "
        "than GPT-4-turbo. Existing GPT-4 prompts are compatible without changes. "
        "A full migration guide is available in the documentation."
    ),
)

LOW_SIGNAL = SourceItem(
    id="test-002",
    title="OpenAI updates their privacy policy footer",
    source_name="OpenAI News",
    source_tier=SourceTier.TIER1,
    published_at=datetime.now(timezone.utc),
    canonical_url="https://openai.com/news",
    raw_content=(
        "OpenAI has made minor updates to the footer links on their privacy "
        "policy page. No changes to data handling or user terms."
    ),
)

# ── Tests ────────────────────────────────────────────────────────────────────

def test_scorer_returns_result():
    """Scorer must return a ScoredItem, not None."""
    result = score_item(HIGH_SIGNAL)
    assert result is not None, "scorer returned None — check logs for errors"

def test_high_signal_relevance():
    """A major model release should score high relevance for Set Piece."""
    result = score_item(HIGH_SIGNAL)
    assert result is not None
    assert result.relevance_score >= 0.6, (
        f"Expected relevance >= 0.6 for a major model release, got {result.relevance_score}"
    )

def test_scores_are_valid_range():
    """All scores must be floats between 0.0 and 1.0."""
    result = score_item(HIGH_SIGNAL)
    assert result is not None
    for field, val in [
        ("relevance",  result.relevance_score),
        ("novelty",    result.novelty_score),
        ("urgency",    result.urgency_score),
        ("confidence", result.confidence_score),
    ]:
        assert 0.0 <= val <= 1.0, f"{field} score {val} is outside 0.0–1.0"

def test_required_text_fields_populated():
    """what_changed and why_it_matters must not be empty."""
    result = score_item(HIGH_SIGNAL)
    assert result is not None
    assert len(result.what_changed) > 10, "what_changed is too short or empty"
    assert len(result.why_it_matters) > 10, "why_it_matters is too short or empty"

def test_impact_tags_present():
    """A high-signal item must produce at least one impact tag."""
    result = score_item(HIGH_SIGNAL)
    assert result is not None
    assert len(result.impact_tags) >= 1, "Expected at least one impact tag"

def test_low_signal_scores_lower_than_high():
    """A trivial update should score lower relevance than a major model release."""
    high = score_item(HIGH_SIGNAL)
    low  = score_item(LOW_SIGNAL)
    assert high is not None
    assert low  is not None
    assert high.relevance_score > low.relevance_score, (
        f"High signal ({high.relevance_score}) should outscore "
        f"low signal ({low.relevance_score})"
    )

def test_trace_id_assigned():
    """Every scored item must have a trace_id for observability."""
    result = score_item(HIGH_SIGNAL)
    assert result is not None
    assert result.trace_id is not None
    assert len(result.trace_id) > 0
