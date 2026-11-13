"""SQLite repository simulating enterprise/municipal DB integration and HITL review queue."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

from .models import InquiryRecord, RoutingOutcome


class InquiryRepository:
    """Manages inquiry records and Human-in-the-Loop review queue in SQLite."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit or roll back on exit, and always close it."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS inquiries (
                    ticket_id TEXT PRIMARY KEY,
                    category_hint TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source_channel TEXT NOT NULL,
                    processed INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS routing_results (
                    ticket_id TEXT PRIMARY KEY,
                    data_classification TEXT NOT NULL,
                    route_target TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    escalation_reason TEXT NOT NULL,
                    sanitized_payload TEXT NOT NULL,
                    draft_answer TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS human_review_queue (
                    ticket_id TEXT PRIMARY KEY,
                    review_status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    resolved INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def insert_inquiry(self, record: InquiryRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO inquiries (ticket_id, category_hint, body, source_channel, processed)
                VALUES (?, ?, ?, ?, 0)
                """,
                (record.ticket_id, record.category_hint, record.body, record.source_channel),
            )

    def fetch_pending(self) -> List[InquiryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticket_id, category_hint, body, source_channel FROM inquiries WHERE processed = 0 ORDER BY ticket_id"
            ).fetchall()
        return [
            InquiryRecord(
                ticket_id=r["ticket_id"],
                category_hint=r["category_hint"],
                body=r["body"],
                source_channel=r["source_channel"],
            )
            for r in rows
        ]

    def save_outcome(self, outcome: RoutingOutcome) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE inquiries SET processed = 1 WHERE ticket_id = ?",
                (outcome.ticket_id,),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO routing_results
                (ticket_id, data_classification, route_target, review_status, confidence, escalation_reason, sanitized_payload, draft_answer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.ticket_id,
                    outcome.decision.classification.value,
                    outcome.decision.target.value,
                    outcome.review_status.value,
                    outcome.confidence,
                    outcome.escalation_reason,
                    outcome.sanitized_payload,
                    outcome.draft_answer,
                ),
            )
            if outcome.review_status.value != "AUTO_DRAFTED":
                conn.execute(
                    """
                    INSERT OR REPLACE INTO human_review_queue (ticket_id, review_status, reason, confidence, resolved)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (
                        outcome.ticket_id,
                        outcome.review_status.value,
                        outcome.escalation_reason,
                        outcome.confidence,
                    ),
                )

    def fetch_human_queue(self) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticket_id, review_status, reason, confidence, resolved FROM human_review_queue ORDER BY ticket_id"
            ).fetchall()
        return [dict(r) for r in rows]
