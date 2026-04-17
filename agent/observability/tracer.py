# agent/observability/tracer.py
import logging
import uuid
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache
def get_langfuse():
    from agent.config import settings
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("Langfuse keys not set — tracing disabled")
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as e:
        logger.warning(f"Langfuse init failed — tracing disabled: {e}")
        return None


def trace_score(
    run_id: str,
    item_title: str,
    system_prompt: str,
    user_message: str,
    raw_response: str,
    scores: dict,
    model: str = "llama-3.3-70b-versatile",
) -> str | None:
    """Trace a single scoring LLM call to Langfuse (v4 API)."""
    lf = get_langfuse()
    if lf is None:
        return str(uuid.uuid4())

    try:
        trace_id = lf.create_trace_id()

        with lf.start_as_current_observation(
            trace_context={"trace_id": trace_id},
            name="score-item",
            as_type="span",
            input={"title": item_title},
            metadata={"run_id": run_id},
        ) as span:
            span.set_trace_io(
                input={"title": item_title},
                output=scores,
            )

            gen = span.start_observation(
                name="groq-scoring",
                as_type="generation",
                model=model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_message},
                ],
                output=raw_response,
            )
            gen.end()

            for score_name, score_value in scores.items():
                if isinstance(score_value, (int, float)):
                    span.score_trace(name=score_name, value=float(score_value))

        return trace_id
    except Exception as e:
        logger.warning(f"Trace failed (non-fatal): {e}")
        return str(uuid.uuid4())


def trace_pipeline_run(
    run_id: str,
    item_count: int,
    scored_count: int,
    published_count: int,
    errors: list[str],
) -> None:
    """Trace the overall pipeline run to Langfuse (v4 API)."""
    lf = get_langfuse()
    if lf is None:
        return
    try:
        trace_id = lf.create_trace_id()

        with lf.start_as_current_observation(
            trace_context={"trace_id": trace_id},
            name="pipeline-run",
            as_type="span",
            input={"run_id": run_id, "items_collected": item_count},
            metadata={"errors": errors},
        ) as span:
            span.set_trace_io(
                input={"run_id": run_id, "items_collected": item_count},
                output={
                    "scored":    scored_count,
                    "published": published_count,
                    "errors":    len(errors),
                },
            )
    except Exception as e:
        logger.warning(f"Pipeline trace failed (non-fatal): {e}")