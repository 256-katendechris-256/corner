# agent/pipeline/nodes.py
import logging
import time
from agent.pipeline.state import PipelineState
from agent.ingestion.tier1 import ingest_tier1
from agent.ingestion.rss import ingest_tier2
from agent.normalisation.normaliser import (
    normalise_and_store, save_scored_item, log_run_stage,
)
from agent.scoring.scorer import score_item

logger = logging.getLogger(__name__)

NOISY_SOURCES = {
    "OpenAI Developer Forum",
}

def node_collect(state: PipelineState) -> dict:
    logger.info("=== COLLECT ===")
    t1 = ingest_tier1()
    t2 = ingest_tier2(max_per_feed=5)
    all_items = t1 + t2

    filtered = [i for i in all_items if i.source_name not in NOISY_SOURCES]
    skipped  = len(all_items) - len(filtered)
    if skipped:
        logger.info(f"  Filtered {skipped} items from noisy sources")

    logger.info(f"Collected {len(filtered)} items ({skipped} filtered)")

    log_run_stage(
        state["run_id"], "collect", "ok",
        item_count=len(filtered),
        detail=f"{len(t1)} tier1, {len(t2)} tier2, {skipped} filtered",
    )
    return {"raw_items": filtered}


def _passes_quality_check(item) -> bool:
    """Tier-aware quality gate: official sources get a lower bar."""
    from agent.normalisation.schemas import SourceTier
    content = item.raw_content or ""
    clean_chars = sum(1 for c in content if c.isascii() and c.isprintable())
    ratio = clean_chars / max(len(content), 1)

    if item.source_tier == SourceTier.TIER1:
        return len(content) >= 80 and ratio >= 0.4
    return len(content) >= 200 and ratio >= 0.6


def node_normalise(state: PipelineState) -> dict:
    logger.info("=== NORMALISE ===")
    errors = []
    try:
        readable = []
        for item in state["raw_items"]:
            if not _passes_quality_check(item):
                logger.warning(f"  SKIPPED (low quality): {item.title[:60]}")
                continue
            readable.append(item)
        logger.info(f"  {len(readable)}/{len(state['raw_items'])} passed quality check")
        new_items = normalise_and_store(readable)
        logger.info(f"  {len(new_items)} new items after dedup")

        log_run_stage(
            state["run_id"], "normalise", "ok",
            item_count=len(new_items),
            detail=f"{len(readable)} passed quality, {len(new_items)} new after dedup",
        )
        return {"new_items": new_items, "errors": errors}
    except Exception as e:
        logger.error(f"Normalisation failed: {e}")
        log_run_stage(state["run_id"], "normalise", "error", detail=str(e))
        return {"new_items": [], "errors": [f"normalise: {e}"]}


def node_score(state: PipelineState) -> dict:
    logger.info("=== SCORE ===")
    scored = []
    errors = list(state.get("errors", []))
    run_id = state["run_id"]

    for i, item in enumerate(state["new_items"]):
        try:
            result = score_item(item, run_id)
            if result:
                scored.append(result)
                save_scored_item(result, run_id)
                logger.info(f"  [{i+1}/{len(state['new_items'])}] scored: {item.title[:50]}")
            else:
                errors.append(f"score returned None: {item.title}")
                logger.warning(f"  [{i+1}/{len(state['new_items'])}] failed: {item.title[:50]}")
        except Exception as e:
            logger.error(f"Scoring error on '{item.title}': {e}")
            errors.append(f"score error: {item.title}: {e}")

        if i < len(state["new_items"]) - 1:
            time.sleep(4)

    logger.info(f"Scored {len(scored)}/{len(state['new_items'])} items")

    log_run_stage(
        run_id, "score", "ok",
        item_count=len(scored),
        detail=f"{len(scored)}/{len(state['new_items'])} scored, {len(errors)} errors",
    )
    return {"scored_items": scored, "errors": errors}


def node_synthesise(state: PipelineState) -> dict:
    logger.info("=== SYNTHESISE ===")

    MIN_RELEVANCE = 0.3
    quality_items = [
        i for i in state["scored_items"]
        if i.relevance_score >= MIN_RELEVANCE
    ]
    logger.info(
        f"  {len(quality_items)}/{len(state['scored_items'])} items "
        f"above relevance threshold ({MIN_RELEVANCE})"
    )

    if not quality_items:
        return {
            "digest_draft": (
                f"No new high-signal items today "
                f"(threshold: {MIN_RELEVANCE}, "
                f"total scored: {len(state['scored_items'])})."
            )
        }

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

    lines += [
        "---",
        f"_Run ID: {state['run_id']} | "
        f"Scored: {len(state['scored_items'])} | "
        f"Published: {len(top)} | "
        f"Filtered: {len(state['scored_items']) - len(quality_items)}_"
    ]

    digest = "\n".join(lines)
    logger.info(f"  Digest built — {len(digest)} chars")
    return {"digest_draft": digest}   # return only what changed