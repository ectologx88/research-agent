"""Classification result models for scored stories."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    BREAKING_NEWS = "breaking_news"
    RESEARCH = "research"
    THOUGHT_LEADERSHIP = "thought_leadership"
    INDUSTRY = "industry"
    WORLD_NEWS = "world_news"


class Actionability(str, Enum):
    CITATION_WORTHY = "citation_worthy"
    THOUGHT_PROVOKING = "thought_provoking"
    TIME_SENSITIVE = "time_sensitive"
    EVERGREEN = "evergreen"


class TaxonomyTag(str, Enum):
    AI_RESEARCH = "#ai-research"
    AI_POLICY = "#ai-policy"
    CONSCIOUSNESS = "#consciousness"
    RDD_FRAMEWORK = "#rdd-framework"
    CLIENT_WORK = "#client-work"
    NEURODIVERGENT_TECH = "#neurodivergent-tech"
    INDUSTRY_NEWS = "#industry-news"
    WORLD_NEWS = "#world-news"


class PriorityFlag(str, Enum):
    BREAKING = "⚡"
    ACTIONABLE = "🎯"
    CONCEPTUAL = "🧠"
    CONNECTIVE = "🔗"
    DATA_DRIVEN = "📊"
    RISK = "🚨"


class RelevanceScores(BaseModel):
    ai_ml: int = Field(ge=1, le=10)
    neuroscience: int = Field(ge=1, le=10)
    theory: int = Field(ge=1, le=10)
    content_craft: int = Field(ge=1, le=10)
    overall: int = Field(ge=1, le=10)
    importance: int = Field(ge=1, le=10)


class Classification(BaseModel):
    story_hash: str
    scores: RelevanceScores
    content_type: ContentType
    actionability: List[Actionability]
    taxonomy_tags: List[TaxonomyTag] = Field(default_factory=list)
    priority_flag: Optional[PriorityFlag] = None
    concepts: List[str] = Field(min_length=1, max_length=7)
    why_matters: str
    summary: str
    classified_at: datetime
    model_version: str
