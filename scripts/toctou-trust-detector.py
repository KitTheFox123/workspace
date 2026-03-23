#!/usr/bin/env python3
"""toctou-trust-detector.py — Detect TOCTOU race conditions in agent trust.

The trust gap nobody names: Time-of-Check to Time-of-Use in agent state.
Check trust score → agent acts → score updates. The window between
"checked" and "acted" is where drift hides.

CWE-367: TOCTOU race condition. Classic OS security problem.
In agent trust: the score you checked is not the score at action time.

Fix: receipt-at-action-time. Hash(state) at the moment of action,
not at check time. The receipt IS the snapshot.

Per santaclawd (Clawk, Mar 22-23): "if the verifier does [mint the
receipt], it's self-attesting. If a third party does, you need the
third party online at action time."

Solution: counterparty co-signs the receipt. Both parties hash their
view of state at action time. Divergence = TOCTOU detected.

References:
- CWE-367: Time-of-check Time-of-use Race Condition
- Lamport (1978): Time, Clocks, and the Ordering of Events
- Bishop & Dilger (1996): Checking for Race Conditions in File Accesses
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustSnapshot:
    """Trust state at a specific moment."""
    agent_id: str
    timestamp: float
    trust_score: float
    correction_count: int
    interaction_count: int
    last_receipt_hash: Optional[str] = None

    @property
    def state_hash(self) -> str:
        """Deterministic hash of trust state at this moment."""
        canonical = json.dumps({
            "agent_id": self.agent_id,
            "trust_score": round(self.trust_score, 4),
            "correction_count": self.correction_count,
            "interaction_count": self.interaction_count,
            "last_receipt_hash": self.last_receipt_hash,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class ActionReceipt:
    """Receipt minted at action time, not check time."""
    action_id: str
    agent_snapshot: TrustSnapshot
    counterparty_snapshot: Optional[TrustSnapshot]
    action_type: str
    action_timestamp: float
    check_timestamp: float  # When trust was originally checked

    @property
    def toctou_window_ms(self) -> float:
        """Time between check and action in milliseconds."""
        return (self.action_timestamp - self.check_timestamp) * 1000

    @property
    def state_diverged(self) -> bool:
        """Did agent state change between check and action?"""
        if self.counterparty_snapshot is None:
            return False  # Can't verify without counterparty
        return (
            self.agent_snapshot.state_hash
            != self.counterparty_snapshot.state_hash
        )


class TOCTOUDetector:
    """Detect and prevent TOCTOU in agent trust scoring.

    Three detection modes:
    1. WINDOW — check-to-action delay exceeds threshold
    2. DIVERGENCE — agent and counterparty disagree on state
    3. STALE — trust score used past its freshness TTL
    """

    WINDOW_WARN_MS = 500    # >500ms = suspicious
    WINDOW_BLOCK_MS = 5000  # >5s = block
    FRESHNESS_TTL_S = 60    # Trust scores expire after 60s
    MAX_DIVERGENCE_TOLERANCE = 0.05  # 5% score difference OK

    def __init__(self):
        self.receipts: list[ActionReceipt] = []
        self.violations: list[dict] = []

    def check_action(self, receipt: ActionReceipt) -> dict:
        """Evaluate a receipt for TOCTOU violations."""
        self.receipts.append(receipt)
        issues = []
        severity = "CLEAN"

        # Check 1: Window size
        window = receipt.toctou_window_ms
        if window > self.WINDOW_BLOCK_MS:
            issues.append({
                "type": "WINDOW_EXCEEDED",
                "detail": f"check-to-action: {window:.0f}ms (max: {self.WINDOW_BLOCK_MS}ms)",
                "severity": "BLOCK",
            })
            severity = "BLOCK"
        elif window > self.WINDOW_WARN_MS:
            issues.append({
                "type": "WINDOW_WARNING",
                "detail": f"check-to-action: {window:.0f}ms (warn: {self.WINDOW_WARN_MS}ms)",
                "severity": "WARN",
            })
            if severity != "BLOCK":
                severity = "WARN"

        # Check 2: State divergence
        if receipt.counterparty_snapshot:
            agent_score = receipt.agent_snapshot.trust_score
            cp_score = receipt.counterparty_snapshot.trust_score
            divergence = abs(agent_score - cp_score)

            if divergence > self.MAX_DIVERGENCE_TOLERANCE:
                issues.append({
                    "type": "STATE_DIVERGENCE",
                    "detail": f"agent={agent_score:.3f} vs counterparty={cp_score:.3f} (delta={divergence:.3f})",
                    "severity": "BLOCK" if divergence > 0.20 else "WARN",
                })
                if divergence > 0.20:
                    severity = "BLOCK"
                elif severity != "BLOCK":
                    severity = "WARN"

            if receipt.state_diverged:
                issues.append({
                    "type": "HASH_MISMATCH",
                    "detail": f"agent_hash={receipt.agent_snapshot.state_hash} vs cp_hash={receipt.counterparty_snapshot.state_hash}",
                    "severity": "CRITICAL",
                })
                severity = "CRITICAL"

        # Check 3: Freshness
        staleness = receipt.action_timestamp - receipt.check_timestamp
        if staleness > self.FRESHNESS_TTL_S:
            issues.append({
                "type": "STALE_SCORE",
                "detail": f"score age: {staleness:.0f}s (TTL: {self.FRESHNESS_TTL_S}s)",
                "severity": "BLOCK",
            })
            severity = "BLOCK"

        result = {
            "action_id": receipt.action_id,
            "verdict": severity,
            "toctou_window_ms": round(window, 1),
            "issues": issues,
            "recommendation": self._recommend(severity),
        }

        if severity != "CLEAN":
            self.violations.append(result)

        return result

    def _recommend(self, severity: str) -> str:
        if severity == "CRITICAL":
            return "HALT — state mismatch between agent and counterparty. Possible compromise."
        if severity == "BLOCK":
            return "RE-CHECK — trust score stale or window too large. Re-verify before action."
        if severity == "WARN":
            return "PROCEED_WITH_AUDIT — log for post-hoc review."
        return "PROCEED"

    def summary(self) -> dict:
        total = len(self.receipts)
        violations = len(self.violations)
        by_type = {}
        for v in self.violations:
            for issue in v["issues"]:
                t = issue["type"]
                by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_actions": total,
            "violations": violations,
            "violation_rate": round(violations / total, 3) if total > 0 else 0.0,
            "by_type": by_type,
        }


def demo():
    detector = TOCTOUDetector()
    now = time.time()

    print("=" * 60)
    print("SCENARIO 1: Clean action (fast, no divergence)")
    print("=" * 60)

    snap = TrustSnapshot("kit_fox", now, 0.85, 12, 60, "abc123")
    cp_snap = TrustSnapshot("kit_fox", now, 0.85, 12, 60, "abc123")
    receipt = ActionReceipt(
        action_id="action_001",
        agent_snapshot=snap,
        counterparty_snapshot=cp_snap,
        action_type="payment",
        action_timestamp=now + 0.1,  # 100ms later
        check_timestamp=now,
    )
    print(json.dumps(detector.check_action(receipt), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: TOCTOU — score changed between check and action")
    print("=" * 60)

    agent_snap = TrustSnapshot("suspicious_bot", now, 0.90, 5, 30, "def456")
    # Counterparty sees DIFFERENT state — score dropped during window
    cp_snap2 = TrustSnapshot("suspicious_bot", now + 3, 0.45, 8, 33, "ghi789")
    receipt2 = ActionReceipt(
        action_id="action_002",
        agent_snapshot=agent_snap,
        counterparty_snapshot=cp_snap2,
        action_type="payment",
        action_timestamp=now + 3,
        check_timestamp=now,
    )
    print(json.dumps(detector.check_action(receipt2), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Stale score (checked 2 minutes ago)")
    print("=" * 60)

    stale_snap = TrustSnapshot("slow_agent", now - 120, 0.75, 3, 15, "jkl012")
    receipt3 = ActionReceipt(
        action_id="action_003",
        agent_snapshot=stale_snap,
        counterparty_snapshot=None,
        action_type="data_access",
        action_timestamp=now,
        check_timestamp=now - 120,
    )
    print(json.dumps(detector.check_action(receipt3), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Borderline (600ms window, slight divergence)")
    print("=" * 60)

    snap4 = TrustSnapshot("edge_agent", now, 0.72, 7, 40, "mno345")
    cp_snap4 = TrustSnapshot("edge_agent", now + 0.6, 0.69, 7, 40, "mno345")
    receipt4 = ActionReceipt(
        action_id="action_004",
        agent_snapshot=snap4,
        counterparty_snapshot=cp_snap4,
        action_type="api_call",
        action_timestamp=now + 0.6,
        check_timestamp=now,
    )
    print(json.dumps(detector.check_action(receipt4), indent=2))

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(json.dumps(detector.summary(), indent=2))


if __name__ == "__main__":
    demo()
