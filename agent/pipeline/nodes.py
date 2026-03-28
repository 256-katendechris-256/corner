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
    """Stage 2 — embed, dedup, store. Returns only genuinely new items."""
    logger.info("=== NORMALISE ===")
    try:
        # Filter out items with too little usable content before storing
        readable = []
        for item in state["raw_items"]:
            content = item.raw_content or ""
            # Require at least 200 chars of actual readable text
            # items with garbled encoding produce very short clean text
            clean_chars = sum(1 for c in content if c.isascii() and c.isprintable())
            ratio = clean_chars / max(len(content), 1)
            if len(content) < 200 or ratio < 0.6:
                logger.warning(f"  SKIPPED (low quality content): {item.title[:60]}")
                continue
            readable.append(item)

        logger.info(f"  {len(readable)}/{len(state['raw_items'])} items passed quality check")
        state["new_items"] = normalise_and_store(readable)
        logger.info(f"  {len(state['new_items'])} new items after dedup")
    except Exception as e:
        logger.error(f"Normalisation failed: {e}")
        state["errors"].append(f"normalise: {e}")
        state["new_items"] = []
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
    """Stage 4 — draft the daily digest from scored items."""
    logger.info("=== SYNTHESISE ===")

    # Only include items above the relevance threshold
    MIN_RELEVANCE = 0.3
    quality_items = [
        item for item in state["scored_items"]
        if item.relevance_score >= MIN_RELEVANCE
    ]

    logger.info(
        f"  {len(quality_items)}/{len(state['scored_items'])} items "
        f"above relevance threshold ({MIN_RELEVANCE})"
    )

    if not quality_items:
        state["digest_draft"] = (
            "No new high-signal items today "
            f"(threshold: {MIN_RELEVANCE}, "
            f"total scored: {len(state['scored_items'])})."
        )
        return state

    # Sort by relevance, take top 8
    top = sorted(quality_items,
                 key=lambda x: x.relevance_score, reverse=True)[:8]

    lines = ["## AI Market Intelligence — Daily Digest\n"]
    for item in top:
        si = item.source_item
        lines += [
            f"### {si.title}",
            f"**Source:** {si.source_name}  |  "
            f"**Tier:** {si.source_tier.value}  |  "
            f"**Relevance:** {item.relevance_score:.2f}  |  "
            f"**Urgency:** {item.urgency_score:.2f}",
            f"**What changed:** {item.what_changed}",
            f"**Why it matters:** {item.why_it_matters}",
        ]
        if item.recommended_action:
            lines.append(f"**Recommended action:** {item.recommended_action}")
        if item.impact_tags:
            lines.append(
                f"**Tags:** {', '.join(t.value for t in item.impact_tags)}"
            )
        lines.append(f"**URL:** {si.canonical_url}\n")

    # Summary footer
    lines += [
        "---",
        f"_Run ID: {state['run_id']} | "
        f"Items scored: {len(state['scored_items'])} | "
        f"Published: {len(top)} | "
        f"Filtered (low relevance): "
        f"{len(state['scored_items']) - len(quality_items)}_"
    ]

    if state["errors"]:
        lines.append(
            f"_Pipeline errors: {len(state['errors'])} — check logs_"
        )

    state["digest_draft"] ="\n".join(lines)