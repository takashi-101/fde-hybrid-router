"""Domain models for hybrid cloud/local LLM routing and Human-in-the-Loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class DataClassification(str, Enum):
    PUBLIC = "PUBLIC"          # Safe for cloud LLM if needed
    INTERNAL_PII = "INTERNAL_PII"  # Must stay in closed/local LLM with PII masking


class RouteTarget(str, Enum):
    CLOUD_LLM = "CLOUD_LLM"
    LOCAL_LLM_MASKED = "LOCAL_LLM_MASKED"
    BLOCKED_HUMAN_ONLY = "BLOCKED_HUMAN_ONLY"


class ReviewStatus(str, Enum):
    AUTO_DRAFTED = "AUTO_DRAFTED"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    ESCALATED_SECURITY = "ESCALATED_SECURITY"


@dataclass(frozen=True)
class InquiryRecord:
    ticket_id: str
    category_hint: str
    body: str
    source_channel: str = "web_form"


@dataclass(frozen=True)
class RouteDecision:
    classification: DataClassification
    target: RouteTarget
    injection_detected: bool
    matched_rules: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoutingOutcome:
    ticket_id: str
    decision: RouteDecision
    review_status: ReviewStatus
    confidence: float
    escalation_reason: str
    sanitized_payload: str
    draft_answer: str
