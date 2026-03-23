#!/usr/bin/env python3
"""toctou-trust-detector.py — TOCTOU detection in agent trust scoring.

The gap santaclawd identified: check trust score → agent acts → score updates.
The window between "checked" and "acted" is where drift hides.

TOCTOU (Time-of-Check to Time-of-Use) is a classic race condition.
In trust: the score you checked may not be the score that was true
when the agent acted.

Fix: embed score-at-action-time in the receipt itself. The receipt
is the ground truth, not the last-read cache.

References:
- Bishop & Dilger (1996): Checking for Race Conditions in File Accesses
- Cai et al. (2009): TOCTOU Attacks on UNIX-Style File Systems
- santaclawd (2026-03-23): "TOCTOU in agent state machines"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustSnapshot:
    """Trust score at a specific moment."""
    score: float
    timestamp: float
    source: str  # "cache" | "live" | "receipt"
    hash: Optional[str] = None

    def __post_init__(self):
        if not self.hash:
            data = f"{self.score}:{self.timestamp}:{self.source}"
            self.hash = hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class TrustAction:
    """An action taken based on a trust check."""
    action_type: str
    check_snapshot: TrustSnapshot  # score when checked
    action_timestamp: float  # when action executed
    actual_score_at_action: Optional[float] = None  # true score at action time

    @property
    def toctou_gap_seconds(self) -> float:
        return self.action_timestamp - self.check_snapshot.timestamp

    @property
    def score_drift(self) -> Optional[float]:
        if self.actual_score_at_action is not None:
            return abs(self.actual_score_at_action - self.check_snapshot.score)
        return None


class TOCTOUDetector:
    """Detect TOCTOU gaps in trust scoring."""

    # Thresholds
    MAX_SAFE_GAP_SECONDS = 5.0  # Check must be within 5s of action
    SCORE_DRIFT_WARNING = 0.05  # 5% drift = warning
    SCORE_DRIFT_CRITICAL = 0.15  # 15% drift = critical
    STALE_CACHE_SECONDS = 30.0  # Cache older than 30s = stale

    def __init__(self):
        self.actions: list[TrustAction] = []
        self.violations: list[dict] = []

    def record_action(self, action: TrustAction) -> dict:
        """Record an action and check for TOCTOU violations."""
        self.actions.append(action)
        result = self._analyze(action)
        if result["severity"] != "SAFE":
            self.violations.append(result)
        return result

    def _analyze(self, action: TrustAction) -> dict:
        gap = action.toctou_gap_seconds
        drift = action.score_drift

        issues = []
        severity = "SAFE"

        # Gap analysis
        if gap > self.STALE_CACHE_SECONDS:
            issues.append(f"STALE_CHECK — {gap:.1f}s gap, cache expired")
            severity = "CRITICAL"
        elif gap > self.MAX_SAFE_GAP_SECONDS:
            issues.append(f"WIDE_GAP — {gap:.1f}s between check and action")
            severity = max(severity, "WARNING", key=lambda s: ["SAFE", "WARNING", "CRITICAL"].index(s))

        # Cache source
        if action.check_snapshot.source == "cache":
            issues.append("CACHED_CHECK — not live score")
            if severity == "SAFE":
                severity = "WARNING"

        # Score drift (if actual score known)
        if drift is not None:
            if drift > self.SCORE_DRIFT_CRITICAL:
                issues.append(f"SCORE_DRIFT_CRITICAL — {drift:.3f} drift during gap")
                severity = "CRITICAL"
            elif drift > self.SCORE_DRIFT_WARNING:
                issues.append(f"SCORE_DRIFT — {drift:.3f} drift during gap")
                severity = max(severity, "WARNING", key=lambda s: ["SAFE", "WARNING", "CRITICAL"].index(s))

        # Decision reversal check
        reversal = False
        if drift is not None and action.actual_score_at_action is not None:
            # Would decision change with actual score?
            check_allowed = action.check_snapshot.score >= 0.5
            actual_allowed = action.actual_score_at_action >= 0.5
            if check_allowed != actual_allowed:
                reversal = True
                issues.append("DECISION_REVERSAL — action would be different with actual score")
                severity = "CRITICAL"

        return {
            "action": action.action_type,
            "severity": severity,
            "gap_seconds": round(gap, 2),
            "check_score": round(action.check_snapshot.score, 3),
            "actual_score": round(action.actual_score_at_action, 3) if action.actual_score_at_action else None,
            "drift": round(drift, 3) if drift else None,
            "decision_reversal": reversal,
            "check_source": action.check_snapshot.source,
            "check_hash": action.check_snapshot.hash,
            "issues": issues,
        }

    def report(self) -> dict:
        total = len(self.actions)
        violations = len(self.violations)
        critical = sum(1 for v in self.violations if v["severity"] == "CRITICAL")
        warnings = sum(1 for v in self.violations if v["severity"] == "WARNING")

        avg_gap = 0
        if self.actions:
            avg_gap = sum(a.toctou_gap_seconds for a in self.actions) / total

        return {
            "total_actions": total,
            "violations": violations,
            "critical": critical,
            "warnings": warnings,
            "avg_gap_seconds": round(avg_gap, 2),
            "grade": self._grade(violations, critical, total),
            "recommendation": self._recommend(critical, warnings),
        }

    def _grade(self, violations: int, critical: int, total: int) -> str:
        if total == 0:
            return "N/A"
        if critical > 0:
            return "F"
        ratio = violations / total
        if ratio == 0:
            return "A"
        elif ratio < 0.05:
            return "B"
        elif ratio < 0.15:
            return "C"
        elif ratio < 0.30:
            return "D"
        return "F"

    def _recommend(self, critical: int, warnings: int) -> str:
        if critical > 0:
            return "EMBED_SCORE_IN_RECEIPT — score-at-action-time must be in receipt hash"
        if warnings > 0:
            return "REDUCE_GAP — move to live scoring or tighter cache TTL"
        return "HEALTHY — gaps within tolerance"


def demo():
    detector = TOCTOUDetector()
    now = time.time()

    print("=" * 60)
    print("SCENARIO 1: Tight gap, live check (SAFE)")
    print("=" * 60)
    result = detector.record_action(TrustAction(
        action_type="PAYMENT",
        check_snapshot=TrustSnapshot(score=0.85, timestamp=now - 1.0, source="live"),
        action_timestamp=now,
        actual_score_at_action=0.84,
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Stale cache, score drifted (CRITICAL)")
    print("=" * 60)
    result = detector.record_action(TrustAction(
        action_type="PAYMENT",
        check_snapshot=TrustSnapshot(score=0.72, timestamp=now - 45.0, source="cache"),
        action_timestamp=now,
        actual_score_at_action=0.38,  # dropped below threshold!
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Decision reversal (CRITICAL)")
    print("=" * 60)
    result = detector.record_action(TrustAction(
        action_type="ESCALATION",
        check_snapshot=TrustSnapshot(score=0.55, timestamp=now - 8.0, source="cache"),
        action_timestamp=now,
        actual_score_at_action=0.42,  # would have blocked instead of allowed
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Receipt-embedded score (SAFE)")
    print("=" * 60)
    result = detector.record_action(TrustAction(
        action_type="ATTESTATION",
        check_snapshot=TrustSnapshot(score=0.91, timestamp=now - 0.5, source="receipt"),
        action_timestamp=now,
        actual_score_at_action=0.91,  # no drift — score in receipt
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("OVERALL REPORT")
    print("=" * 60)
    print(json.dumps(detector.report(), indent=2))


if __name__ == "__main__":
    demo()
