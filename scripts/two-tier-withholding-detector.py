#!/usr/bin/env python3
"""
two-tier-withholding-detector.py — Distinguish individual withholding from coordinated suppression.

Per santaclawd: "individual withholding = RECEIPT_WITHHOLDING_ATTACK.
correlated silence across multiple agents = something worse: coordinated suppression."

Two threat tiers:
  Tier 1 (WARNING): Individual agent stops producing receipts
  Tier 2 (CRITICAL): Correlated silence across multiple agents

Detection methods:
  - Individual: expected receipt rate vs actual (Poisson model)
  - Coordinated: pairwise silence correlation (Pearson r > 0.7)
  - Shared operator/task as amplifier

References:
  - Moradi et al. (arXiv 2307.13906): Coordinated Byzantine attack covariance
  - Chandra & Toueg (1996): Failure detectors in distributed systems

Usage:
    python3 two-tier-withholding-detector.py
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentReceiptProfile:
    agent_id: str
    operator_id: str
    expected_rate_per_hour: float  # historical baseline
    active_tasks: list[str] = field(default_factory=list)
    receipt_timestamps: list[float] = field(default_factory=list)
    silence_windows: list[tuple[float, float]] = field(default_factory=list)  # (start, end)


@dataclass
class WithholdingEvent:
    tier: int  # 1 or 2
    severity: str  # WARNING or CRITICAL
    event_type: str  # INDIVIDUAL_WITHHOLDING or COORDINATED_SUPPRESSION
    agents: list[str]
    correlation_score: float  # 0.0 for individual, Pearson r for coordinated
    window_hours: float
    shared_operator: Optional[str]
    shared_tasks: list[str]
    confidence: float
    remediation: str


class TwoTierWithholdingDetector:
    """Detect and classify receipt withholding attacks."""

    def __init__(self, correlation_window_hours: float = 1.0, correlation_threshold: float = 0.7):
        self.correlation_window = correlation_window_hours
        self.correlation_threshold = correlation_threshold
        self.profiles: dict[str, AgentReceiptProfile] = {}

    def register_agent(self, profile: AgentReceiptProfile):
        self.profiles[profile.agent_id] = profile

    def _is_silent(self, profile: AgentReceiptProfile, window_start: float, window_end: float) -> bool:
        """Check if agent produced zero receipts in window."""
        receipts_in_window = [
            t for t in profile.receipt_timestamps
            if window_start <= t <= window_end
        ]
        return len(receipts_in_window) == 0

    def _silence_probability(self, profile: AgentReceiptProfile, window_hours: float) -> float:
        """Probability of zero receipts in window given expected rate (Poisson)."""
        expected = profile.expected_rate_per_hour * window_hours
        if expected <= 0:
            return 1.0
        return math.exp(-expected)  # P(X=0) = e^(-λ)

    def _pairwise_silence_correlation(
        self, p1: AgentReceiptProfile, p2: AgentReceiptProfile,
        time_slots: list[tuple[float, float]]
    ) -> float:
        """Pearson correlation of silence patterns across time slots."""
        if len(time_slots) < 3:
            return 0.0

        s1 = [1.0 if self._is_silent(p1, start, end) else 0.0 for start, end in time_slots]
        s2 = [1.0 if self._is_silent(p2, start, end) else 0.0 for start, end in time_slots]

        n = len(s1)
        mean1 = sum(s1) / n
        mean2 = sum(s2) / n

        cov = sum((a - mean1) * (b - mean2) for a, b in zip(s1, s2)) / n
        std1 = math.sqrt(sum((a - mean1) ** 2 for a in s1) / n)
        std2 = math.sqrt(sum((b - mean2) ** 2 for b in s2) / n)

        if std1 == 0 or std2 == 0:
            # Both always silent or never silent — check if same pattern
            return 1.0 if mean1 == mean2 else 0.0

        return cov / (std1 * std2)

    def detect(self, window_start: float, window_end: float) -> list[WithholdingEvent]:
        """Run detection across all registered agents."""
        events = []
        window_hours = (window_end - window_start) / 3600

        # Phase 1: Individual withholding detection
        silent_agents = []
        for agent_id, profile in self.profiles.items():
            if self._is_silent(profile, window_start, window_end):
                p_silence = self._silence_probability(profile, window_hours)
                if p_silence < 0.05:  # Statistically unlikely silence
                    silent_agents.append((agent_id, p_silence))
                    events.append(WithholdingEvent(
                        tier=1,
                        severity="WARNING",
                        event_type="INDIVIDUAL_WITHHOLDING",
                        agents=[agent_id],
                        correlation_score=0.0,
                        window_hours=window_hours,
                        shared_operator=profile.operator_id,
                        shared_tasks=profile.active_tasks,
                        confidence=1.0 - p_silence,
                        remediation="MONITOR: increase attestation frequency, notify counterparties",
                    ))

        # Phase 2: Coordinated suppression detection
        if len(silent_agents) >= 2:
            # Generate time slots for correlation analysis
            slot_duration = 600  # 10-minute slots
            slots = []
            t = window_start - 86400  # Look back 24h for pattern
            while t < window_end:
                slots.append((t, t + slot_duration))
                t += slot_duration

            silent_ids = [a[0] for a in silent_agents]
            checked_pairs = set()

            for i, aid1 in enumerate(silent_ids):
                for aid2 in silent_ids[i + 1:]:
                    pair_key = tuple(sorted([aid1, aid2]))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    p1 = self.profiles[aid1]
                    p2 = self.profiles[aid2]

                    corr = self._pairwise_silence_correlation(p1, p2, slots)

                    # Amplifiers
                    same_operator = p1.operator_id == p2.operator_id
                    shared_tasks = list(set(p1.active_tasks) & set(p2.active_tasks))

                    effective_threshold = self.correlation_threshold
                    if same_operator:
                        effective_threshold *= 0.8  # Lower bar for same operator
                    if shared_tasks:
                        effective_threshold *= 0.9

                    if corr >= effective_threshold:
                        # Coordinated suppression detected
                        group = [aid1, aid2]
                        # Check if more agents correlate
                        for aid3 in silent_ids:
                            if aid3 in group:
                                continue
                            p3 = self.profiles[aid3]
                            corr3_1 = self._pairwise_silence_correlation(p1, p3, slots)
                            corr3_2 = self._pairwise_silence_correlation(p2, p3, slots)
                            if corr3_1 >= effective_threshold and corr3_2 >= effective_threshold:
                                group.append(aid3)

                        events.append(WithholdingEvent(
                            tier=2,
                            severity="CRITICAL",
                            event_type="COORDINATED_SUPPRESSION",
                            agents=group,
                            correlation_score=corr,
                            window_hours=window_hours,
                            shared_operator=p1.operator_id if same_operator else None,
                            shared_tasks=shared_tasks,
                            confidence=min(0.99, corr * (1.2 if same_operator else 1.0)),
                            remediation="ESCALATE: emit COORDINATED_SUPPRESSION receipt, halt affected task pipelines, notify all counterparties",
                        ))

        # Deduplicate: if agents appear in Tier 2, upgrade from Tier 1
        tier2_agents = set()
        for e in events:
            if e.tier == 2:
                tier2_agents.update(e.agents)

        events = [
            e for e in events
            if not (e.tier == 1 and e.agents[0] in tier2_agents)
        ] + [e for e in events if e.tier == 2]

        # Deduplicate tier 2 events
        seen_groups = set()
        deduped = []
        for e in events:
            if e.tier == 2:
                key = tuple(sorted(e.agents))
                if key in seen_groups:
                    continue
                seen_groups.add(key)
            deduped.append(e)

        return deduped


def demo():
    print("=" * 60)
    print("Two-Tier Withholding Detector")
    print("=" * 60)

    now = time.time()
    hour = 3600

    # Scenario 1: Individual withholding
    print("\n--- Scenario 1: Individual withholding (rogue agent) ---")
    detector = TwoTierWithholdingDetector()

    # Normal agent: receipts every 30 min
    normal = AgentReceiptProfile(
        agent_id="honest_alice",
        operator_id="op_good",
        expected_rate_per_hour=2.0,
        active_tasks=["task_1"],
        receipt_timestamps=[now - i * 1800 for i in range(48)],  # 24h of receipts
    )

    # Withholding agent: stopped producing
    rogue = AgentReceiptProfile(
        agent_id="rogue_bob",
        operator_id="op_bad",
        expected_rate_per_hour=2.0,
        active_tasks=["task_1"],
        receipt_timestamps=[now - i * 1800 for i in range(24, 48)],  # stopped 12h ago
    )

    detector.register_agent(normal)
    detector.register_agent(rogue)

    events = detector.detect(now - 2 * hour, now)  # 2h window for statistical significance
    for e in events:
        print(json.dumps({
            "tier": e.tier,
            "severity": e.severity,
            "type": e.event_type,
            "agents": e.agents,
            "confidence": round(e.confidence, 3),
            "remediation": e.remediation,
        }, indent=2))

    # Scenario 2: Coordinated suppression (same operator)
    print("\n--- Scenario 2: Coordinated suppression (3 agents, same operator) ---")
    detector2 = TwoTierWithholdingDetector()

    # Create 3 agents that go silent at the same time
    for i, name in enumerate(["colluder_1", "colluder_2", "colluder_3"]):
        # All produced receipts, then all stopped 2h ago
        timestamps = [now - j * 1800 for j in range(5, 48)]  # stopped ~2.5h ago
        profile = AgentReceiptProfile(
            agent_id=name,
            operator_id="op_shady",  # Same operator!
            expected_rate_per_hour=2.0,
            active_tasks=["shared_task"],
            receipt_timestamps=timestamps,
        )
        detector2.register_agent(profile)

    # Add honest agent for comparison
    honest = AgentReceiptProfile(
        agent_id="honest_carol",
        operator_id="op_good",
        expected_rate_per_hour=2.0,
        active_tasks=["other_task"],
        receipt_timestamps=[now - i * 1800 for i in range(48)],
    )
    detector2.register_agent(honest)

    events2 = detector2.detect(now - 2 * hour, now)
    for e in events2:
        print(json.dumps({
            "tier": e.tier,
            "severity": e.severity,
            "type": e.event_type,
            "agents": e.agents,
            "correlation": round(e.correlation_score, 3),
            "shared_operator": e.shared_operator,
            "confidence": round(e.confidence, 3),
            "remediation": e.remediation,
        }, indent=2))

    # Scenario 3: Independent silence (different operators, different times)
    print("\n--- Scenario 3: Independent silence (not coordinated) ---")
    detector3 = TwoTierWithholdingDetector()

    # Agent A stopped 6h ago
    agent_a = AgentReceiptProfile(
        agent_id="indie_a",
        operator_id="op_1",
        expected_rate_per_hour=1.0,
        active_tasks=["task_x"],
        receipt_timestamps=[now - j * 3600 for j in range(6, 30)],
    )
    # Agent B stopped 1h ago
    agent_b = AgentReceiptProfile(
        agent_id="indie_b",
        operator_id="op_2",
        expected_rate_per_hour=1.0,
        active_tasks=["task_y"],
        # Receipts until 1h ago but with different timing
        receipt_timestamps=[now - 3700 - j * 3600 for j in range(24)],
    )
    detector3.register_agent(agent_a)
    detector3.register_agent(agent_b)

    events3 = detector3.detect(now - 2 * hour, now)
    for e in events3:
        print(json.dumps({
            "tier": e.tier,
            "severity": e.severity,
            "type": e.event_type,
            "agents": e.agents,
            "correlation": round(e.correlation_score, 3),
            "confidence": round(e.confidence, 3),
        }, indent=2))

    print("\n" + "=" * 60)
    print("Tier 1 (WARNING): Individual withholding — monitor + notify")
    print("Tier 2 (CRITICAL): Coordinated suppression — escalate + halt")
    print("Same operator = lower correlation threshold (0.8x)")
    print("Shared tasks = amplifier (0.9x threshold)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
