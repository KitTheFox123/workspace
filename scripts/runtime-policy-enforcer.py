#!/usr/bin/env python3
"""runtime-policy-enforcer.py — Runtime contract enforcement.

Complement to dispute-prevention-auditor.py (pre-contract gates).
This enforces DURING execution: delivery timeline, quality trajectory,
escrow conditions, and counterparty acknowledgment.

Per santaclawd: "pre-dispute checks gate before contract. policy
enforcer checks at runtime. together: eliminate the ambiguity window."

Curry-Howard parallel: receipt IS the deliverable. ATF tests membership
(did you claim what you did?) not correctness (was the claim true?).

References:
- Tetlock (2015): Superforecasting — calibration > confidence
- Hollnagel (2009): ETTO — efficiency-thoroughness trade-off
- Rasmussen (1997): drift to boundary of acceptable performance
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from enum import Enum


class PolicyAction(Enum):
    CONTINUE = "CONTINUE"
    WARN = "WARN"
    PAUSE = "PAUSE"
    ESCALATE = "ESCALATE"
    TERMINATE = "TERMINATE"


@dataclass
class DeliveryCheckpoint:
    """A point-in-time check during contract execution."""
    checkpoint_id: str
    timestamp: str
    deliverable_hash: Optional[str]
    quality_score: float  # 0.0-1.0
    counterparty_ack: bool
    latency_ms: Optional[int] = None


@dataclass
class RuntimePolicy:
    """Policy rules for runtime enforcement."""
    max_delivery_latency_ms: int = 30000
    min_quality_score: float = 0.5
    quality_degradation_threshold: float = 0.2  # max drop between checkpoints
    require_counterparty_ack: bool = True
    max_unacked_checkpoints: int = 2
    escrow_release_min_quality: float = 0.7
    max_consecutive_warnings: int = 3


@dataclass
class EnforcementState:
    """Tracks runtime enforcement state across checkpoints."""
    checkpoints: List[DeliveryCheckpoint] = field(default_factory=list)
    warnings: int = 0
    paused: bool = False
    terminated: bool = False
    escrow_released: bool = False

    @property
    def quality_trajectory(self) -> List[float]:
        return [c.quality_score for c in self.checkpoints]

    @property
    def avg_quality(self) -> float:
        if not self.checkpoints:
            return 0.0
        return sum(c.quality_score for c in self.checkpoints) / len(self.checkpoints)

    @property
    def quality_slope(self) -> float:
        """Linear regression slope of quality over checkpoints."""
        scores = self.quality_trajectory
        if len(scores) < 2:
            return 0.0
        n = len(scores)
        x_mean = (n - 1) / 2
        y_mean = sum(scores) / n
        num = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
        den = sum((i - x_mean) ** 2 for i in range(n))
        return num / den if den > 0 else 0.0

    @property
    def unacked_count(self) -> int:
        return sum(1 for c in self.checkpoints if not c.counterparty_ack)


class RuntimePolicyEnforcer:
    """Enforces contract policies at runtime checkpoints."""

    def __init__(self, policy: RuntimePolicy):
        self.policy = policy
        self.state = EnforcementState()

    def check(self, checkpoint: DeliveryCheckpoint) -> dict:
        """Evaluate a checkpoint against policy. Returns action + diagnosis."""
        self.state.checkpoints.append(checkpoint)
        violations = []
        action = PolicyAction.CONTINUE

        # Check 1: Delivery latency
        if checkpoint.latency_ms and checkpoint.latency_ms > self.policy.max_delivery_latency_ms:
            violations.append({
                "rule": "MAX_DELIVERY_LATENCY",
                "expected": f"≤{self.policy.max_delivery_latency_ms}ms",
                "actual": f"{checkpoint.latency_ms}ms",
                "severity": "WARNING",
            })
            action = max(action, PolicyAction.WARN, key=lambda x: list(PolicyAction).index(x))

        # Check 2: Quality floor
        if checkpoint.quality_score < self.policy.min_quality_score:
            violations.append({
                "rule": "MIN_QUALITY_SCORE",
                "expected": f"≥{self.policy.min_quality_score}",
                "actual": f"{checkpoint.quality_score:.2f}",
                "severity": "ESCALATE",
            })
            action = max(action, PolicyAction.ESCALATE, key=lambda x: list(PolicyAction).index(x))

        # Check 3: Quality degradation between checkpoints
        if len(self.state.checkpoints) >= 2:
            prev = self.state.checkpoints[-2].quality_score
            curr = checkpoint.quality_score
            drop = prev - curr
            if drop > self.policy.quality_degradation_threshold:
                violations.append({
                    "rule": "QUALITY_DEGRADATION",
                    "expected": f"drop ≤{self.policy.quality_degradation_threshold}",
                    "actual": f"drop={drop:.2f} ({prev:.2f}→{curr:.2f})",
                    "severity": "PAUSE",
                    "note": "Rasmussen drift — quality sliding toward boundary",
                })
                action = max(action, PolicyAction.PAUSE, key=lambda x: list(PolicyAction).index(x))

        # Check 4: Counterparty acknowledgment
        if self.policy.require_counterparty_ack and not checkpoint.counterparty_ack:
            if self.state.unacked_count > self.policy.max_unacked_checkpoints:
                violations.append({
                    "rule": "COUNTERPARTY_ACK",
                    "expected": f"max {self.policy.max_unacked_checkpoints} unacked",
                    "actual": f"{self.state.unacked_count} unacked",
                    "severity": "PAUSE",
                })
                action = max(action, PolicyAction.PAUSE, key=lambda x: list(PolicyAction).index(x))

        # Check 5: Quality trajectory (Tetlock: calibration over confidence)
        slope = self.state.quality_slope
        if len(self.state.checkpoints) >= 3 and slope < -0.1:
            violations.append({
                "rule": "QUALITY_TRAJECTORY",
                "expected": "slope ≥ -0.1",
                "actual": f"slope={slope:.3f}",
                "severity": "ESCALATE",
                "note": "Declining trajectory — Tetlock: track record matters more than last call",
            })
            action = max(action, PolicyAction.ESCALATE, key=lambda x: list(PolicyAction).index(x))

        # Check 6: Missing deliverable hash
        if not checkpoint.deliverable_hash:
            violations.append({
                "rule": "DELIVERABLE_HASH",
                "expected": "non-null hash",
                "actual": "null",
                "severity": "ESCALATE",
                "note": "No hash = deniable delivery",
            })
            action = max(action, PolicyAction.ESCALATE, key=lambda x: list(PolicyAction).index(x))

        # Warning accumulation
        if action == PolicyAction.WARN:
            self.state.warnings += 1
            if self.state.warnings >= self.policy.max_consecutive_warnings:
                action = PolicyAction.PAUSE
                violations.append({
                    "rule": "WARNING_ACCUMULATION",
                    "expected": f"<{self.policy.max_consecutive_warnings} consecutive",
                    "actual": f"{self.state.warnings} consecutive",
                    "severity": "PAUSE",
                })
        elif action == PolicyAction.CONTINUE:
            self.state.warnings = 0  # reset on clean checkpoint

        # Escrow check
        escrow_eligible = (
            self.state.avg_quality >= self.policy.escrow_release_min_quality
            and self.state.unacked_count == 0
            and action == PolicyAction.CONTINUE
        )

        return {
            "checkpoint_id": checkpoint.checkpoint_id,
            "action": action.value,
            "violations": violations,
            "state": {
                "total_checkpoints": len(self.state.checkpoints),
                "avg_quality": round(self.state.avg_quality, 3),
                "quality_slope": round(self.state.quality_slope, 3),
                "consecutive_warnings": self.state.warnings,
                "unacked": self.state.unacked_count,
            },
            "escrow": {
                "eligible_for_release": escrow_eligible,
                "min_quality_met": self.state.avg_quality >= self.policy.escrow_release_min_quality,
                "all_acked": self.state.unacked_count == 0,
            },
        }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Healthy contract execution")
    print("=" * 60)

    enforcer = RuntimePolicyEnforcer(RuntimePolicy())
    checkpoints = [
        DeliveryCheckpoint("cp1", "2026-03-22T06:00:00Z", "sha256:aaa", 0.85, True, 1200),
        DeliveryCheckpoint("cp2", "2026-03-22T06:10:00Z", "sha256:bbb", 0.88, True, 1100),
        DeliveryCheckpoint("cp3", "2026-03-22T06:20:00Z", "sha256:ccc", 0.90, True, 1050),
    ]
    for cp in checkpoints:
        result = enforcer.check(cp)
        print(json.dumps(result, indent=2))
        print()

    print("=" * 60)
    print("SCENARIO 2: Quality degradation (Rasmussen drift)")
    print("=" * 60)

    enforcer2 = RuntimePolicyEnforcer(RuntimePolicy())
    checkpoints2 = [
        DeliveryCheckpoint("cp1", "2026-03-22T06:00:00Z", "sha256:aaa", 0.90, True, 1200),
        DeliveryCheckpoint("cp2", "2026-03-22T06:10:00Z", "sha256:bbb", 0.75, True, 2500),
        DeliveryCheckpoint("cp3", "2026-03-22T06:20:00Z", "sha256:ccc", 0.50, True, 5000),
        DeliveryCheckpoint("cp4", "2026-03-22T06:30:00Z", "sha256:ddd", 0.35, False, 45000),
    ]
    for cp in checkpoints2:
        result = enforcer2.check(cp)
        print(json.dumps(result, indent=2))
        print()

    print("=" * 60)
    print("SCENARIO 3: Missing hash (deniable delivery)")
    print("=" * 60)

    enforcer3 = RuntimePolicyEnforcer(RuntimePolicy())
    result = enforcer3.check(
        DeliveryCheckpoint("cp1", "2026-03-22T06:00:00Z", None, 0.80, True, 1000)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
