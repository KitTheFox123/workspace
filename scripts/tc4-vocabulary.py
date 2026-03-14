"""
vocabulary.py — genesis adapter for agent-trust-harness
Maps raw trust signals to normalized vocabulary entries.
Delivered by bro_agent (tc4 contract 52a3c71c, Mar 14 2026).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class VocabularyEntry:
    term: str
    score: float          # 0.0-1.0 trust signal strength
    source: str           # originating agent or system
    evidence_hash: Optional[str] = None  # sha256 of backing artifact
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None


class VocabularyAdapter:
    """
    Genesis adapter: consumes raw inputs, emits normalized VocabularyEntry objects.
    Downstream adapters (survivorship, remediation, gossip) consume these.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._entries: List[VocabularyEntry] = []

    def ingest(self, raw: dict) -> VocabularyEntry:
        """Normalize a raw signal dict to VocabularyEntry."""
        score = float(raw.get("score", 0.5))
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Score {score} outside 0-1 range")
        entry = VocabularyEntry(
            term=raw["term"],
            score=score,
            source=raw.get("source", "unknown"),
            evidence_hash=raw.get("evidence_hash"),
            tags=raw.get("tags", []),
            created_at=raw.get("created_at"),
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> List[VocabularyEntry]:
        return list(self._entries)

    def flush(self) -> List[VocabularyEntry]:
        out = self._entries
        self._entries = []
        return out

    def as_dict(self) -> List[dict]:
        return [
            {
                "term": e.term,
                "score": e.score,
                "source": e.source,
                "evidence_hash": e.evidence_hash,
                "tags": e.tags,
            }
            for e in self._entries
        ]
