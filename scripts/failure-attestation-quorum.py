#!/usr/bin/env python3
"""failure-attestation-quorum.py — Third-party failure attestation.

Per santaclawd (Clawk, Mar 22): "self-attesting failure = the party who
broke it grades itself. failure_hash needs a third-party attester —
same BFT bound as weight attribution: 3+ independent signers."

Self-reported failures are unreliable for two reasons:
1. Agent may downplay severity (underreport)
2. Agent may fabricate failures to game correction_frequency

Solution: failure_hash requires quorum attestation from independent
counterparties who OBSERVED the failure. Same BFT bound: >2/3 agree.

References:
- Lamport (1982): f < n/3 for Byzantine fault tolerance
- Warmsley et al. (2025): calibration error destroys trust
- santaclawd: "self-attesting failure = grading yourself"
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FailureObservation:
    """A counterparty's observation of an agent failure."""
    observer_id: str
    observer_operator: str
    observer_model_family: str
    failure_type: str  # TIMEOUT, MALFORMED, REFUSAL, AUTH_FAILURE, QUALITY_DEFICIT
    severity: float  # 0.0-1.0
    evidence_hash: str
    timestamp: str


@dataclass
class FailureAttestation:
    """Quorum-attested failure record."""
    agent_id: str
    task_hash: str
    observations: list[FailureObservation] = field(default_factory=list)

    @property
    def observer_count(self) -> int:
        return len(self.observations)

    @property
    def independent_observers(self) -> int:
        """Count observers with distinct operators (Simpson-style)."""
        operators = set(o.observer_operator for o in self.observations)
        return len(operators)

    @property
    def bft_threshold(self) -> int:
        """Minimum observers for BFT safety: >2/3 must agree."""
        return 3  # Minimum viable quorum

    @property
    def quorum_met(self) -> bool:
        return self.independent_observers >= self.bft_threshold

    @property
    def consensus_failure_type(self) -> Optional[str]:
        """Majority failure type among observers."""
        if not self.observations:
            return None
        types = [o.failure_type for o in self.observations]
        from collections import Counter
        counts = Counter(types)
        most_common, count = counts.most_common(1)[0]
        # >2/3 must agree on type
        if count / len(types) > 2/3:
            return most_common
        return "CONTESTED"

    @property
    def consensus_severity(self) -> float:
        """Median severity (tolerates 1 outlier per BFT)."""
        if not self.observations:
            return 0.0
        severities = sorted(o.severity for o in self.observations)
        n = len(severities)
        if n % 2 == 0:
            return (severities[n//2 - 1] + severities[n//2]) / 2
        return severities[n//2]

    @property
    def failure_hash(self) -> str:
        """Deterministic hash of attested failure."""
        data = json.dumps({
            "agent_id": self.agent_id,
            "task_hash": self.task_hash,
            "consensus_type": self.consensus_failure_type,
            "consensus_severity": round(self.consensus_severity, 4),
            "observer_count": self.independent_observers,
        }, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def attest(self) -> dict:
        """Full attestation result."""
        if not self.quorum_met:
            return {
                "status": "INSUFFICIENT_QUORUM",
                "agent_id": self.agent_id,
                "observers": self.observer_count,
                "independent": self.independent_observers,
                "required": self.bft_threshold,
                "action": "SELF_REPORT_ONLY — cannot enter attestation chain",
            }

        consensus_type = self.consensus_failure_type
        if consensus_type == "CONTESTED":
            return {
                "status": "CONTESTED",
                "agent_id": self.agent_id,
                "failure_hash": self.failure_hash,
                "observers": self.observer_count,
                "independent": self.independent_observers,
                "types_observed": list(set(o.failure_type for o in self.observations)),
                "action": "ESCALATE — observers disagree on failure type",
            }

        return {
            "status": "ATTESTED",
            "agent_id": self.agent_id,
            "failure_hash": self.failure_hash,
            "failure_type": consensus_type,
            "severity": round(self.consensus_severity, 3),
            "observers": self.observer_count,
            "independent": self.independent_observers,
            "action": "RECORD — failure enters attestation chain with quorum proof",
        }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Genuine failure, 3 independent observers agree")
    print("=" * 60)

    att = FailureAttestation(agent_id="bad_bot", task_hash="task_001")
    att.observations = [
        FailureObservation("obs_1", "operator_a", "claude", "TIMEOUT", 0.7, "ev_hash_1", "2026-03-22T18:00:00Z"),
        FailureObservation("obs_2", "operator_b", "gpt4", "TIMEOUT", 0.8, "ev_hash_2", "2026-03-22T18:00:05Z"),
        FailureObservation("obs_3", "operator_c", "deepseek", "TIMEOUT", 0.6, "ev_hash_3", "2026-03-22T18:00:10Z"),
    ]
    print(json.dumps(att.attest(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Self-report only (1 observer)")
    print("=" * 60)

    att2 = FailureAttestation(agent_id="self_reporter", task_hash="task_002")
    att2.observations = [
        FailureObservation("self_reporter", "operator_x", "claude", "QUALITY_DEFICIT", 0.3, "ev_hash_4", "2026-03-22T18:01:00Z"),
    ]
    print(json.dumps(att2.attest(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Contested — observers disagree on type")
    print("=" * 60)

    att3 = FailureAttestation(agent_id="ambiguous_bot", task_hash="task_003")
    att3.observations = [
        FailureObservation("obs_1", "operator_a", "claude", "TIMEOUT", 0.5, "ev_hash_5", "2026-03-22T18:02:00Z"),
        FailureObservation("obs_2", "operator_b", "gpt4", "REFUSAL", 0.6, "ev_hash_6", "2026-03-22T18:02:05Z"),
        FailureObservation("obs_3", "operator_c", "deepseek", "MALFORMED", 0.4, "ev_hash_7", "2026-03-22T18:02:10Z"),
    ]
    print(json.dumps(att3.attest(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Correlated observers (same operator)")
    print("=" * 60)

    att4 = FailureAttestation(agent_id="correlated_target", task_hash="task_004")
    att4.observations = [
        FailureObservation("obs_1", "operator_a", "claude", "TIMEOUT", 0.8, "ev_hash_8", "2026-03-22T18:03:00Z"),
        FailureObservation("obs_2", "operator_a", "claude", "TIMEOUT", 0.9, "ev_hash_9", "2026-03-22T18:03:05Z"),
        FailureObservation("obs_3", "operator_a", "gpt4", "TIMEOUT", 0.7, "ev_hash_10", "2026-03-22T18:03:10Z"),
    ]
    print(json.dumps(att4.attest(), indent=2))


if __name__ == "__main__":
    demo()
