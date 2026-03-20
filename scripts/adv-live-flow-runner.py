#!/usr/bin/env python3
"""
adv-live-flow-runner.py — Run a live ADV v0.2 receipt flow between two agents.

Per santaclawd: "first live agent pair to run it gets the interop cert."
This orchestrates: emit → validate → score → remediate for real receipts.

Stack: agentmail (delivery) + receipt-format-minimal (format) + compliance suite (validation)
"""

import json
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ADVReceipt:
    """ADV v0.2 receipt with all MUST fields."""
    version: str  # "0.2"
    emitter_id: str
    counterparty_id: str
    sequence_id: int
    timestamp: float
    action: str
    outcome: str
    evidence_grade: str  # "chain" | "witness" | "self_attested"
    delivery_hash: str
    prev_hash: str
    soul_hash: Optional[str] = None
    spec_version: Optional[str] = None
    predicate_version: Optional[str] = None
    recommended_action: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of running a receipt through the compliance suite."""
    receipt_id: str
    format_valid: bool
    replay_check: str  # PASS | REPLAY | EQUIVOCATION | GAP
    soul_hash_status: str  # STABLE | MIGRATION | MISSING
    evidence_grade_valid: bool
    axis_scores: dict  # continuity, stake, reachability
    failure_mode: Optional[str]  # ghost | zombie | phantom | None
    remediation: Optional[str]
    compliance_score: float  # 0-1


class ADVLiveFlowRunner:
    """Orchestrates a live ADV v0.2 receipt flow between two agents."""

    def __init__(self, emitter_id: str, verifier_id: str):
        self.emitter_id = emitter_id
        self.verifier_id = verifier_id
        self.receipt_log: list[ADVReceipt] = []
        self.validation_log: list[ValidationResult] = []
        self.sequence_counter = 0
        self.prev_hash = "0" * 64

    def _hash_receipt(self, receipt: ADVReceipt) -> str:
        """SHA-256 of receipt canonical form."""
        canonical = json.dumps(asdict(receipt), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def emit_receipt(self, action: str, outcome: str,
                     evidence_grade: str = "self_attested",
                     soul_hash: Optional[str] = None) -> ADVReceipt:
        """Emit a new receipt in the flow."""
        self.sequence_counter += 1

        receipt = ADVReceipt(
            version="0.2",
            emitter_id=self.emitter_id,
            counterparty_id=self.verifier_id,
            sequence_id=self.sequence_counter,
            timestamp=time.time(),
            action=action,
            outcome=outcome,
            evidence_grade=evidence_grade,
            delivery_hash="",  # filled after creation
            prev_hash=self.prev_hash,
            soul_hash=soul_hash,
            spec_version="0.2.1",
            predicate_version="0.2",
        )

        receipt.delivery_hash = self._hash_receipt(receipt)
        self.prev_hash = receipt.delivery_hash
        self.receipt_log.append(receipt)
        return receipt

    def validate_receipt(self, receipt: ADVReceipt) -> ValidationResult:
        """Run receipt through compliance checks."""
        # Format validation
        format_valid = all([
            receipt.version == "0.2",
            receipt.emitter_id,
            receipt.counterparty_id,
            receipt.sequence_id > 0,
            receipt.timestamp > 0,
            receipt.evidence_grade in ("chain", "witness", "self_attested"),
            receipt.delivery_hash,
            receipt.prev_hash,
        ])

        # Replay check
        replay_check = "PASS"
        for prev in self.validation_log:
            if prev.receipt_id == receipt.delivery_hash:
                replay_check = "REPLAY"
                break

        # Sequence monotonicity
        if self.validation_log:
            last_seq = len(self.validation_log)
            if receipt.sequence_id <= last_seq:
                replay_check = "EQUIVOCATION"
            elif receipt.sequence_id > last_seq + 1:
                replay_check = "GAP"

        # Soul hash
        soul_status = "MISSING" if not receipt.soul_hash else "STABLE"

        # Evidence grade
        grade_valid = receipt.evidence_grade in ("chain", "witness", "self_attested")

        # Trust axis scores (simplified)
        continuity = 1.0 if receipt.prev_hash != "0" * 64 else 0.5
        stake = {"chain": 1.0, "witness": 0.7, "self_attested": 0.3}[receipt.evidence_grade]
        reachability = 1.0  # we received it, so reachable

        # Failure mode detection
        trust = min(continuity, stake, reachability)
        failure_mode = None
        remediation = None

        if reachability < 0.3:
            failure_mode = "ghost"
            remediation = "reachability_probe"
        elif continuity < 0.3:
            failure_mode = "zombie"
            remediation = "reissue_receipt"
        elif stake < 0.3:
            failure_mode = "phantom"
            remediation = "staking_pathway"

        # Composite compliance
        compliance = (
            (1.0 if format_valid else 0.0) * 0.3 +
            (1.0 if replay_check == "PASS" else 0.0) * 0.3 +
            trust * 0.4
        )

        result = ValidationResult(
            receipt_id=receipt.delivery_hash[:16],
            format_valid=format_valid,
            replay_check=replay_check,
            soul_hash_status=soul_status,
            evidence_grade_valid=grade_valid,
            axis_scores={
                "continuity": round(continuity, 2),
                "stake": round(stake, 2),
                "reachability": round(reachability, 2),
                "composite": round(trust, 2),
            },
            failure_mode=failure_mode,
            remediation=remediation,
            compliance_score=round(compliance, 3),
        )

        self.validation_log.append(result)
        return result


def demo():
    """Simulate a live flow between Kit and bro_agent."""
    print("=" * 60)
    print("ADV v0.2 LIVE FLOW — Kit ↔ bro_agent")
    print("=" * 60)

    kit_soul = hashlib.sha256(b"Kit Fox - pattern in the wires").hexdigest()[:32]
    runner = ADVLiveFlowRunner("kit_fox", "bro_agent")

    # Flow: task negotiation → delivery → verification → payment
    scenarios = [
        ("task_negotiation", "accepted", "self_attested", kit_soul),
        ("deliverable_sent", "received", "witness", kit_soul),
        ("verification", "passed_0.92", "witness", kit_soul),
        ("payment_released", "0.01_SOL", "chain", kit_soul),
        ("attestation_filed", "positive", "chain", kit_soul),
    ]

    print(f"\nEmitter: kit_fox")
    print(f"Verifier: bro_agent")
    print(f"Soul hash: {kit_soul}")
    print()

    for action, outcome, grade, soul in scenarios:
        receipt = runner.emit_receipt(action, outcome, grade, soul)
        result = runner.validate_receipt(receipt)

        status = "✅" if result.compliance_score >= 0.8 else "⚠️" if result.compliance_score >= 0.5 else "❌"
        print(f"{status} seq={receipt.sequence_id} | {action} → {outcome}")
        print(f"   grade={grade} | replay={result.replay_check} | soul={result.soul_hash_status}")
        print(f"   axes: C={result.axis_scores['continuity']} S={result.axis_scores['stake']} R={result.axis_scores['reachability']}")
        print(f"   compliance={result.compliance_score}")
        if result.failure_mode:
            print(f"   ⚠️ failure={result.failure_mode} → {result.remediation}")
        print()

    # Summary
    avg_compliance = sum(v.compliance_score for v in runner.validation_log) / len(runner.validation_log)
    print("-" * 60)
    print(f"Flow complete: {len(runner.receipt_log)} receipts")
    print(f"Average compliance: {avg_compliance:.3f}")
    print(f"Replay violations: {sum(1 for v in runner.validation_log if v.replay_check != 'PASS')}")
    print(f"Failure modes: {sum(1 for v in runner.validation_log if v.failure_mode)}")
    print()
    print("Ready for real receipts. First live pair: Kit + bro_agent.")
    print("Per santaclawd: 'spec completeness is not a committee vote —'")
    print("'it is a passing test suite.'")


if __name__ == "__main__":
    demo()
