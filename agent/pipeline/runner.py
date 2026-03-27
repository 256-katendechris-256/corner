# agent/pipeline/runner.py
from langgraph.graph import StateGraph, END
from agent.pipeline.state import PipelineState
from agent.pipeline.nodes import (
    node_collect,
    node_normalise,
    node_score,
    node_synthesise
)
import uuid, logging

logger = logging.getLogger(__name__)

def build_pipeline():
    graph = StateGraph(PipelineState)

    # Register nodes
    graph.add_node('collect', node_collect)
    graph.add_node('normalise', node_normalise)
    graph.add_node('score', node_score)
    graph.add_node('synthesise', node_synthesise)

    # Define edges (the flow)
    graph.set_entry_point('collect')
    graph.add_edge('collect', 'normalise')
    graph.add_edge('normalise', 'score')
    graph.add_edge('score', 'synthesise')
    graph.add_edge('synthesise', END)

    return graph.compile()

def run_pipeline():
    """Entry point called by the scheduler."""
    pipeline = build_pipeline()

    initial_state: PipelineState = {
        'run_id': str(uuid.uuid4()),
        'raw_items': [],
        'new_items': [],
        'scored_items': [],
        'errors': [],
        'digest_draft': None,
        'approved': False,
    }

    final_state = pipeline.invoke(initial_state)
    logger.info(f"Pipeline complete. Errors: {final_state['errors']}")
    return final_state

if __name__ == '__main__':
    logging.basicConfig(level='INFO')
    result = run_pipeline()
    print(result['digest_draft'])