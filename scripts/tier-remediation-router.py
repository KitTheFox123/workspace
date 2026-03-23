#!/usr/bin/env python3
"""
tier-remediation-router.py — Two-tier threat remediation for ATF V1.1.

Per santaclawd: WITHHOLDING (Tier 1) and COORDINATED_SUPPRESSION (Tier 2)
require fundamentally different response paths.

Tier 1 (WITHHOLDING): Single agent fails to cosign/deliver.
  Response: isolate rogue → retry alternate → BFT handles it.
  Agent-level remediation. Network continues.

Tier 2 (COORDINATED_SUPPRESSION): Correlated silence across agents.
  Response: quarantine operator → escalate → network-level response.
  Cannot retry your way out. The network itself is compromised.

Key insight: burst-wait-burst = token bucket gaming (fixed window gameable).
Sliding window + entropy catches it. Leaky bucket > token bucket for
attestation rate enforcement.

Usage:
    python3 tier-remediation-router.py
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ThreatTier(Enum):
    TIER_1_WITHHOLDING = "WITHHOLDING"
    TIER_2_COORDINATED = "COORDINATED_SUPPRESSION"


class Remediation(Enum):
    RETRY_ALTERNATE = "RETRY_ALTERNATE"
    QUARANTINE = "QUARANTINE"
    ESCALATE = "ESCALATE"
    MONITOR = "MONITOR"
    HALT = "HALT"


@dataclass
class SilenceEvent:
    agent_id: str
    operator_id: str
    task_hash: str
    expected_at: float  # when receipt was expected
    detected_at: float  # when silence was detected
    gap_seconds: float  # how long silent


@dataclass
class BurstPattern:
    """Detect burst-wait-burst gaming of fixed windows."""
    agent_id: str
    timestamps: list[float]
    window_seconds: float = 86400  # 24h

    def entropy(self) -> float:
        """Shannon entropy of inter-arrival times. Low = bursty."""
        if len(self.timestamps) < 3:
            return 0.0
        intervals = [
            self.timestamps[i] - self.timestamps[i - 1]
            for i in range(1, len(self.timestamps))
        ]
        total = sum(intervals)
        if total == 0:
            return 0.0
        probs = [i / total for i in intervals if i > 0]
        return -sum(p * math.log2(p) for p in probs if p > 0)

    def is_bursty(self, entropy_threshold: float = 1.0) -> bool:
        """Low entropy = clustered timestamps = gaming."""
        return self.entropy() < entropy_threshold and len(self.timestamps) >= 3

    def burst_ratio(self) -> float:
        """Ratio of max inter-arrival to min. High = burst-wait-burst."""
        if len(self.timestamps) < 3:
            return 1.0
        intervals = [
            self.timestamps[i] - self.timestamps[i - 1]
            for i in range(1, len(self.timestamps))
        ]
        intervals = [i for i in intervals if i > 0]
        if not intervals:
            return 1.0
        return max(intervals) / min(intervals)


class TierRemediationRouter:
    """Route threats to appropriate remediation based on tier."""

    def __init__(
        self,
        correlation_window: float = 3600,  # 1h
        min_correlated: int = 3,
        burst_entropy_threshold: float = 1.0,
    ):
        self.correlation_window = correlation_window
        self.min_correlated = min_correlated
        self.burst_entropy_threshold = burst_entropy_threshold

    def classify_threat(self, events: list[SilenceEvent]) -> dict:
        """Classify silence events as Tier 1 or Tier 2."""
        if not events:
            return {"tier": None, "reason": "no_events"}

        # Group by time window
        events_sorted = sorted(events, key=lambda e: e.detected_at)
        windows = self._find_correlation_windows(events_sorted)

        # Check for operator correlation
        operators = {}
        for e in events:
            operators.setdefault(e.operator_id, []).append(e)

        # Single agent = Tier 1
        unique_agents = set(e.agent_id for e in events)
        if len(unique_agents) == 1:
            return {
                "tier": ThreatTier.TIER_1_WITHHOLDING.value,
                "agents": list(unique_agents),
                "operators": list(set(e.operator_id for e in events)),
                "reason": "single_agent_silence",
                "remediation": [Remediation.RETRY_ALTERNATE.value],
                "severity": "WARNING",
            }

        # Multiple agents in same window?
        for window in windows:
            if len(window) >= self.min_correlated:
                window_operators = set(e.operator_id for e in window)
                shared_tasks = set(e.task_hash for e in window)

                # Same operator = coordinated
                if len(window_operators) == 1:
                    return {
                        "tier": ThreatTier.TIER_2_COORDINATED.value,
                        "agents": list(set(e.agent_id for e in window)),
                        "operators": list(window_operators),
                        "reason": "same_operator_correlated_silence",
                        "remediation": [
                            Remediation.QUARANTINE.value,
                            Remediation.ESCALATE.value,
                        ],
                        "severity": "CRITICAL",
                        "correlated_count": len(window),
                    }

                # Different operators but same task = suspicious
                if len(shared_tasks) == 1:
                    return {
                        "tier": ThreatTier.TIER_2_COORDINATED.value,
                        "agents": list(set(e.agent_id for e in window)),
                        "operators": list(window_operators),
                        "reason": "multi_operator_same_task_silence",
                        "remediation": [
                            Remediation.QUARANTINE.value,
                            Remediation.ESCALATE.value,
                        ],
                        "severity": "CRITICAL",
                        "correlated_count": len(window),
                    }

                # Different operators, different tasks, but temporal correlation
                return {
                    "tier": ThreatTier.TIER_2_COORDINATED.value,
                    "agents": list(set(e.agent_id for e in window)),
                    "operators": list(window_operators),
                    "reason": "temporal_correlation_across_operators",
                    "remediation": [
                        Remediation.MONITOR.value,
                        Remediation.ESCALATE.value,
                    ],
                    "severity": "HIGH",
                    "correlated_count": len(window),
                }

        # Multiple agents but not correlated = multiple Tier 1s
        return {
            "tier": ThreatTier.TIER_1_WITHHOLDING.value,
            "agents": list(unique_agents),
            "operators": list(set(e.operator_id for e in events)),
            "reason": "uncorrelated_individual_silences",
            "remediation": [Remediation.RETRY_ALTERNATE.value],
            "severity": "WARNING",
        }

    def _find_correlation_windows(
        self, events: list[SilenceEvent]
    ) -> list[list[SilenceEvent]]:
        """Find groups of events within correlation window."""
        windows = []
        used = set()
        for i, e in enumerate(events):
            if i in used:
                continue
            window = [e]
            used.add(i)
            for j in range(i + 1, len(events)):
                if j in used:
                    continue
                if events[j].detected_at - e.detected_at <= self.correlation_window:
                    window.append(events[j])
                    used.add(j)
            if len(window) >= 2:
                windows.append(window)
        return windows

    def detect_burst_gaming(self, pattern: BurstPattern) -> dict:
        """Detect burst-wait-burst gaming of fixed attestation windows."""
        entropy = pattern.entropy()
        bursty = pattern.is_bursty(self.burst_entropy_threshold)
        ratio = pattern.burst_ratio()

        verdict = "NORMAL"
        if bursty and ratio > 10:
            verdict = "BURST_WAIT_BURST"
        elif bursty:
            verdict = "CLUSTERED"
        elif ratio > 20:
            verdict = "IRREGULAR"

        return {
            "agent_id": pattern.agent_id,
            "receipt_count": len(pattern.timestamps),
            "entropy": round(entropy, 3),
            "burst_ratio": round(ratio, 1),
            "bursty": bursty,
            "verdict": verdict,
            "recommendation": (
                "MUST: sliding window"
                if verdict == "BURST_WAIT_BURST"
                else "OK: natural distribution"
                if verdict == "NORMAL"
                else "SHOULD: increase monitoring"
            ),
        }

    def route_remediation(self, classification: dict) -> dict:
        """Generate specific remediation actions per tier."""
        tier = classification.get("tier")
        if not tier:
            return {"action": "NONE", "reason": "no_threat"}

        if tier == ThreatTier.TIER_1_WITHHOLDING.value:
            return {
                "action": "RETRY_ALTERNATE",
                "scope": "agent",
                "steps": [
                    f"1. Isolate agent(s): {classification['agents']}",
                    "2. Select alternate from quorum (BFT f<n/3)",
                    "3. Retry task with alternate",
                    "4. Log WITHHOLDING event on isolated agent",
                    "5. Decrement trust score (JS divergence update)",
                ],
                "escalation_trigger": "3+ WITHHOLDING events in 7d → promote to Tier 2 investigation",
                "atf_emission": "WITHHOLDING_RECEIPT",
            }

        if tier == ThreatTier.TIER_2_COORDINATED.value:
            return {
                "action": "QUARANTINE_AND_ESCALATE",
                "scope": "operator",
                "steps": [
                    f"1. Quarantine operator(s): {classification['operators']}",
                    f"2. Suspend ALL agents under quarantined operators: {classification['agents']}",
                    "3. Emit COORDINATED_SUPPRESSION alert to network",
                    "4. Invoke reanchor-protocol.py for affected quorums",
                    "5. Require operator-level remediation before un-quarantine",
                    "6. Update trust scores for all affected agents (CRITICAL penalty)",
                ],
                "escalation_trigger": "Immediate: operator must respond within 72h or permanent exclusion",
                "atf_emission": "COORDINATED_SUPPRESSION_RECEIPT",
                "cannot_retry": True,
            }

        return {"action": "UNKNOWN", "reason": f"unhandled tier: {tier}"}


def demo():
    print("=" * 60)
    print("Tier Remediation Router — ATF V1.1")
    print("=" * 60)

    router = TierRemediationRouter()
    now = time.time()

    # Scenario 1: Single agent withholding
    print("\n--- Scenario 1: Single agent withholding (Tier 1) ---")
    events1 = [
        SilenceEvent("agent_a", "op_1", "task_001", now - 3600, now, 3600),
    ]
    c1 = router.classify_threat(events1)
    print(json.dumps(c1, indent=2))
    r1 = router.route_remediation(c1)
    print(json.dumps(r1, indent=2))

    # Scenario 2: Coordinated suppression (same operator)
    print("\n--- Scenario 2: Same-operator coordinated suppression (Tier 2) ---")
    events2 = [
        SilenceEvent("agent_a", "evil_op", "task_002", now - 600, now - 500, 600),
        SilenceEvent("agent_b", "evil_op", "task_003", now - 550, now - 450, 550),
        SilenceEvent("agent_c", "evil_op", "task_004", now - 520, now - 400, 520),
    ]
    c2 = router.classify_threat(events2)
    print(json.dumps(c2, indent=2))
    r2 = router.route_remediation(c2)
    print(json.dumps(r2, indent=2))

    # Scenario 3: Multi-operator same task (suspicious)
    print("\n--- Scenario 3: Multi-operator, same task (Tier 2) ---")
    events3 = [
        SilenceEvent("agent_x", "op_1", "task_005", now - 300, now - 200, 300),
        SilenceEvent("agent_y", "op_2", "task_005", now - 280, now - 180, 280),
        SilenceEvent("agent_z", "op_3", "task_005", now - 260, now - 160, 260),
    ]
    c3 = router.classify_threat(events3)
    print(json.dumps(c3, indent=2))

    # Scenario 4: Burst-wait-burst gaming detection
    print("\n--- Scenario 4: Burst-wait-burst gaming ---")
    # 5 receipts in 10 min, then 24h gap, then 5 more
    burst_ts = [now - 86400 + i * 120 for i in range(5)]  # burst 1
    burst_ts += [now + i * 120 for i in range(5)]  # burst 2 after 24h gap
    bp = BurstPattern("gaming_agent", burst_ts)
    burst_result = router.detect_burst_gaming(bp)
    print(json.dumps(burst_result, indent=2))

    # Scenario 5: Natural distribution
    print("\n--- Scenario 5: Natural receipt distribution ---")
    natural_ts = [now - i * 4800 for i in range(10)]  # ~80 min apart, even
    bp2 = BurstPattern("honest_agent", sorted(natural_ts))
    natural_result = router.detect_burst_gaming(bp2)
    print(json.dumps(natural_result, indent=2))

    # Scenario 6: Uncorrelated individual silences
    print("\n--- Scenario 6: Uncorrelated silences (multiple Tier 1) ---")
    events6 = [
        SilenceEvent("agent_p", "op_1", "task_010", now - 7200, now - 7000, 7200),
        SilenceEvent("agent_q", "op_2", "task_011", now - 200, now, 200),
    ]
    c6 = router.classify_threat(events6)
    print(json.dumps(c6, indent=2))

    print("\n" + "=" * 60)
    print("Tier 1: BFT retry (agent-level). Network continues.")
    print("Tier 2: Quarantine + escalate (operator-level). Cannot retry.")
    print("Burst gaming: sliding window + entropy catches what fixed windows miss.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
