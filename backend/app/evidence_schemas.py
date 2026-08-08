"""Claim-level provenance contracts for the WishForge first version.

The concept analysis pipeline already returns paper metadata and abstract-level
evidence cards.  This module adds the missing audit layer: every important
statement in an explanation can point back to one or more evidence cards, and
the UI can distinguish a supported statement from an unverified hypothesis.

The models intentionally do not copy the source text into a second document.
They reference the existing ``EvidenceCard`` IDs so one source of truth is
kept for excerpts and source locations.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


ClaimType = Literal[
    "definition",
    "mechanism",
    "evolution",
    "limitation",
    "result",
    "related_concept",
    "research_gap",
    "hypothesis",
]
ClaimStatus = Literal[
    "supported",
    "partially_supported",
    "contradicted",
    "unverified",
    "hypothesis",
]
ClaimRelation = Literal["supports", "contradicts", "qualifies", "background"]


class ClaimEvidenceLink(BaseModel):
    """A typed edge between one claim and one existing evidence card."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    evidence_id: str = Field(min_length=1, max_length=200)
    relation: ClaimRelation = "supports"
    note: str = Field(default="", max_length=1000)


class ClaimRecord(BaseModel):
    """One auditable statement generated during concept analysis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=lambda: f"claim-{uuid4()}")
    text: str = Field(min_length=1, max_length=5000)
    claim_type: ClaimType = "definition"
    status: ClaimStatus = "unverified"
    confidence: Literal["high", "medium", "low"] = "low"
    scope: str = Field(default="", max_length=2000)
    evidence_links: list[ClaimEvidenceLink] = Field(default_factory=list, max_length=50)
    next_action: str = Field(default="人工核对原文和适用边界", max_length=1000)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EvidenceLedger(BaseModel):
    """Claim-to-evidence view for one completed analysis."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    analysis_id: str
    claims: list[ClaimRecord] = Field(default_factory=list, max_length=200)
    evidence_count: int = Field(default=0, ge=0)
    linked_claim_count: int = Field(default=0, ge=0)
    # ``coverage`` is retained as a compatibility alias for the original
    # first-version response.  The two explicit rates prevent a linked
    # abstract snippet from being mistaken for manually verified evidence.
    coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    link_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    verified_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    contradicted_claim_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list, max_length=30)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
