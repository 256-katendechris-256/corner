# agent/observability/tracer.py
from langfuse import Langfuse
from agent.config import settings
import os

# Initialize once
langfuse = Langfuse(
    public_key=os.getenv('LANGFUSE_PUBLIC_KEY', ''),
    secret_key=os.getenv('LANGFUSE_SECRET_KEY', ''),
    host=os.getenv('LANGFUSE_HOST', 'https://cloud.langfuse.com'),
)

def trace_score(run_id: str, item_title: str, prompt: str, response: str, scores: dict) -> str:
    """
    Record a single scoring LLM call in Langfuse.
    Returns the trace ID for storage in scored_items.trace_id.
    """
    trace = langfuse.trace(
        name='score-item',
        input={'item_title': item_title},
        output=scores,
        metadata={'run_id': run_id},
    )
    trace.generation(
        name='gpt-scoring',
        input=prompt,
        output=response,
        model='gpt-4o-mini',
    )
    langfuse.flush()
    return trace.id