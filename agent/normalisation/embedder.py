# # agent/normalisation/embedder.py
# from openai import OpenAI
# from agent.config import settings
# import logging

# logger = logging.getLogger(__name__)

# client = OpenAI(api_key=settings.openai_api_key)

# def embed_text(text: str, max_chars: int = 8000) -> list[float]:
#     """
#     Call OpenAI text-embedding-3-small to get a 1536-dim vector.
#     Truncates text to max_chars before embedding.
#     """
#     truncated = text[:max_chars].replace('\n', ' ')
#     response = client.embeddings.create(
#         model='text-embedding-3-small',
#         input=truncated,
#     )
#     return response.data[0].embedding
# agent/normalisation/embedder.py
# Uses sentence-transformers locally — free, no API key needed
# Produces 384-dim vectors (vs OpenAI's 1536) — update your DB schema below


from sentence_transformers import SentenceTransformer
import logging

logger = logging.getLogger(__name__)

# Downloaded once on first run, cached locally after that
_model = None

def get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model (first run — downloads ~90MB)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def embed_text(text: str, max_chars: int = 8000) -> list[float]:
    """
    Embed text locally using sentence-transformers.
    Returns a 384-dimensional vector. Free, no API calls.
    """
    truncated = text[:max_chars].replace("\n", " ")
    model = get_model()
    embedding = model.encode(truncated, normalize_embeddings=True)
    return embedding.tolist()