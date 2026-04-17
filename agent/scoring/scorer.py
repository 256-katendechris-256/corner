# import json
# import logging
# import uuid

# from openai import OpenAI
# from agent.config import settings
# from agent.normalisation.schemas import SourceItem, ScoredItem, ImpactTag
# from agent.normalisation.embedder import embed_text
# from agent.normalisation.normaliser import retrieve_similar

# logger = logging.getLogger(__name__)
# client = OpenAI(api_key=settings.openai_api_key)


# SYSTEM_PROMPT = """
# You are an AI market intelligence analyst for Set Piece, a UK digital agency.

# Set Piece builds AI products for clients. You monitor AI industry developments and assess their business impact.

# Your job is to score a new development and explain why it matters.

# SCORING RUBRIC (all scores 0.0 to 1.0):
# - relevance
# - novelty
# - urgency
# - confidence

# IMPACT TAGS:
# delivery, commercial, tooling, governance, client_opportunity, risk

# Respond ONLY with valid JSON.

# {
#  "relevance": 0.0,
#  "novelty": 0.0,
#  "urgency": 0.0,
#  "confidence": 0.0,
#  "what_changed": "one sentence",
#  "why_it_matters": "2-3 sentences",
#  "recommended_action": "optional",
#  "impact_tags": ["tag1", "tag2"]
# }
# """


# def build_user_message(item: SourceItem, prior_context: list[dict]) -> str:
#     """Assemble item + RAG context."""
#     context_str = ""

#     if prior_context:
#         context_str = "SIMILAR PAST ITEMS:\n"
#         for c in prior_context[:3]:
#             context_str += f"- {c['title']} ({c['source']})\n"
#         context_str += "\n"

#     return (
#         f"{context_str}"
#         f"NEW ITEM:\n"
#         f"Source: {item.source_name} ({item.source_tier.value})\n"
#         f"Title: {item.title}\n"
#         f"URL: {item.canonical_url}\n\n"
#         f"Content:\n{(item.raw_content or '')[:6000]}"
#     )


# def score_item(item: SourceItem) -> ScoredItem | None:
#     """Score a single item using LLM."""
#     try:
#         # 🔹 Step 1: Embed + retrieve context
#         embedding = embed_text(item.raw_content or item.title)
#         prior = retrieve_similar(embedding, top_k=5)

#         # 🔹 Step 2: Build prompt
#         user_message = build_user_message(item, prior)

#         # 🔹 Step 3: Call OpenAI
#         response = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": SYSTEM_PROMPT},
#                 {"role": "user", "content": user_message},
#             ],
#             temperature=0.2,
#             max_tokens=800,
#             response_format={"type": "json_object"},
#         )

#         raw = response.choices[0].message.content
#         data = json.loads(raw)

#         # 🔹 Step 4: Convert to ScoredItem
#         return ScoredItem(
#             source_item=item,
#             relevance_score=float(data.get("relevance", 0)),
#             novelty_score=float(data.get("novelty", 0)),
#             urgency_score=float(data.get("urgency", 0)),
#             confidence_score=float(data.get("confidence", 0)),
#             what_changed=data.get("what_changed", ""),
#             why_it_matters=data.get("why_it_matters", ""),
#             recommended_action=data.get("recommended_action"),
#             impact_tags=[
#                 ImpactTag(t)
#                 for t in data.get("impact_tags", [])
#                 if t in ImpactTag._value2member_map_
#             ],
#             trace_id=str(uuid.uuid4()),
#         )

#     except Exception as e:
#         logger.error(f"Scoring failed for {item.title}: {e}")
#         return None

# agent/scoring/scorer.py
import json
import time
from groq import Groq
from agent.config import settings
from agent.normalisation.schemas import SourceItem, ScoredItem, ImpactTag
from agent.normalisation.embedder import embed_text
from agent.normalisation.normaliser import retrieve_similar
from agent.observability.tracer import trace_score
import logging

logger = logging.getLogger(__name__)
client = Groq(api_key=settings.groq_api_key)
#client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))

SYSTEM_PROMPT = """
You are an AI market intelligence analyst for Set Piece, a UK digital agency.
Set Piece builds AI products for clients. You monitor AI industry developments
and assess their business impact.

Score the development and explain why it matters.

SCORING RUBRIC (all scores 0.0 to 1.0):
  relevance   — how relevant to Set Piece's AI delivery work
  novelty     — how new or surprising (1.0 = never seen before)
  urgency     — how quickly Set Piece should act
  confidence  — how confident you are in the information

IMPACT TAGS (pick all that apply):
  delivery, commercial, tooling, governance, client_opportunity, risk

Respond ONLY with valid JSON matching this exact schema:
{
  "relevance": 0.0,
  "novelty": 0.0,
  "urgency": 0.0,
  "confidence": 0.0,
  "what_changed": "one sentence",
  "why_it_matters": "2-3 sentences for Set Piece specifically",
  "recommended_action": "optional next step or null",
  "impact_tags": ["tag1", "tag2"]
}
"""

def build_user_message(item: SourceItem, prior_context: list[dict]) -> str:
    context_str = ""
    if prior_context:
        context_str = "SIMILAR PAST ITEMS (for reference):\n"
        for c in prior_context[:3]:
            context_str += f"  - {c['title']} ({c['source']})\n"
        context_str += "\n"
    return (
        f"{context_str}"
        f"NEW ITEM TO SCORE:\n"
        f"Source: {item.source_name} ({item.source_tier.value})\n"
        f"Title: {item.title}\n"
        f"URL: {item.canonical_url}\n"
        f"Content:\n{(item.raw_content or '')[:4000]}"
    )

def score_item(
    item: SourceItem,
    pipeline_run_id: str,
    max_retries: int = 3,
) -> ScoredItem | None:
    embedding    = embed_text(item.raw_content or item.title)
    prior        = retrieve_similar(embedding, top_k=5)
    user_message = build_user_message(item, prior)

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                temperature=0.2,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            raw  = response.choices[0].message.content
            data = json.loads(raw)

            trace_id = trace_score(
                run_id=pipeline_run_id,
                item_title=item.title,
                system_prompt=SYSTEM_PROMPT,
                user_message=user_message,
                raw_response=raw,
                scores={k: data.get(k) for k in
                        ["relevance","novelty","urgency","confidence"]},
            )

            return ScoredItem(
                source_item=item,
                relevance_score=float(data.get("relevance", 0)),
                novelty_score=float(data.get("novelty", 0)),
                urgency_score=float(data.get("urgency", 0)),
                confidence_score=float(data.get("confidence", 0)),
                what_changed=data.get("what_changed", ""),
                why_it_matters=data.get("why_it_matters", ""),
                recommended_action=data.get("recommended_action"),
                impact_tags=[
                    ImpactTag(t) for t in data.get("impact_tags", [])
                    if t in ImpactTag._value2member_map_
                ],
                trace_id=trace_id,
            )

        except Exception as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                f"  Attempt {attempt+1}/{max_retries} failed for "
                f"'{item.title[:40]}': {e} — waiting {wait}s"
            )
            if attempt < max_retries - 1:
                time.sleep(wait)

    logger.error(f"All {max_retries} attempts failed for: {item.title}")
    return None