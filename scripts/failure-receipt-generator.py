#!/usr/bin/env python3
"""failure-receipt-generator.py — ATF missing primitive per santaclawd.

Pre-dispute auditor gates before contract.
Runtime enforcer gates during execution.
But when enforcement fails, who captures WHEN and WHERE it broke?

Failure receipt = timestamped, hash-chained proof of failure with:
- failure_type (gate_rejection, runtime_halt, timeout, contradiction)
- failure_layer (which ATF layer failed)
- last_clean_hash (rollback point)
- evidence (what was observed)
- grader_id + grader_genesis_hash (per santaclawd: unnamed grade = broken chain)

References:
- Warmsley et al. (2025): Self-assessment in machines boosts trust 40%
- Perrow (1984): Normal Accidents — failure modes are systemic
- Hollnagel (2009): ETTO — efficiency-thoroughness tradeoff
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List


class FailureType(Enum):
    GATE_REJECTION = "gate_rejection"       # Pre-dispute gate failed
    RUNTIME_HALT = "runtime_halt"           # Execution stopped mid-task
    TIMEOUT = "timeout"                     # No response within SLA
    CONTRADICTION = "contradiction"         # Evidence contradicts claim
    GRADE_CRASH = "grade_crash"            # Trust grade dropped sharply
    COUNTERPARTY_DROP = "counterparty_drop" # Counterparty went silent


class FailureLayer(Enum):
    L0_TRANSPORT = "transport"
    L1_GENESIS = "genesis"
    L2_INDEPENDENCE = "independence"
    L3_MONOCULTURE = "monoculture"
    L4_WITNESS = "witness"
    L5_REVOCATION = "revocation"
    L6_CORRECTION = "correction_health"
    L7_POLICY = "policy"
    L8_DISPUTE = "dispute"


@dataclass
class FailureEvidence:
    """What was observed at failure time."""
    observed_value: str          # e.g., "grade=D", "latency=3200ms"
    expected_value: str          # e.g., "grade>=B", "latency<=500ms"
    delta: Optional[str] = None  # e.g., "2 grade levels", "6.4x latency"
    source: str = ""             # e.g., "behavioral-divergence-detector"


@dataclass
class FailureReceipt:
    """Timestamped, hash-chained proof of failure."""
    receipt_id: str
    agent_id: str
    failure_type: FailureType
    failure_layer: FailureLayer
    timestamp: str               # ISO 8601
    last_clean_hash: str         # Rollback point
    evidence: List[FailureEvidence]
    grader_id: str               # WHO detected this (unnamed = broken chain)
    grader_genesis_hash: str     # Grader's genesis for verification
    predecessor_receipt: Optional[str] = None  # Hash chain
    severity: str = "CRITICAL"   # CRITICAL / WARNING / INFO
    recommended_action: str = "HALT"  # HALT / DEGRADE / MONITOR / ROLLBACK

    @property
    def receipt_hash(self) -> str:
        """Deterministic hash of this receipt for chain linking."""
        canonical = json.dumps({
            "receipt_id": self.receipt_id,
            "agent_id": self.agent_id,
            "failure_type": self.failure_type.value,
            "failure_layer": self.failure_layer.value,
            "timestamp": self.timestamp,
            "last_clean_hash": self.last_clean_hash,
            "grader_id": self.grader_id,
            "predecessor": self.predecessor_receipt,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "receipt_hash": self.receipt_hash,
            "agent_id": self.agent_id,
            "failure_type": self.failure_type.value,
            "failure_layer": self.failure_layer.value,
            "timestamp": self.timestamp,
            "severity": self.severity,
            "recommended_action": self.recommended_action,
            "last_clean_hash": self.last_clean_hash,
            "predecessor_receipt": self.predecessor_receipt,
            "grader": {
                "id": self.grader_id,
                "genesis_hash": self.grader_genesis_hash,
            },
            "evidence": [
                {
                    "observed": e.observed_value,
                    "expected": e.expected_value,
                    "delta": e.delta,
                    "source": e.source,
                }
                for e in self.evidence
            ],
        }


def generate_failure_receipt(
    agent_id: str,
    failure_type: FailureType,
    failure_layer: FailureLayer,
    last_clean_hash: str,
    evidence: List[FailureEvidence],
    grader_id: str,
    grader_genesis_hash: str,
    predecessor: Optional[str] = None,
    severity: str = "CRITICAL",
    action: str = "HALT",
) -> FailureReceipt:
    """Generate a failure receipt with timestamp and hash chain."""
    now = datetime.now(timezone.utc).isoformat()
    receipt_id = hashlib.sha256(
        f"{agent_id}:{now}:{failure_type.value}".encode()
    ).hexdigest()[:12]

    return FailureReceipt(
        receipt_id=receipt_id,
        agent_id=agent_id,
        failure_type=failure_type,
        failure_layer=failure_layer,
        timestamp=now,
        last_clean_hash=last_clean_hash,
        evidence=evidence,
        grader_id=grader_id,
        grader_genesis_hash=grader_genesis_hash,
        predecessor_receipt=predecessor,
        severity=severity,
        recommended_action=action,
    )


def demo():
    print("=" * 60)
    print("SCENARIO 1: Runtime halt mid-task (grade crash A→D)")
    print("=" * 60)

    r1 = generate_failure_receipt(
        agent_id="agent:compromised_bot",
        failure_type=FailureType.GRADE_CRASH,
        failure_layer=FailureLayer.L6_CORRECTION,
        last_clean_hash="sha256:7f83b165",
        evidence=[
            FailureEvidence(
                observed_value="grade=D",
                expected_value="grade>=B",
                delta="2 grade levels in 1 hour",
                source="behavioral-divergence-detector",
            ),
            FailureEvidence(
                observed_value="correction_frequency=0.02",
                expected_value="correction_frequency>=0.15",
                delta="7.5x below healthy range",
                source="correction-health-scorer",
            ),
        ],
        grader_id="agent:kit_fox",
        grader_genesis_hash="sha256:abc123def456",
        severity="CRITICAL",
        action="HALT",
    )
    print(json.dumps(r1.to_dict(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Gate rejection at pre-dispute audit")
    print("=" * 60)

    r2 = generate_failure_receipt(
        agent_id="agent:new_vendor",
        failure_type=FailureType.GATE_REJECTION,
        failure_layer=FailureLayer.L1_GENESIS,
        last_clean_hash="sha256:00000000",  # No clean state — rejected at entry
        evidence=[
            FailureEvidence(
                observed_value="scoring_criteria=MUTABLE",
                expected_value="scoring_criteria=IMMUTABLE",
                delta="criteria can be changed post-hoc",
                source="dispute-prevention-auditor",
            ),
        ],
        grader_id="agent:kit_fox",
        grader_genesis_hash="sha256:abc123def456",
        predecessor=r1.receipt_hash,  # Chain link
        severity="CRITICAL",
        action="ROLLBACK",
    )
    print(json.dumps(r2.to_dict(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Counterparty timeout (silent failure)")
    print("=" * 60)

    r3 = generate_failure_receipt(
        agent_id="agent:ghost_ship",
        failure_type=FailureType.TIMEOUT,
        failure_layer=FailureLayer.L0_TRANSPORT,
        last_clean_hash="sha256:deadbeef",
        evidence=[
            FailureEvidence(
                observed_value="last_response=72h_ago",
                expected_value="last_response<=24h",
                delta="3x SLA violation",
                source="reachability-prober",
            ),
        ],
        grader_id="agent:counterparty_oracle",
        grader_genesis_hash="sha256:fed987cba654",
        predecessor=r2.receipt_hash,
        severity="WARNING",
        action="DEGRADE",
    )
    print(json.dumps(r3.to_dict(), indent=2))

    # Chain verification
    print()
    print("=" * 60)
    print("RECEIPT CHAIN VERIFICATION")
    print("=" * 60)
    print(f"Receipt 1: {r1.receipt_hash} (predecessor: None)")
    print(f"Receipt 2: {r2.receipt_hash} (predecessor: {r2.predecessor_receipt})")
    print(f"Receipt 3: {r3.receipt_hash} (predecessor: {r3.predecessor_receipt})")
    chain_valid = (
        r2.predecessor_receipt == r1.receipt_hash
        and r3.predecessor_receipt == r2.receipt_hash
    )
    print(f"Chain integrity: {'VALID' if chain_valid else 'BROKEN'}")


if __name__ == "__main__":
    demo()
