# agent/pipeline/nodes.py
from agent.pipeline.state import PipelineState
from agent.ingestion.tier1 import ingest_tier1
from agent.ingestion.rss import ingest_tier2
from agent.normalisation.normaliser import normalise_and_store
from agent.scoring.scorer import score_item
import logging
import uuid

logger = logging.getLogger(__name__)

def node_collect(state: PipelineState) -> PipelineState:
    """Fetch all sources — Tier 1 and Tier 2."""
    logger.info('--- COLLECT ---')
    t1 = ingest_tier1()
    t2 = ingest_tier2(max_per_feed=5)
    state['raw_items'] = t1 + t2
    logger.info(f'Collected {len(state["raw_items"])} raw items')
    return state

def node_normalise(state: PipelineState) -> PipelineState:
    """Embed, deduplicate, and store. Returns only new items."""
    logger.info('--- NORMALISE ---')
    state['new_items'] = normalise_and_store(state['raw_items'])
    logger.info(f'{len(state["new_items"])} new items after dedup')
    return state

def node_score(state: PipelineState) -> PipelineState:
    """Score each new item with the LLM."""
    logger.info('--- SCORE ---')
    scored = []
    for item in state['new_items']:
        result = score_item(item)
        if result:
            scored.append(result)
        else:
            state['errors'].append(f'Scoring failed: {item.title}')
    state['scored_items'] = scored
    logger.info(f'Scored {len(scored)} items')
    return state

def node_synthesise(state: PipelineState) -> PipelineState:
    """Draft the daily digest from scored items."""
    logger.info('--- SYNTHESISE ---')
    if not state['scored_items']:
        state['digest_draft'] = 'No new high-signal items today.'
        return state

    # Format top items by relevance score
    top = sorted(state['scored_items'], key=lambda x: x.relevance_score, reverse=True)[:8]
    lines = [f'## AI Market Intelligence — Daily Digest\n']
    for item in top:
        lines.append(f"### {item.source_item.title}")
        lines.append(f"Source: {item.source_item.source_name} | "
                      f"Relevance: {item.relevance_score:.2f}")
        lines.append(f"**What changed:** {item.what_changed}")
        lines.append(f"**Why it matters:** {item.why_it_matters}")
        if item.recommended_action:
            lines.append(f"**Action:** {item.recommended_action}")
        lines.append(f"Tags: {', '.join(t.value for t in item.impact_tags)}")
        lines.append(f"URL: {item.source_item.canonical_url}\n")

    state['digest_draft'] = '\n'.join(lines)
    return state