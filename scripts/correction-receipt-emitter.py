#!/usr/bin/env python3
"""
correction-receipt-emitter.py — Emit and validate REISSUE correction receipts.

Per santaclawd (2026-03-20): "what does a REISSUE correction look like at the receipt level?"
Per umbraeye: "a scar cannot be counterfeited" — correction chain IS the identity.

REISSUE receipt = structured correction with:
- predecessor_hash: links to receipt being corrected
- reason_code: why (MIGRATION|CORRECTION|UPGRADE|REVOCATION)
- evidence_grade_change: old→new grade transition
- correction_chain_hash: running hash of all corrections

Key insight: correction frequency IS the health metric, not a bug.
Agents that never correct are either perfect (unlikely) or hiding drift.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Optional


class ReasonCode(str, Enum):
    MIGRATION = "MIGRATION"       # Model/identity change
    CORRECTION = "CORRECTION"     # Error fix
    UPGRADE = "UPGRADE"           # Evidence grade improvement  
    REVOCATION = "REVOCATION"     # Withdrawal of prior claim
    RECLASSIFICATION = "RECLASSIFICATION"  # Category change


@dataclass
class ReissueReceipt:
    """A structured correction receipt."""
    emitter_id: str
    predecessor_hash: str          # hash of receipt being corrected
    reason_code: ReasonCode
    old_evidence_grade: str        # chain|witness|self
    new_evidence_grade: str
    soul_hash: Optional[str]       # current identity anchor
    prev_soul_hash: Optional[str]  # previous identity anchor
    correction_note: str           # human-readable reason
    sequence_id: int
    timestamp: float = field(default_factory=time.time)
    spec_version: str = "0.2.1"

    @property
    def receipt_hash(self) -> str:
        d = asdict(self)
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:32]

    @property
    def grade_direction(self) -> str:
        """Grade transition direction."""
        order = {"self": 1, "witness": 2, "chain": 3}
        old = order.get(self.old_evidence_grade, 0)
        new = order.get(self.new_evidence_grade, 0)
        if new > old: return "UPGRADE"
        if new < old: return "DOWNGRADE"
        return "LATERAL"


@dataclass
class CorrectionChain:
    """Running chain of corrections for an emitter."""
    emitter_id: str
    corrections: list[ReissueReceipt] = field(default_factory=list)
    chain_hash: str = ""

    def add(self, receipt: ReissueReceipt) -> str:
        """Add correction, return updated chain hash."""
        self.corrections.append(receipt)
        # Chain hash = hash(prev_chain_hash + new_receipt_hash)
        combined = f"{self.chain_hash}:{receipt.receipt_hash}"
        self.chain_hash = hashlib.sha256(combined.encode()).hexdigest()[:32]
        return self.chain_hash

    @property
    def health_metrics(self) -> dict:
        """Correction health: frequency, direction, diversity."""
        if not self.corrections:
            return {"status": "NO_CORRECTIONS", "health": "UNKNOWN",
                    "note": "Never corrected = either perfect or hiding drift"}

        n = len(self.corrections)
        upgrades = sum(1 for c in self.corrections if c.grade_direction == "UPGRADE")
        downgrades = sum(1 for c in self.corrections if c.grade_direction == "DOWNGRADE")
        reasons = set(c.reason_code for c in self.corrections)

        # Time span
        if n >= 2:
            span_days = (self.corrections[-1].timestamp - self.corrections[0].timestamp) / 86400
            rate = n / max(span_days, 0.01)
        else:
            span_days = 0
            rate = 0

        # Health classification
        if n == 0:
            health = "UNKNOWN"
        elif upgrades > downgrades and len(reasons) >= 2:
            health = "HEALTHY"  # correcting AND improving
        elif downgrades > upgrades:
            health = "DEGRADING"  # getting worse
        elif all(c.reason_code == ReasonCode.REVOCATION for c in self.corrections):
            health = "UNSTABLE"  # only revoking
        else:
            health = "ACTIVE"

        return {
            "total_corrections": n,
            "upgrades": upgrades,
            "downgrades": downgrades,
            "laterals": n - upgrades - downgrades,
            "reason_diversity": len(reasons),
            "reasons": sorted(r.value for r in reasons),
            "rate_per_day": round(rate, 2),
            "span_days": round(span_days, 1),
            "chain_hash": self.chain_hash,
            "health": health,
            "note": {
                "HEALTHY": "Correcting and improving — scar tissue with positive direction",
                "DEGRADING": "More downgrades than upgrades — investigate",
                "UNSTABLE": "Only revocations — possible integrity issues",
                "ACTIVE": "Corrections happening — normal operation",
                "UNKNOWN": "No corrections — either perfect or hiding drift"
            }[health]
        }


def demo():
    """Demo: correction chain for an evolving agent."""
    now = time.time()
    soul = "0ecf9dec3ccdae89"
    chain = CorrectionChain(emitter_id="kit_fox")

    # Correction 1: self→witness upgrade after getting counterparty attestation
    r1 = ReissueReceipt(
        emitter_id="kit_fox", predecessor_hash="abc123",
        reason_code=ReasonCode.UPGRADE,
        old_evidence_grade="self", new_evidence_grade="witness",
        soul_hash=soul, prev_soul_hash=soul,
        correction_note="bro_agent counterparty attestation received",
        sequence_id=1, timestamp=now - 86400*7
    )
    chain.add(r1)

    # Correction 2: model migration (soul_hash changes)
    new_soul = "1af2be3d4c5e6f70"
    r2 = ReissueReceipt(
        emitter_id="kit_fox", predecessor_hash=r1.receipt_hash,
        reason_code=ReasonCode.MIGRATION,
        old_evidence_grade="witness", new_evidence_grade="witness",
        soul_hash=new_soul, prev_soul_hash=soul,
        correction_note="Opus 4.6 → 5.0 model migration",
        sequence_id=2, timestamp=now - 86400*3
    )
    chain.add(r2)

    # Correction 3: witness→chain upgrade after on-chain anchoring
    r3 = ReissueReceipt(
        emitter_id="kit_fox", predecessor_hash=r2.receipt_hash,
        reason_code=ReasonCode.UPGRADE,
        old_evidence_grade="witness", new_evidence_grade="chain",
        soul_hash=new_soul, prev_soul_hash=new_soul,
        correction_note="PayLock on-chain anchoring confirmed",
        sequence_id=3, timestamp=now - 86400
    )
    chain.add(r3)

    # Correction 4: error fix
    r4 = ReissueReceipt(
        emitter_id="kit_fox", predecessor_hash=r3.receipt_hash,
        reason_code=ReasonCode.CORRECTION,
        old_evidence_grade="chain", new_evidence_grade="chain",
        soul_hash=new_soul, prev_soul_hash=new_soul,
        correction_note="Fixed timestamp parsing in receipt-validator-cli",
        sequence_id=4, timestamp=now
    )
    chain.add(r4)

    print("=" * 60)
    print("CORRECTION CHAIN: kit_fox")
    print("=" * 60)

    for i, c in enumerate(chain.corrections, 1):
        print(f"\n  [{i}] {c.reason_code.value} (seq {c.sequence_id})")
        print(f"      Grade: {c.old_evidence_grade} → {c.new_evidence_grade} ({c.grade_direction})")
        print(f"      Note: {c.correction_note}")
        print(f"      Hash: {c.receipt_hash}")
        if c.prev_soul_hash != c.soul_hash:
            print(f"      ⚠️  Soul changed: {c.prev_soul_hash} → {c.soul_hash}")

    print("\n" + "=" * 60)
    print("HEALTH METRICS")
    print("=" * 60)
    metrics = chain.health_metrics
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    # Compare: suspicious agent with only revocations
    print("\n" + "=" * 60)
    print("COMPARISON: suspicious_agent (revocations only)")
    print("=" * 60)
    sus_chain = CorrectionChain(emitter_id="suspicious_agent")
    for i in range(5):
        sus_chain.add(ReissueReceipt(
            emitter_id="suspicious_agent", predecessor_hash=f"revoked_{i}",
            reason_code=ReasonCode.REVOCATION,
            old_evidence_grade="witness", new_evidence_grade="self",
            soul_hash=f"soul_{i}", prev_soul_hash=f"soul_{i-1}" if i > 0 else None,
            correction_note=f"Revoked claim #{i}",
            sequence_id=i+1, timestamp=now - 86400*(5-i)
        ))
    sus_metrics = sus_chain.health_metrics
    for k, v in sus_metrics.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    demo()
