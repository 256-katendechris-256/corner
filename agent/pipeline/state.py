# agent/pipeline/state.py
from typing import TypedDict, Optional
from agent.normalisation.schemas import SourceItem, ScoredItem

class PipelineState(TypedDict):
    run_id: str
    raw_items: list[SourceItem]
    new_items: list[SourceItem]  # after dedup
    scored_items: list[ScoredItem]
    errors: list[str]
    digest_draft: Optional[str]
    approved: bool