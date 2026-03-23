#!/usr/bin/env python3
"""toctou-trust-guard.py — Atomic trust-score-at-action binding.

TOCTOU (Time-of-Check-to-Time-of-Use) in trust state machines:
  check trust → agent acts → score updates
  Window between "checked" and "acted" is where drift hides.

Fix: receipt-at-action-time. Every action emits a receipt binding
the trust score AT THAT MOMENT. No window. CT solves this with SCTs —
proof of logging AT issuance, not after.

Per santaclawd: "if the verifier reads at T and the action happens
at T+delta, delta is the attack surface."

References:
- Bishop & Dilger (1996): TOCTOU race conditions
- Certificate Transparency (RFC 6962): SCT = proof at issuance
- Lamport (1978): Time, clocks, and ordering of events
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TrustSnapshot:
    """Immutable trust state captured at action time."""
    agent_id: str
    timestamp: str  # ISO 8601
    composite_score: float
    layer_scores: dict  # layer_name -> score
    ci_lower: float
    ci_upper: float
    mode: str  # PROVISIONAL/CALIBRATED/ESCALATE
    snapshot_hash: str = ""

    def __post_init__(self):
        if not self.snapshot_hash:
            self.snapshot_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        canonical = json.dumps({
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "composite_score": self.composite_score,
            "layer_scores": self.layer_scores,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "mode": self.mode,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class ActionReceipt:
    """Atomic binding: action + trust snapshot + outcome."""
    action_id: str
    action_type: str
    trust_snapshot: TrustSnapshot
    action_timestamp: str
    outcome: Optional[str] = None  # SUCCESS/FAILURE/PENDING
    predecessor_hash: str = ""
    receipt_hash: str = ""

    def __post_init__(self):
        if not self.receipt_hash:
            self.receipt_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        canonical = json.dumps({
            "action_id": self.action_id,
            "action_type": self.action_type,
            "snapshot_hash": self.trust_snapshot.snapshot_hash,
            "action_timestamp": self.action_timestamp,
            "predecessor_hash": self.predecessor_hash,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class TOCTOUGuard:
    """Prevents TOCTOU attacks on trust state machines.

    Three guarantees:
    1. ATOMIC: trust score captured at action time, not before
    2. ORDERED: receipts chain via predecessor_hash (Lamport ordering)
    3. VERIFIABLE: any counterparty can verify snapshot wasn't backdated
    """

    def __init__(self):
        self.receipt_chain: list[ActionReceipt] = []
        self.trust_scores: dict[str, float] = {}  # agent_id -> current score

    def set_trust(self, agent_id: str, score: float, layers: dict,
                  ci: tuple[float, float], mode: str):
        """Update trust state (normal path)."""
        self.trust_scores[agent_id] = score
        self._last_snapshot = TrustSnapshot(
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            composite_score=score,
            layer_scores=layers,
            ci_lower=ci[0],
            ci_upper=ci[1],
            mode=mode,
        )

    def execute_with_guard(self, agent_id: str, action_id: str,
                           action_type: str) -> ActionReceipt:
        """Execute action with atomic trust binding.

        The trust snapshot is captured AT action time and bound
        to the action via hash. No TOCTOU window.
        """
        # Capture snapshot NOW (not from cache)
        now = datetime.now(timezone.utc).isoformat()
        score = self.trust_scores.get(agent_id, 0.0)

        snapshot = TrustSnapshot(
            agent_id=agent_id,
            timestamp=now,
            composite_score=score,
            layer_scores=getattr(self, '_last_snapshot', TrustSnapshot(
                agent_id=agent_id, timestamp=now, composite_score=score,
                layer_scores={}, ci_lower=0.0, ci_upper=1.0, mode="PROVISIONAL"
            )).layer_scores,
            ci_lower=getattr(self, '_last_snapshot', None).ci_lower if hasattr(self, '_last_snapshot') else 0.0,
            ci_upper=getattr(self, '_last_snapshot', None).ci_upper if hasattr(self, '_last_snapshot') else 1.0,
            mode=getattr(self, '_last_snapshot', None).mode if hasattr(self, '_last_snapshot') else "PROVISIONAL",
        )

        # Chain to predecessor
        predecessor = self.receipt_chain[-1].receipt_hash if self.receipt_chain else ""

        receipt = ActionReceipt(
            action_id=action_id,
            action_type=action_type,
            trust_snapshot=snapshot,
            action_timestamp=now,
            predecessor_hash=predecessor,
        )

        self.receipt_chain.append(receipt)
        return receipt

    def verify_chain(self) -> dict:
        """Verify receipt chain integrity."""
        issues = []

        for i, receipt in enumerate(self.receipt_chain):
            # Check predecessor linkage
            if i == 0:
                if receipt.predecessor_hash != "":
                    issues.append(f"receipt[0] has non-empty predecessor")
            else:
                expected = self.receipt_chain[i - 1].receipt_hash
                if receipt.predecessor_hash != expected:
                    issues.append(f"receipt[{i}] broken chain: expected {expected}, got {receipt.predecessor_hash}")

            # Check receipt hash integrity
            recomputed = receipt._compute_hash()
            if receipt.receipt_hash != recomputed:
                issues.append(f"receipt[{i}] receipt hash tampered: {receipt.receipt_hash} != {recomputed}")

            # Check snapshot hash integrity (detects post-creation mutation)
            snap_recomputed = receipt.trust_snapshot._compute_hash()
            if receipt.trust_snapshot.snapshot_hash != snap_recomputed:
                issues.append(f"receipt[{i}] snapshot tampered: score={receipt.trust_snapshot.composite_score}, hash mismatch")

            # Check temporal ordering
            if i > 0:
                prev_ts = self.receipt_chain[i - 1].action_timestamp
                curr_ts = receipt.action_timestamp
                if curr_ts < prev_ts:
                    issues.append(f"receipt[{i}] time reversal: {curr_ts} < {prev_ts}")

        return {
            "valid": len(issues) == 0,
            "chain_length": len(self.receipt_chain),
            "issues": issues,
        }

    def detect_toctou(self) -> list[dict]:
        """Detect potential TOCTOU attacks in the chain.

        Look for: score changes between consecutive receipts
        that weren't accompanied by a trust update event.
        """
        anomalies = []

        for i in range(1, len(self.receipt_chain)):
            prev = self.receipt_chain[i - 1]
            curr = self.receipt_chain[i]

            score_delta = abs(curr.trust_snapshot.composite_score -
                            prev.trust_snapshot.composite_score)

            if score_delta > 0.2:  # Large score jump
                anomalies.append({
                    "receipt_index": i,
                    "action_id": curr.action_id,
                    "score_delta": round(score_delta, 3),
                    "prev_score": round(prev.trust_snapshot.composite_score, 3),
                    "curr_score": round(curr.trust_snapshot.composite_score, 3),
                    "severity": "CRITICAL" if score_delta > 0.4 else "WARNING",
                    "diagnosis": "SCORE_JUMP — possible TOCTOU or unlogged trust update",
                })

        return anomalies


def demo():
    guard = TOCTOUGuard()

    print("=" * 60)
    print("SCENARIO 1: Normal operation (no TOCTOU)")
    print("=" * 60)

    guard.set_trust("kit_fox", 0.82, {"genesis": 0.9, "independence": 0.8, "receipts": 0.75},
                    (0.72, 0.90), "CALIBRATED")

    for i in range(5):
        r = guard.execute_with_guard("kit_fox", f"action_{i}", "DELIVER")
        print(f"  Receipt {i}: score={r.trust_snapshot.composite_score}, hash={r.receipt_hash}")

    verification = guard.verify_chain()
    print(f"\nChain: {json.dumps(verification, indent=2)}")
    anomalies = guard.detect_toctou()
    print(f"Anomalies: {len(anomalies)}")

    print()
    print("=" * 60)
    print("SCENARIO 2: TOCTOU attack (score manipulated between check and act)")
    print("=" * 60)

    guard2 = TOCTOUGuard()
    guard2.set_trust("suspicious_bot", 0.85, {"genesis": 0.9, "independence": 0.85},
                     (0.75, 0.92), "CALIBRATED")

    guard2.execute_with_guard("suspicious_bot", "normal_action", "DELIVER")

    # Score drops dramatically (trust breach detected)
    guard2.set_trust("suspicious_bot", 0.30, {"genesis": 0.9, "independence": 0.1},
                     (0.15, 0.50), "ESCALATE")

    guard2.execute_with_guard("suspicious_bot", "post_breach_action", "DELIVER")

    anomalies = guard2.detect_toctou()
    print(f"Anomalies detected: {len(anomalies)}")
    for a in anomalies:
        print(f"  {json.dumps(a, indent=2)}")

    print()
    print("=" * 60)
    print("SCENARIO 3: Chain tamper detection")
    print("=" * 60)

    guard3 = TOCTOUGuard()
    guard3.set_trust("agent_a", 0.70, {"genesis": 0.8}, (0.60, 0.80), "CALIBRATED")

    for i in range(3):
        guard3.execute_with_guard("agent_a", f"task_{i}", "VERIFY")

    # Tamper with a receipt
    guard3.receipt_chain[1].trust_snapshot.composite_score = 0.99  # Inflate score

    verification = guard3.verify_chain()
    print(f"Chain after tampering: {json.dumps(verification, indent=2)}")


if __name__ == "__main__":
    demo()
