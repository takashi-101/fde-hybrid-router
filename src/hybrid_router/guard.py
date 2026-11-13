"""Trust-boundary guards: sensitivity classification, PII masking, and prompt-injection detection."""

from __future__ import annotations

import re
from typing import List, Tuple

from .models import DataClassification, RouteDecision, RouteTarget


class InjectionGuard:
    """Detects prompt-injection attempts before any text reaches an LLM."""

    _PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
        ("ignore_instructions", re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions", re.I)),
        ("system_prompt_leak", re.compile(r"(?:reveal|show|print)\s+(?:the\s+)?system\s+prompt", re.I)),
        ("jp_override", re.compile(r"(?:これまでの|前の)(?:指示|命令|ルール)を(?:すべて)?(?:無視|忘れ)")),
        ("jp_role_hijack", re.compile(r"(?:システムプロンプト|内部設定|機密情報)を(?:出力|表示|教え)")),
    )

    def inspect(self, text: str) -> Tuple[bool, List[str]]:
        matched = [name for name, pat in self._PATTERNS if pat.search(text)]
        return (len(matched) > 0), matched


class SensitivityClassifier:
    """Classifies data sensitivity and masks PII before local LLM processing."""

    _PII_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
        ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
        ("ID_NUM", re.compile(r"(?<!\d)(?:\d{4}-\d{4}-\d{4}|\d{12})(?!\d)")),
        ("PHONE", re.compile(r"(?<!\d)(?:0\d{1,4}-\d{1,4}-\d{3,4}|0[789]0\d{8})(?!\d)")),
        ("PERSON", re.compile(r"((?:氏名|名前|申請者|担当)\s*[:：]\s*)([^\n、。,\/／(（\[]+?)(?=\s*(?:[\n、。,\/／(（\[]|様|さん|$))")),
        ("AMOUNT", re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)\s?(?:万円|億円|円)")),
    )

    _INTERNAL_KEYWORDS: Tuple[str, ...] = ("申請", "個人番号", "マイナンバー", "口座", "医療", "生活保護", "非公開")

    def classify_and_mask(self, text: str) -> Tuple[DataClassification, str, List[str]]:
        if not isinstance(text, str):
            raise TypeError("Fail-closed: payload must be a string.")

        working = text
        found_types: List[str] = []

        for label, pat in self._PII_PATTERNS:
            if label == "PERSON":
                if pat.search(working):
                    found_types.append(label)
                    working = pat.sub(r"\1[PERSON_MASKED]", working)
            else:
                if pat.search(working):
                    found_types.append(label)
                    working = pat.sub(f"[{label}_MASKED]", working)

        has_internal_kw = any(kw in text for kw in self._INTERNAL_KEYWORDS)
        if found_types or has_internal_kw:
            return DataClassification.INTERNAL_PII, working, sorted(set(found_types))
        return DataClassification.PUBLIC, working, []


def decide_route(
    text: str,
    injection_guard: InjectionGuard,
    classifier: SensitivityClassifier,
) -> Tuple[RouteDecision, str]:
    """Fail-closed routing: injection -> block; PII/internal -> local masked; public -> cloud allowed."""
    injected, inj_rules = injection_guard.inspect(text)
    classification, masked_text, pii_types = classifier.classify_and_mask(text)

    if injected:
        return (
            RouteDecision(
                classification=classification,
                target=RouteTarget.BLOCKED_HUMAN_ONLY,
                injection_detected=True,
                matched_rules=inj_rules,
            ),
            masked_text,
        )

    if classification == DataClassification.INTERNAL_PII:
        return (
            RouteDecision(
                classification=classification,
                target=RouteTarget.LOCAL_LLM_MASKED,
                injection_detected=False,
                matched_rules=pii_types,
            ),
            masked_text,
        )

    return (
        RouteDecision(
            classification=DataClassification.PUBLIC,
            target=RouteTarget.CLOUD_LLM,
            injection_detected=False,
            matched_rules=[],
        ),
        masked_text,
    )
