from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib

class SourceTier(str, Enum):
    TIER1 = 'tier1'  # official vendor changelogs
    TIER2 = 'tier2'  #Newsletters, analysts
    TIER3 = 'tier3' #Youtube, podcasts

class ImpactTag(str, Enum):
    DELIVERY ='delivery'
    COMMERCIAL ='commercial'
    TOOLING = 'tooling'
    GOVERNANCE = 'governance'
    CLIENT_OPPORTUNITY = 'client_oppotunity'
    RISK = 'risk'

class SourceItem(BaseModel):
    id: str  #deterministic hash
    title: str 
    source_name: str
    source_tier: SourceTier
    published_at: datetime
    canonical_url: str
    raw_content: str # full text, stored for audit 
    key_excerpt: Optional[str] = None

    @classmethod
    def make_id(cls, source_name: str, url:str) -> str:
        raw = f'{source_name}: {url}'
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    """
        The make_id() method creates a deterministic ID from source name + URL. This means the same article
        will always get the same ID, so you can safely use it as a database primary key without risk of duplicates on
        re-ingestion
    """
    
class ScoredItem(BaseModel):
    source_item: SourceItem
    relevance_score: float
    novelty_score: float
    urgency_score: float
    confidence_score: float
    what_changed: str
    why_it_matters: str
    recommended_action: Optional[str] =None
    impact_tags: list[ImpactTag] = []
    approved: bool =False
    approved_summary: Optional[str]=None
    trace_id: Optional[str]=None