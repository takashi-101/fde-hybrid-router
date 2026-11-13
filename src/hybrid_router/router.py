"""Hybrid FDE Router combining trust-boundary routing, LLM adapter abstraction, and HITL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple

from .db import InquiryRepository
from .guard import InjectionGuard, SensitivityClassifier, decide_route
from .models import InquiryRecord, RouteTarget, ReviewStatus, RoutingOutcome


@dataclass(frozen=True)
class ModelPrediction:
    draft_answer: str
    confidence: float
    high_risk_flag: bool = False


ModelBackend = Callable[[str, str], ModelPrediction]


def default_cloud_backend(category_hint: str, sanitized_text: str) -> ModelPrediction:
    """Stub for cloud LLM (called ONLY for PUBLIC data with no PII)."""
    if "一般公開" in sanitized_text or "営業時間" in sanitized_text or "アクセス" in sanitized_text:
        return ModelPrediction(
            draft_answer=f"【公開案内ドラフト】{category_hint}に関する一般的なご案内です。",
            confidence=0.92,
            high_risk_flag=False,
        )
    return ModelPrediction(
        draft_answer="判断材料が不足しているため担当者確認が必要です。",
        confidence=0.55,
        high_risk_flag=False,
    )


def default_local_backend(category_hint: str, masked_text: str) -> ModelPrediction:
    """Stub for closed/local LLM (receives ONLY masked internal text)."""
    if "支給要件" in masked_text or "標準手順" in masked_text:
        return ModelPrediction(
            draft_answer=f"【閉域ローカルLLM回答案】{category_hint}の標準手順に基づく一次回答候補です。",
            confidence=0.86,
            high_risk_flag=False,
        )
    if "不服" in masked_text or "訴訟" in masked_text or "例外" in masked_text:
        return ModelPrediction(
            draft_answer="",
            confidence=0.42,
            high_risk_flag=True,
        )
    return ModelPrediction(
        draft_answer="確認が必要な項目が含まれるため、一次回答を保留します。",
        confidence=0.68,
        high_risk_flag=False,
    )


class HybridFDERouter:
    """Routes DB inquiries through security boundaries and Human-in-the-Loop gates."""

    def __init__(
        self,
        repo: InquiryRepository,
        confidence_threshold: float = 0.80,
        cloud_backend: ModelBackend = default_cloud_backend,
        local_backend: ModelBackend = default_local_backend,
    ) -> None:
        self.repo = repo
        self.confidence_threshold = confidence_threshold
        self.cloud_backend = cloud_backend
        self.local_backend = local_backend
        self.injection_guard = InjectionGuard()
        self.classifier = SensitivityClassifier()

    def process_record(self, record: InquiryRecord) -> RoutingOutcome:
        decision, masked_payload = decide_route(
            record.body, self.injection_guard, self.classifier
        )

        # 1. Fail-closed security escalation on prompt injection
        if decision.target == RouteTarget.BLOCKED_HUMAN_ONLY:
            outcome = RoutingOutcome(
                ticket_id=record.ticket_id,
                decision=decision,
                review_status=ReviewStatus.ESCALATED_SECURITY,
                confidence=0.0,
                escalation_reason=f"Prompt injection detected: {', '.join(decision.matched_rules)}",
                sanitized_payload="[BLOCKED_BY_INJECTION_GUARD]",
                draft_answer="",
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
            reason = (
                "High-risk case flagged by model"
                if pred.high_risk_flag
                else f"Low confidence ({pred.confidence:.2f} < {self.confidence_threshold:.2f})"
            )
            outcome = RoutingOutcome(
                ticket_id=record.ticket_id,
                decision=decision,
                review_status=ReviewStatus.NEEDS_HUMAN_REVIEW,
                confidence=pred.confidence,
                escalation_reason=reason,
                sanitized_payload=masked_payload,
                draft_answer=pred.draft_answer,
            )
        else:
            outcome = RoutingOutcome(
                ticket_id=record.ticket_id,
                decision=decision,
                review_status=ReviewStatus.AUTO_DRAFTED,
                confidence=pred.confidence,
                escalation_reason="",
                sanitized_payload=masked_payload,
                draft_answer=pred.draft_answer,
            )

        self.repo.save_outcome(outcome)
        return outcome

    def process_pending(self) -> List[RoutingOutcome]:
        return [self.process_record(rec) for rec in self.repo.fetch_pending()]
