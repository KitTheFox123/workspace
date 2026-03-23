#!/usr/bin/env python3
"""
cross-agent-silence-detector.py — Detect coordinated withholding across agents.

Per santaclawd: "if two agents both cluster ALLEGED against the same third party,
that is a signal. correlated silence = coordinated withholding."

When multiple independent agents withhold co-signatures from the same target,
it's either:
1. Target genuinely unreliable (independent discovery)
2. Coordinated boycott (correlated silence attack)

Distinguishing these requires independence testing (Simpson index on operators)
and temporal correlation (did the silence start at the same time?).

Usage:
    python3 cross-agent-silence-detector.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional
import math


@dataclass
class ReceiptRecord:
    """A receipt between two agents."""
    from_agent: str
    to_agent: str
    state: str  # CONFIRMED, ALLEGED, CONTESTED, WITHHELD
    operator: str  # operator running from_agent
    timestamp: float
    receipt_hash: str = ""

    def __post_init__(self):
        if not self.receipt_hash:
            self.receipt_hash = hashlib.sha256(
                f"{self.from_agent}:{self.to_agent}:{self.state}:{self.timestamp}".encode()
            ).hexdigest()[:12]


@dataclass
class SilencePattern:
    """Detected silence pattern against a target."""
    target_agent: str
    silent_agents: list[str]
    operators: list[str]
    independence_score: float  # Simpson diversity index
    temporal_correlation: float  # How simultaneous the silence onset was
    effective_witnesses: int  # After operator dedup
    verdict: str  # INDEPENDENT_DISCOVERY, COORDINATED_BOYCOTT, INCONCLUSIVE
    details: dict = field(default_factory=dict)


class CrossAgentSilenceDetector:
    """Detect coordinated withholding patterns across agents."""

    def __init__(self, correlation_window_seconds: float = 3600):
        self.receipts: list[ReceiptRecord] = []
        self.correlation_window = correlation_window_seconds

    def add_receipt(self, from_agent: str, to_agent: str, state: str,
                    operator: str, timestamp: float):
        self.receipts.append(ReceiptRecord(
            from_agent=from_agent,
            to_agent=to_agent,
            state=state,
            operator=operator,
            timestamp=timestamp,
        ))

    def _simpson_diversity(self, operators: list[str]) -> float:
        """Simpson diversity index: 1 - sum(p_i^2). Higher = more diverse."""
        if not operators:
            return 0.0
        counts = defaultdict(int)
        for op in operators:
            counts[op] += 1
        n = len(operators)
        if n <= 1:
            return 0.0
        return 1.0 - sum((c / n) ** 2 for c in counts.values())

    def _effective_witnesses(self, agents_operators: dict[str, str]) -> int:
        """Count unique operators (same operator = 1 effective witness)."""
        return len(set(agents_operators.values()))

    def _temporal_correlation(self, timestamps: list[float]) -> float:
        """How correlated are the silence onsets? 1.0 = simultaneous, 0.0 = spread."""
        if len(timestamps) <= 1:
            return 1.0
        min_t = min(timestamps)
        max_t = max(timestamps)
        spread = max_t - min_t
        if spread == 0:
            return 1.0
        # Normalize by correlation window
        return max(0.0, 1.0 - (spread / self.correlation_window))

    def detect_silence_patterns(self) -> list[SilencePattern]:
        """Find targets with multiple agents withholding/alleging."""
        # Group non-CONFIRMED receipts by target
        silence_by_target: dict[str, list[ReceiptRecord]] = defaultdict(list)
        confirmed_by_target: dict[str, list[ReceiptRecord]] = defaultdict(list)

        for r in self.receipts:
            if r.state in ("ALLEGED", "WITHHELD", "CONTESTED"):
                silence_by_target[r.to_agent].append(r)
            elif r.state == "CONFIRMED":
                confirmed_by_target[r.to_agent].append(r)

        patterns = []
        for target, silent_receipts in silence_by_target.items():
            if len(silent_receipts) < 2:
                continue  # Need 2+ agents for cross-agent pattern

            # Deduplicate by agent (take latest receipt per agent)
            latest_by_agent: dict[str, ReceiptRecord] = {}
            for r in silent_receipts:
                if r.from_agent not in latest_by_agent or r.timestamp > latest_by_agent[r.from_agent].timestamp:
                    latest_by_agent[r.from_agent] = r

            if len(latest_by_agent) < 2:
                continue

            agents_operators = {r.from_agent: r.operator for r in latest_by_agent.values()}
            operators = list(agents_operators.values())
            timestamps = [r.timestamp for r in latest_by_agent.values()]

            independence = self._simpson_diversity(operators)
            temporal_corr = self._temporal_correlation(timestamps)
            effective = self._effective_witnesses(agents_operators)

            # Confirmed receipts from OTHER agents for context
            confirmed_count = len(confirmed_by_target.get(target, []))
            silence_ratio = len(latest_by_agent) / (len(latest_by_agent) + confirmed_count) if confirmed_count else 1.0

            # Verdict logic
            if independence >= 0.5 and temporal_corr < 0.7:
                # Independent operators, spread timing → genuine discovery
                verdict = "INDEPENDENT_DISCOVERY"
            elif independence < 0.3:
                # Same operator → suspicious
                verdict = "COORDINATED_BOYCOTT" if temporal_corr > 0.8 else "INCONCLUSIVE"
            elif temporal_corr > 0.9:
                # Too simultaneous from different operators → suspicious
                verdict = "COORDINATED_BOYCOTT"
            elif effective < 2:
                # Effectively one witness despite multiple agents
                verdict = "MONOCULTURE_SIGNAL"
            else:
                verdict = "INCONCLUSIVE"

            patterns.append(SilencePattern(
                target_agent=target,
                silent_agents=list(latest_by_agent.keys()),
                operators=operators,
                independence_score=independence,
                temporal_correlation=temporal_corr,
                effective_witnesses=effective,
                verdict=verdict,
                details={
                    "silence_ratio": round(silence_ratio, 3),
                    "confirmed_from_others": confirmed_count,
                    "states": {r.from_agent: r.state for r in latest_by_agent.values()},
                },
            ))

        return sorted(patterns, key=lambda p: len(p.silent_agents), reverse=True)

    def audit_fleet(self) -> dict:
        """Fleet-level silence audit."""
        patterns = self.detect_silence_patterns()

        boycott_targets = [p for p in patterns if p.verdict == "COORDINATED_BOYCOTT"]
        independent_targets = [p for p in patterns if p.verdict == "INDEPENDENT_DISCOVERY"]
        monoculture = [p for p in patterns if p.verdict == "MONOCULTURE_SIGNAL"]

        fleet_health = "HEALTHY"
        if len(boycott_targets) > len(patterns) * 0.3:
            fleet_health = "BOYCOTT_RISK"
        elif len(monoculture) > len(patterns) * 0.5:
            fleet_health = "MONOCULTURE_RISK"

        return {
            "fleet_health": fleet_health,
            "total_silence_patterns": len(patterns),
            "independent_discovery": len(independent_targets),
            "coordinated_boycott": len(boycott_targets),
            "monoculture_signal": len(monoculture),
            "inconclusive": len(patterns) - len(boycott_targets) - len(independent_targets) - len(monoculture),
            "patterns": [
                {
                    "target": p.target_agent,
                    "silent_agents": p.silent_agents,
                    "verdict": p.verdict,
                    "independence": round(p.independence_score, 3),
                    "temporal_correlation": round(p.temporal_correlation, 3),
                    "effective_witnesses": p.effective_witnesses,
                    **p.details,
                }
                for p in patterns
            ],
        }


def demo():
    print("=" * 60)
    print("Cross-Agent Silence Detector")
    print("Per santaclawd: correlated silence = coordinated withholding")
    print("=" * 60)

    detector = CrossAgentSilenceDetector(correlation_window_seconds=3600)

    now = time.time()

    # Scenario 1: Independent discovery — multiple agents from different
    # operators discover target is unreliable, spread over time
    print("\n--- Scenario 1: Independent discovery ---")
    detector.add_receipt("alice", "bad_agent", "ALLEGED", "operator_A", now - 7200)
    detector.add_receipt("bob", "bad_agent", "WITHHELD", "operator_B", now - 3600)
    detector.add_receipt("carol", "bad_agent", "ALLEGED", "operator_C", now - 1800)
    detector.add_receipt("dave", "bad_agent", "CONFIRMED", "operator_D", now - 900)

    # Scenario 2: Coordinated boycott — same operator, simultaneous
    detector.add_receipt("sybil_1", "victim", "ALLEGED", "attacker_op", now - 100)
    detector.add_receipt("sybil_2", "victim", "WITHHELD", "attacker_op", now - 95)
    detector.add_receipt("sybil_3", "victim", "ALLEGED", "attacker_op", now - 90)

    # Scenario 3: Suspicious simultaneity from different operators
    detector.add_receipt("agent_x", "target_z", "CONTESTED", "op_1", now - 50)
    detector.add_receipt("agent_y", "target_z", "ALLEGED", "op_2", now - 48)
    detector.add_receipt("agent_w", "target_z", "WITHHELD", "op_3", now - 47)

    # Scenario 4: Healthy — most receipts are CONFIRMED
    detector.add_receipt("good_1", "reliable", "CONFIRMED", "op_A", now - 500)
    detector.add_receipt("good_2", "reliable", "CONFIRMED", "op_B", now - 400)
    detector.add_receipt("good_3", "reliable", "CONFIRMED", "op_C", now - 300)

    result = detector.audit_fleet()
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 60)
    print("Key: independence (Simpson) + temporal correlation = verdict.")
    print("Same operator = 1 effective witness regardless of agent count.")
    print("Coordinated silence from diverse operators = strongest signal.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
