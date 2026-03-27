# agent/ingestion/youtube.py
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from agent.normalisation.schemas import SourceItem, SourceTier
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# Trusted channels to monitor
MONITORED_CHANNELS = [
    'Andrej Karpathy',
    'AI Explained',
    'Yannic Kilcher',
]

def get_transcript(video_id: str) -> list[dict] | None:
    """
    Fetch captions for a YouTube video.
    Compatible with youtube-transcript-api >= 0.6
    """
    try:
        # New API: instantiate, then call fetch()
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        # Returns FetchedTranscript object — convert to list of dicts
        return [{"text": s.text, "start": s.start, "duration": s.duration}
                for s in transcript]
    except Exception as e:
        logger.warning(f"Transcript error for {video_id}: {e}")
        return None
    
def transcript_to_text(segments: list[dict]) -> str:
    """Concatenate transcript segments into plain text."""
    return ' '.join(s['text'] for s in segments)

def make_timestamp_url(video_id: str, start_seconds: float) -> str:
    """Produce a YouTube URL that opens at a specific timestamp."""
    t = int(start_seconds)
    return f'https://www.youtube.com/watch?v={video_id}&t={t}s'

def ingest_video(video_id: str, channel_name: str, title: str) -> SourceItem | None:
    """
    Fetch transcript for a single video and return a SourceItem.
    Returns None if no transcript is available.
    """
    segments = get_transcript(video_id)
    if segments is None:
        return None

    full_text = transcript_to_text(segments)
    url = f'https://www.youtube.com/watch?v={video_id}'

    return SourceItem(
        id=SourceItem.make_id(channel_name, url),
        title=title,
        source_name=channel_name,
        source_tier=SourceTier.TIER3,
        published_at=datetime.now(timezone.utc),
        canonical_url=url,
        raw_content=full_text[:12000],  # cap for context window
    )