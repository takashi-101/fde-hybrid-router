"""Hybrid FDE Router combining trust-boundary routing, pluggable LLM backends, and HITL."""

from __future__ import annotations

from typing import List, Optional

from .backends import (
    ModelBackend,
    ModelPrediction,
    default_local_backend,
    sample_cloud_backend,
    sample_local_backend,
)
from .db import InquiryRepository
from .guard import InjectionGuard, SensitivityClassifier, decide_route
from .models import InquiryRecord, RouteTarget, ReviewStatus, RoutingOutcome

__all__ = [
    "HybridFDERouter",
    "ModelBackend",
    "ModelPrediction",
    "sample_cloud_backend",
    "sample_local_backend",
]


class HybridFDERouter:
    """Routes DB inquiries through security boundaries and Human-in-the-Loop gates.

    cloud_backend: defaults to the fixed-response sample (no external call).
    local_backend: defaults to Ollama, falling back to the local sample if Ollama is unreachable.
    """

    def __init__(
        self,
        repo: InquiryRepository,
        confidence_threshold: float = 0.80,
        cloud_backend: ModelBackend = sample_cloud_backend,
        local_backend: Optional[ModelBackend] = None,
    ) -> None:
        self.repo = repo
        self.confidence_threshold = confidence_threshold
        self.cloud_backend = cloud_backend
        self.local_backend = local_backend if local_backend is not None else default_local_backend()
        self.injection_guard = InjectionGuard()
        self.classifier = SensitivityClassifier()

    def process_record(self, record: InquiryRecord) -> RoutingOutcome:
        decision, masked_payload = decide_route(
            record.body, self.injection_guard, self.classifier
        )

        # 1. Fail-closed security escalation on prompt injection (no LLM is called)
        if decision.target == RouteTarget.BLOCKED_HUMAN_ONLY:
            outcome = RoutingOutcome(
                ticket_id=record.ticket_id,
                decision=decision,
                review_status=ReviewStatus.ESCALATED_SECURITY,
                confidence=0.0,
                escalation_reason=f"Prompt injection detected: {', '.join(decision.matched_rules)}",
                sanitized_payload="[BLOCKED_BY_INJECTION_GUARD]",
                draft_answer="",
                answered_by="none",
            )
            self.repo.save_outcome(outcome)
            return outcome

        # 2. Route by trust boundary (never send INTERNAL_PII to cloud_backend)
        if decision.target == RouteTarget.LOCAL_LLM_MASKED:
            pred = self.local_backend(record.category_hint, masked_payload)
        else:
            pred = self.cloud_backend(record.category_hint, masked_payload)

        # 3. Human-in-the-Loop (Abstain / Escalate on low confidence or high risk)
        if pred.high_risk_flag or pred.confidence < self.confidence_threshold:
            review_status = ReviewStatus.NEEDS_HUMAN_REVIEW
            reason = (
                f"High-risk case flagged by {pred.answered_by}"
                if pred.high_risk_flag
                else f"Low confidence ({pred.confidence:.2f} < {self.confidence_threshold:.2f})"
            )
        else:
            review_status = ReviewStatus.AUTO_DRAFTED
            reason = ""

        outcome = RoutingOutcome(
            ticket_id=record.ticket_id,
            decision=decision,
            review_status=review_status,
            confidence=pred.confidence,
            escalation_reason=reason,
            sanitized_payload=masked_payload,
            draft_answer=pred.draft_answer,
            answered_by=pred.answered_by,
            fallback_reason=pred.fallback_reason,
        )
        self.repo.save_outcome(outcome)
        return outcome

    def process_pending(self) -> List[RoutingOutcome]:
        return [self.process_record(rec) for rec in self.repo.fetch_pending()]
