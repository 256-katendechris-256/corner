# agent/pipeline/runner.py
import uuid
import logging
from langgraph.graph import StateGraph, END
from agent.pipeline.state import PipelineState
from agent.pipeline.nodes import (
    node_collect, node_normalise, node_score, node_synthesise
)

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)


def build_pipeline():
    graph = StateGraph(PipelineState)

    graph.add_node("collect",    node_collect)
    graph.add_node("normalise",  node_normalise)
    graph.add_node("score",      node_score)
    graph.add_node("synthesise", node_synthesise)

    graph.set_entry_point("collect")
    graph.add_edge("collect",    "normalise")
    graph.add_edge("normalise",  "score")
    graph.add_edge("score",      "synthesise")
    graph.add_edge("synthesise", END)

    return graph.compile()


def run_pipeline() -> PipelineState:
    pipeline = build_pipeline()

    initial_state: PipelineState = {
        "run_id":       str(uuid.uuid4()),
        "raw_items":    [],
        "new_items":    [],
        "scored_items": [],
        "errors":       [],
        "digest_draft": None,
    }

    logger.info(f"Starting pipeline run {initial_state['run_id']}")
    final_state = pipeline.invoke(initial_state)
    logger.info(f"Pipeline complete — errors: {final_state['errors']}")
    return final_state


if __name__ == "__main__":
    result = run_pipeline()
    print("\n" + "="*60)
    print(result["digest_draft"])
    print("="*60)
    if result["errors"]:
        print(f"\nErrors ({len(result['errors'])}):")
        for e in result["errors"]:
            print(f"  - {e}")