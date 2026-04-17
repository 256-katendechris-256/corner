import psycopg2
import logging
from agent.config import settings
from agent.normalisation.schemas import SourceItem
from agent.normalisation.embedder import embed_text

logger = logging.getLogger(__name__)


def get_conn():
    return psycopg2.connect(settings.postgres_url)


def is_duplicate(
    embedding: list[float],
    threshold: float | None = None,
) -> bool:
    """
    Check if a semantically similar item already exists in the DB.
    Uses pgvector cosine similarity: 1 = identical, 0 = unrelated.
    """
    if threshold is None:
        threshold = settings.similarity_threshold

    vec_str = '[' + ','.join(map(str, embedding)) + ']'

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM source_items
            WHERE 1 - (embedding <=> %s::vector) > %s
            LIMIT 1
        """, (vec_str, threshold))

        result = cur.fetchone()

    conn.close()
    return result is not None


def save_item(item: SourceItem, embedding: list[float]) -> None:
    """Upsert a SourceItem and its embedding into Postgres."""
    vec_str = '[' + ','.join(map(str, embedding)) + ']'

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO source_items (
                id, title, source_name, source_tier,
                published_at, canonical_url, raw_content, embedding
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)
            ON CONFLICT (id) DO NOTHING
        """, (
            item.id,
            item.title,
            item.source_name,
            item.source_tier.value,
            item.published_at,
            item.canonical_url,
            item.raw_content,
            vec_str
        ))

    conn.commit()
    conn.close()


def normalise_and_store(items: list[SourceItem]) -> list[SourceItem]:
    """
    For each item: embed → dedup check → save.
    Returns only new (non-duplicate) items.
    """
    new_items = []

    for item in items:
        embedding = embed_text(item.raw_content or item.title)

        if is_duplicate(embedding):
            logger.info(f'DUPLICATE — skipping: {item.title[:60]}')
            continue

        save_item(item, embedding)
        logger.info(f'SAVED: {item.title[:60]}')

        new_items.append(item)

    return new_items


def retrieve_similar(embedding: list[float], top_k: int = 5) -> list[dict]:
    """
    RAG retrieval: fetch most similar past items.
    """
    vec_str = '[' + ','.join(map(str, embedding)) + ']'

    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT title, source_name, raw_content, canonical_url,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM source_items
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (vec_str, vec_str, top_k))

        rows = cur.fetchall()

    conn.close()

    return [
        {
            "title": r[0],
            "source": r[1],
            "excerpt": (r[2] or "")[:200],
            "url": r[3],
            "similarity": round(r[4], 3)
        }
        for r in rows
    ]


def save_scored_item(scored_item, run_id: str) -> None:
    """Persist a ScoredItem to the scored_items table."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scored_items (
                    id, source_item_id, run_id,
                    relevance, novelty, urgency, confidence,
                    what_changed, why_it_matters, recommended_action,
                    impact_tags, trace_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                scored_item.source_item.id + "-" + run_id[:8],
                scored_item.source_item.id,
                run_id,
                scored_item.relevance_score,
                scored_item.novelty_score,
                scored_item.urgency_score,
                scored_item.confidence_score,
                scored_item.what_changed,
                scored_item.why_it_matters,
                scored_item.recommended_action,
                [t.value for t in scored_item.impact_tags],
                scored_item.trace_id,
            ))
        conn.commit()
    finally:
        conn.close()


def log_run_stage(run_id: str, stage: str, status: str,
                  item_count: int = 0, detail: str = "") -> None:
    """Write a row to run_logs for pipeline observability."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO run_logs (run_id, stage, status, item_count, detail)
                VALUES (%s, %s, %s, %s, %s)
            """, (run_id, stage, status, item_count, detail))
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to log run stage: {e}")
    finally:
        conn.close()


def save_published_digest(run_id: str, digest_text: str,
                          item_count: int = 0) -> None:
    """Persist a published digest so it survives draft file deletion."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO published_digests (run_id, digest_text, item_count)
                VALUES (%s, %s, %s)
            """, (run_id, digest_text, item_count))
        conn.commit()
    finally:
        conn.close()