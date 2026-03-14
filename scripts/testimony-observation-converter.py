#!/usr/bin/env python3
"""
testimony-observation-converter.py — Models the testimony→observation trust promotion.

Based on Watson & Morgan (Cognition 2025): observed info is ~2x as influential as advisory.
CT logs, Merkle proofs, and multi-party witnessing convert testimony (self-reported)
into observation (independently verifiable).

santaclawd's insight: "the anchor layer is literally just promoting logs from testimony to observation."
"""

from dataclasses import dataclass
from enum import Enum


class EvidenceChannel(Enum):
    TESTIMONY = "testimony"      # Agent self-reports (advisory channel)
    OBSERVATION = "observation"   # Independently verified (spied channel)


@dataclass
class TrustClaim:
    agent_id: str
    claim: str
    channel: EvidenceChannel
    raw_score: float  # 0.0-1.0
    witnesses: int = 1
    has_merkle_proof: bool = False
    has_dkim: bool = False
    in_ct_log: bool = False

    @property
    def effective_score(self) -> float:
        """Watson & Morgan 2025: observation ~2x testimony."""
        multiplier = 2.0 if self.channel == EvidenceChannel.OBSERVATION else 1.0
        return min(1.0, self.raw_score * multiplier)

    @property
    def promotion_eligible(self) -> bool:
        """Can this testimony be promoted to observation?"""
        if self.channel == EvidenceChannel.OBSERVATION:
            return False  # Already observation
        # Need at least 2 of: merkle proof, DKIM, CT log, 3+ witnesses
        criteria = [
            self.has_merkle_proof,
            self.has_dkim,
            self.in_ct_log,
            self.witnesses >= 3,
        ]
        return sum(criteria) >= 2

    def promote(self) -> "TrustClaim":
        """Promote testimony → observation if eligible."""
        if not self.promotion_eligible:
            raise ValueError(f"Not eligible: need 2+ of [merkle, dkim, ct_log, 3+witnesses]")
        return TrustClaim(
            agent_id=self.agent_id,
            claim=self.claim,
            channel=EvidenceChannel.OBSERVATION,
            raw_score=self.raw_score,
            witnesses=self.witnesses,
            has_merkle_proof=self.has_merkle_proof,
            has_dkim=self.has_dkim,
            in_ct_log=self.in_ct_log,
        )


def demo():
    print("=== Testimony → Observation Converter ===")
    print("Watson & Morgan (Cognition 2025): observed ≈ 2× advisory\n")

    scenarios = [
        ("Self-reported liveness", "agent_a", "I am alive", 0.4, 1, False, False, False),
        ("DKIM-signed email", "agent_b", "Work delivered", 0.4, 1, False, True, False),
        ("CT-logged + DKIM cert", "agent_c", "Key rotated", 0.4, 1, False, True, True),
        ("Merkle proof + 3 witnesses", "agent_d", "Attestation valid", 0.4, 3, True, False, False),
        ("Full stack (all anchors)", "agent_e", "Payment settled", 0.4, 5, True, True, True),
    ]

    for name, aid, claim, score, wit, merkle, dkim, ct in scenarios:
        tc = TrustClaim(aid, claim, EvidenceChannel.TESTIMONY, score, wit, merkle, dkim, ct)
        print(f"  {name}")
        print(f"    Channel:    {tc.channel.value}")
        print(f"    Raw score:  {tc.raw_score:.2f}")
        print(f"    Effective:  {tc.effective_score:.2f} (×{tc.effective_score/tc.raw_score:.1f})")
        print(f"    Promotable: {tc.promotion_eligible}")
        if tc.promotion_eligible:
            promoted = tc.promote()
            print(f"    → Promoted:  {promoted.channel.value}, effective={promoted.effective_score:.2f}")
        print()

    # Summary
    print("Key insight: the anchor layer's ONLY job is converting")
    print("testimony (1×) into observation (2×). CT log, Merkle proof,")
    print("DKIM, multi-witness — all different paths to the same promotion.")


if __name__ == "__main__":
    demo()
