"""FDE Hybrid Router: DB-backed AI routing with trust boundaries, injection guard, and HITL."""

from .backends import (
    EndpointNotAllowed,
    FallbackBackend,
    LLMUnavailable,
    ModelPrediction,
    OllamaLocalBackend,
    sample_cloud_backend,
    sample_local_backend,
)
from .db import InquiryRepository
from .guard import InjectionGuard, SensitivityClassifier
from .models import InquiryRecord, RouteDecision, RoutingOutcome
from .router import HybridFDERouter

__all__ = [
    "EndpointNotAllowed",
    "FallbackBackend",
    "HybridFDERouter",
    "InjectionGuard",
    "InquiryRecord",
    "InquiryRepository",
    "LLMUnavailable",
    "ModelPrediction",
    "OllamaLocalBackend",
    "RouteDecision",
    "RoutingOutcome",
    "SensitivityClassifier",
    "sample_cloud_backend",
    "sample_local_backend",
]
