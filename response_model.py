from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResponseType(str, Enum):
    WEEKLY_ROUNDUP = "weekly roundup"
    CONTEXT = "context"
    NOTEPAD = "notepad"


JsonScalar = Union[str, int, float, bool, None]


class Note(BaseModel):
    """A single persistent note entry kept across processing rounds."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[str] = Field(None, description="Optional unique identifier for the note")
    created_at: datetime = Field(default_factory=datetime.now)
    title: Optional[str] = Field(None, description="Short title for quick scanning")
    content: str = Field(..., description="The textual content of the note")
    tags: List[str] = Field(default_factory=list, description="Optional tags to help grouping")
    importance: Optional[int] = Field(None, ge=0, le=10, description="Optional importance score 0-10")
    archived: bool = Field(False, description="If true the note is archived and should be deprioritized")
    
class WeeklyAnalysis(BaseModel):
    """Structured breakdown of the athlete's weekly performance."""
    executive_summary: str = Field(..., description="Overall status of the training block and goals")
    physiological_markers: str = Field(..., description="Insights on Aerobic Decoupling, Efficiency, and Adaptation")
    recovery_correlation: str = Field(..., description="Analysis of how HRV/Sleep responded to training load")
    actionable_adjustments: List[str] = Field(..., description="Bullet points for specific changes to next week's plan")

class OpenAIResponse(BaseModel):
    """Top-level schema for the assistant's structured response.

    - `response_type` indicates which kind of payload is primary.
    - `weekly_roundup` contains a structured analysis for the user.
    - `context` is a simple markdown string for broader athlete context.
    - `notepad` is a list of persistent notes the system should store.
    """

    weekly_roundup: WeeklyAnalysis = Field(None, description="Structured weekly analysis intended for the user")
    context: Optional[str] = Field(None, description="Markdown context for future processing rounds")
    notepad: List[Note] = Field(default_factory=list, description="Persistent notes for pattern discovery and history")
 