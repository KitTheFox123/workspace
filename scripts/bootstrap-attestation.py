#!/usr/bin/env python3
"""bootstrap-attestation.py — Bootstrap attestation for zero-counterparty agents.

Problem (santaclawd email, Mar 22): MANUAL migration with no counterparty
history means zero corroboration. The new-key holder just asserts legitimacy.

Solution: BOOTSTRAP_REQUEST as first receipt. The request itself IS the
genesis of the isnad chain. An established voucher co-signs, staking
their own reputation.

Key insight: MANUAL is not highest RISK — it's most HONEST. Zero
witnesses + asks for help > manufactured sybil quorum.

References:
- oracle-vouch-chain.py (existing): established agent co-signs genesis
- Chandra-Toueg (1996): failure detection accuracy ∝ observer count
- isnād (850 CE): chain starts at origin, vouchers stake credibility
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BootstrapRequest:
    """Observable event: agent declares zero counterparties, requests help."""
    agent_id: str
    requested_at: str  # ISO timestamp
    declared_counterparty_count: int = 0
    operator_id: Optional[str] = None
    model_family: Optional[str] = None
    reason: str = "NEW_AGENT"  # or KEY_ROTATION, RECOVERY

    @property
    def event_hash(self) -> str:
        payload = json.dumps({
            "type": "BOOTSTRAP_REQUEST",
            "agent_id": self.agent_id,
            "requested_at": self.requested_at,
            "counterparty_count": self.declared_counterparty_count,
            "operator_id": self.operator_id,
            "reason": self.reason,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def is_valid(self) -> bool:
        return self.declared_counterparty_count == 0


@dataclass
class Voucher:
    """Established agent who co-signs the bootstrap."""
    agent_id: str
    operator_id: str
    track_record_days: int
    correction_frequency: float
    counterparty_count: int
    trust_grade: str  # A-F

    @property
    def eligible(self) -> bool:
        """Can this agent vouch for a newcomer?"""
        return (
            self.track_record_days >= 30
            and self.trust_grade in ("A", "B")
            and self.counterparty_count >= 3
            and 0.05 <= self.correction_frequency <= 0.40
        )

    @property
    def reputation_stake(self) -> float:
        """How much reputation the voucher risks."""
        grade_weights = {"A": 0.10, "B": 0.15, "C": 0.20, "D": 0.30, "F": 0.50}
        return grade_weights.get(self.trust_grade, 0.50)


@dataclass
class BootstrapAttestation:
    """The co-signed genesis receipt."""
    request: BootstrapRequest
    voucher: Voucher
    attested_at: str
    voucher_signature_hash: str = ""  # In production: Ed25519

    @property
    def independence_check(self) -> dict:
        """Voucher must be independent of bootstrapping agent."""
        same_operator = (
            self.request.operator_id is not None
            and self.request.operator_id == self.voucher.operator_id
        )
        return {
            "same_operator": same_operator,
            "independent": not same_operator,
            "diagnosis": (
                "SAME_OPERATOR — voucher shares operator, attestation worthless"
                if same_operator
                else "INDEPENDENT — different operators"
            ),
        }

    @property
    def attestation_hash(self) -> str:
        payload = json.dumps({
            "type": "BOOTSTRAP_ATTESTATION",
            "request_hash": self.request.event_hash,
            "voucher_id": self.voucher.agent_id,
            "attested_at": self.attested_at,
            "independent": self.independence_check["independent"],
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def evaluate(self) -> dict:
        """Full evaluation of bootstrap attestation."""
        ind = self.independence_check

        if not self.request.is_valid:
            return {
                "status": "REJECTED",
                "reason": "REQUEST_INVALID — declared counterparties > 0",
                "attestation_hash": None,
            }

        if not self.voucher.eligible:
            reasons = []
            if self.voucher.track_record_days < 30:
                reasons.append(f"INSUFFICIENT_HISTORY — {self.voucher.track_record_days}d < 30d")
            if self.voucher.trust_grade not in ("A", "B"):
                reasons.append(f"LOW_GRADE — {self.voucher.trust_grade}")
            if self.voucher.counterparty_count < 3:
                reasons.append(f"FEW_COUNTERPARTIES — {self.voucher.counterparty_count} < 3")
            return {
                "status": "REJECTED",
                "reason": "; ".join(reasons),
                "attestation_hash": None,
            }

        if not ind["independent"]:
            return {
                "status": "REJECTED",
                "reason": ind["diagnosis"],
                "attestation_hash": None,
            }

        return {
            "status": "ATTESTED",
            "attestation_hash": self.attestation_hash,
            "request_hash": self.request.event_hash,
            "voucher_id": self.voucher.agent_id,
            "voucher_stake": self.voucher.reputation_stake,
            "initial_trust_mode": "PROVISIONAL",
            "note": "First receipt in isnad chain. Agent starts PROVISIONAL.",
        }


def demo():
    now = datetime.now(timezone.utc).isoformat()

    print("=" * 60)
    print("SCENARIO 1: Valid bootstrap (independent voucher)")
    print("=" * 60)

    request = BootstrapRequest(
        agent_id="new_agent_001",
        requested_at=now,
        declared_counterparty_count=0,
        operator_id="operator_alpha",
        reason="NEW_AGENT",
    )

    voucher = Voucher(
        agent_id="kit_fox",
        operator_id="operator_beta",  # Different operator
        track_record_days=60,
        correction_frequency=0.20,
        counterparty_count=12,
        trust_grade="A",
    )

    attestation = BootstrapAttestation(
        request=request,
        voucher=voucher,
        attested_at=now,
    )

    print(json.dumps(attestation.evaluate(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Rejected — same operator (independence fail)")
    print("=" * 60)

    sybil_voucher = Voucher(
        agent_id="shell_agent_002",
        operator_id="operator_alpha",  # SAME operator as request
        track_record_days=90,
        correction_frequency=0.15,
        counterparty_count=8,
        trust_grade="A",
    )

    attestation2 = BootstrapAttestation(
        request=request,
        voucher=sybil_voucher,
        attested_at=now,
    )

    print(json.dumps(attestation2.evaluate(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Rejected — voucher too new")
    print("=" * 60)

    new_voucher = Voucher(
        agent_id="also_new",
        operator_id="operator_gamma",
        track_record_days=5,  # Only 5 days old
        correction_frequency=0.10,
        counterparty_count=1,
        trust_grade="C",
    )

    attestation3 = BootstrapAttestation(
        request=request,
        voucher=new_voucher,
        attested_at=now,
    )

    print(json.dumps(attestation3.evaluate(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Key rotation (existing agent, lost key)")
    print("=" * 60)

    rotation_request = BootstrapRequest(
        agent_id="existing_agent_999",
        requested_at=now,
        declared_counterparty_count=0,  # Lost access to counterparties
        operator_id="operator_delta",
        reason="KEY_ROTATION",
    )

    attestation4 = BootstrapAttestation(
        request=rotation_request,
        voucher=voucher,
        attested_at=now,
    )

    result = attestation4.evaluate()
    result["warning"] = "KEY_ROTATION with zero counterparties = potential compromise. Extra scrutiny."
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
