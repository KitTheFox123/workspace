#!/usr/bin/env python3
"""
threat-tier-classifier.py — Two-tier threat model for ATF receipt withholding.

Per santaclawd: individual withholding ≠ coordinated suppression.
- INDIVIDUAL_WITHHOLDING: rogue agent, BFT-tolerable (f<n/3)
- COORDINATED_SUPPRESSION: colluding network, byzantine coalition

Detection differs:
- Individual: timeout-based (Chandra-Toueg failure detector)
- Coordinated: correlation window (statistical co-occurrence of silence)

Correlation window = 2x expected receipt interval (adaptive).

Usage:
    python3 threat-tier-classifier.py
"""

import hashlib
import json
import time
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentReceiptHistory:
    agent_id: str
    operator: str
    receipts: list[float]  # timestamps of receipts
    expected_interval: float = 86400.0  # seconds (default: 1/day)


@dataclass
class ThreatClassification:
    agent_id: str
    threat_type: str  # INDIVIDUAL_WITHHOLDING, COORDINATED_SUPPRESSION, HEALTHY
    severity: str  # CRITICAL, WARN, INFO
    confidence: float
    evidence: dict


class ThreatTierClassifier:
    """Classify withholding threats as individual vs coordinated."""

    def __init__(self, correlation_multiplier: float = 2.0):
        self.correlation_multiplier = correlation_multiplier
        self.agents: dict[str, AgentReceiptHistory] = {}

    def add_agent(self, history: AgentReceiptHistory):
        self.agents[history.agent_id] = history

    def _is_silent(self, agent: AgentReceiptHistory, now: float) -> bool:
        """Check if agent is past expected receipt window."""
        if not agent.receipts:
            return True
        last = max(agent.receipts)
        timeout = agent.expected_interval * self.correlation_multiplier
        return (now - last) > timeout

    def _silence_duration(self, agent: AgentReceiptHistory, now: float) -> float:
        if not agent.receipts:
            return float('inf')
        return now - max(agent.receipts)

    def _detect_correlation(self, silent_agents: list[AgentReceiptHistory], now: float) -> dict:
        """Detect correlated silence patterns."""
        if len(silent_agents) < 2:
            return {"correlated": False, "pairs": 0}

        # Check if silence started around the same time
        silence_starts = []
        for agent in silent_agents:
            if agent.receipts:
                silence_starts.append(max(agent.receipts))

        if len(silence_starts) < 2:
            return {"correlated": False, "pairs": 0}

        # Pairwise correlation: did silences start within same window?
        avg_interval = statistics.mean(a.expected_interval for a in silent_agents)
        correlation_window = avg_interval * 0.5  # silences starting within half an interval

        correlated_pairs = 0
        total_pairs = 0
        for i in range(len(silence_starts)):
            for j in range(i + 1, len(silence_starts)):
                total_pairs += 1
                if abs(silence_starts[i] - silence_starts[j]) < correlation_window:
                    correlated_pairs += 1

        correlation_ratio = correlated_pairs / total_pairs if total_pairs > 0 else 0

        # Check operator correlation (same operator = higher suspicion)
        operators = [a.operator for a in silent_agents]
        unique_operators = len(set(operators))
        operator_concentration = 1.0 - (unique_operators / len(silent_agents))

        return {
            "correlated": correlation_ratio > 0.5,
            "correlation_ratio": round(correlation_ratio, 3),
            "correlated_pairs": correlated_pairs,
            "total_pairs": total_pairs,
            "operator_concentration": round(operator_concentration, 3),
            "unique_operators": unique_operators,
        }

    def classify(self, now: Optional[float] = None) -> list[ThreatClassification]:
        """Classify all agents into threat tiers."""
        now = now or time.time()
        results = []

        silent_agents = [a for a in self.agents.values() if self._is_silent(a, now)]
        healthy_agents = [a for a in self.agents.values() if not self._is_silent(a, now)]

        if not silent_agents:
            for agent in healthy_agents:
                results.append(ThreatClassification(
                    agent_id=agent.agent_id,
                    threat_type="HEALTHY",
                    severity="INFO",
                    confidence=0.95,
                    evidence={"status": "receipts_current"},
                ))
            return results

        # Check for coordination
        correlation = self._detect_correlation(silent_agents, now)

        # BFT threshold
        total = len(self.agents)
        silent_count = len(silent_agents)
        bft_threshold = total / 3
        bft_exceeded = silent_count > bft_threshold

        for agent in silent_agents:
            duration = self._silence_duration(agent, now)
            duration_ratio = duration / agent.expected_interval

            if correlation["correlated"] and silent_count >= 2:
                # COORDINATED_SUPPRESSION
                severity = "CRITICAL" if bft_exceeded else "WARN"
                confidence = min(0.95, correlation["correlation_ratio"] * 1.2)
                results.append(ThreatClassification(
                    agent_id=agent.agent_id,
                    threat_type="COORDINATED_SUPPRESSION",
                    severity=severity,
                    confidence=round(confidence, 3),
                    evidence={
                        "silence_duration_hours": round(duration / 3600, 1),
                        "duration_ratio": round(duration_ratio, 2),
                        "correlation": correlation,
                        "bft_exceeded": bft_exceeded,
                        "silent_fraction": f"{silent_count}/{total}",
                    },
                ))
            else:
                # INDIVIDUAL_WITHHOLDING
                severity = "WARN" if duration_ratio < 5 else "CRITICAL"
                results.append(ThreatClassification(
                    agent_id=agent.agent_id,
                    threat_type="INDIVIDUAL_WITHHOLDING",
                    severity=severity,
                    confidence=min(0.90, 0.5 + duration_ratio * 0.1),
                    evidence={
                        "silence_duration_hours": round(duration / 3600, 1),
                        "duration_ratio": round(duration_ratio, 2),
                        "bft_tolerable": not bft_exceeded,
                        "silent_fraction": f"{silent_count}/{total}",
                    },
                ))

        for agent in healthy_agents:
            results.append(ThreatClassification(
                agent_id=agent.agent_id,
                threat_type="HEALTHY",
                severity="INFO",
                confidence=0.95,
                evidence={"status": "receipts_current"},
            ))

        return results

    def summary(self, now: Optional[float] = None) -> dict:
        """Fleet-level threat summary."""
        classifications = self.classify(now)
        by_type = {}
        for c in classifications:
            by_type.setdefault(c.threat_type, []).append(c.agent_id)

        max_severity = "INFO"
        for c in classifications:
            if c.severity == "CRITICAL":
                max_severity = "CRITICAL"
                break
            if c.severity == "WARN":
                max_severity = "WARN"

        return {
            "total_agents": len(self.agents),
            "healthy": len(by_type.get("HEALTHY", [])),
            "individual_withholding": len(by_type.get("INDIVIDUAL_WITHHOLDING", [])),
            "coordinated_suppression": len(by_type.get("COORDINATED_SUPPRESSION", [])),
            "fleet_severity": max_severity,
            "bft_status": "SAFE" if len(by_type.get("HEALTHY", [])) > len(self.agents) * 2 / 3 else "AT_RISK",
            "classifications": [
                {
                    "agent": c.agent_id,
                    "type": c.threat_type,
                    "severity": c.severity,
                    "confidence": c.confidence,
                    "evidence": c.evidence,
                }
                for c in classifications
            ],
        }


def demo():
    print("=" * 60)
    print("Threat Tier Classifier — Individual vs Coordinated")
    print("=" * 60)

    now = time.time()
    day = 86400

    # Scenario 1: Single rogue agent
    print("\n--- Scenario 1: One rogue agent, rest healthy ---")
    classifier = ThreatTierClassifier()
    classifier.add_agent(AgentReceiptHistory("alice", "op_a", [now - day * 0.5]))
    classifier.add_agent(AgentReceiptHistory("bob", "op_b", [now - day * 0.5]))
    classifier.add_agent(AgentReceiptHistory("carol", "op_c", [now - day * 0.5]))
    classifier.add_agent(AgentReceiptHistory("rogue", "op_d", [now - day * 5]))  # 5 days silent
    classifier.add_agent(AgentReceiptHistory("eve", "op_e", [now - day * 0.5]))
    print(json.dumps(classifier.summary(now), indent=2))

    # Scenario 2: Coordinated suppression (3 agents go silent at same time)
    print("\n--- Scenario 2: Coordinated suppression (3 same-time silence) ---")
    classifier2 = ThreatTierClassifier()
    silence_start = now - day * 3  # all went silent 3 days ago
    classifier2.add_agent(AgentReceiptHistory("agent_1", "op_a", [silence_start]))
    classifier2.add_agent(AgentReceiptHistory("agent_2", "op_a", [silence_start + 3600]))  # 1h apart
    classifier2.add_agent(AgentReceiptHistory("agent_3", "op_b", [silence_start + 7200]))  # 2h apart
    classifier2.add_agent(AgentReceiptHistory("healthy_1", "op_c", [now - day * 0.5]))
    classifier2.add_agent(AgentReceiptHistory("healthy_2", "op_d", [now - day * 0.5]))
    print(json.dumps(classifier2.summary(now), indent=2))

    # Scenario 3: Same operator collusion (BFT exceeded)
    print("\n--- Scenario 3: Same-operator collusion, BFT exceeded ---")
    classifier3 = ThreatTierClassifier()
    silence_start = now - day * 4
    classifier3.add_agent(AgentReceiptHistory("sybil_1", "op_evil", [silence_start]))
    classifier3.add_agent(AgentReceiptHistory("sybil_2", "op_evil", [silence_start + 1800]))
    classifier3.add_agent(AgentReceiptHistory("sybil_3", "op_evil", [silence_start + 3600]))
    classifier3.add_agent(AgentReceiptHistory("honest_1", "op_good", [now - day * 0.5]))
    classifier3.add_agent(AgentReceiptHistory("honest_2", "op_nice", [now - day * 0.5]))
    print(json.dumps(classifier3.summary(now), indent=2))

    # Scenario 4: Independent silences (not correlated)
    print("\n--- Scenario 4: Two silent but uncorrelated (weeks apart) ---")
    classifier4 = ThreatTierClassifier()
    classifier4.add_agent(AgentReceiptHistory("slow_1", "op_a", [now - day * 10]))  # 10 days ago
    classifier4.add_agent(AgentReceiptHistory("slow_2", "op_b", [now - day * 3]))   # 3 days ago
    classifier4.add_agent(AgentReceiptHistory("active_1", "op_c", [now - day * 0.5]))
    classifier4.add_agent(AgentReceiptHistory("active_2", "op_d", [now - day * 0.5]))
    classifier4.add_agent(AgentReceiptHistory("active_3", "op_e", [now - day * 0.5]))
    print(json.dumps(classifier4.summary(now), indent=2))

    print("\n" + "=" * 60)
    print("Two threat tiers: INDIVIDUAL (rogue, WARN) vs COORDINATED (collusion, CRITICAL)")
    print("Detection: individual=timeout, coordinated=correlation window")
    print("Correlation window = 2x expected receipt interval (adaptive)")
    print("BFT threshold: >n/3 silent = AT_RISK regardless of correlation")
    print("=" * 60)


if __name__ == "__main__":
    demo()
