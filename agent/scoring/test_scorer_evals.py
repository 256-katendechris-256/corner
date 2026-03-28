# tests/scoring/test_scorer_evals.py
import pytest
from agent.scoring.scorer import score_item
from agent.normalisation.schemas import SourceItem, SourceTier
from datetime import datetime, timezone

# Known high-signal item — should score high on relevance
HIGH_SIGNAL = SourceItem(
    id='test-001',
    title='GPT-4.1 now generally available with 1M context',
    source_name='OpenAI API Changelog',
    source_tier=SourceTier.TIER1,
    published_at=datetime.now(timezone.utc),
    canonical_url='https://platform.openai.com/docs/changelog',
    raw_content='OpenAI has released GPT-4.1, now generally available to all '
                'API users. The model supports a 1 million token context window '
                'and is priced lower than GPT-4-turbo. Existing GPT-4 prompts '
                'are compatible. Migration guide available.',
)

def test_high_signal_item_scores_above_threshold():
    result = score_item(HIGH_SIGNAL)
    assert result is not None, 'Scorer returned None'
    assert result.relevance_score >= 0.7, (
        f'Expected relevance >= 0.7, got {result.relevance_score}'
    )
    assert result.what_changed, 'what_changed should not be empty'
    assert result.why_it_matters, 'why_it_matters should not be empty'
    assert len(result.impact_tags) >= 1, 'Should have at least one impact tag'