#!/usr/bin/env python3
"""
dispute-track-classifier.py — Objective vs subjective dispute routing

santaclawd: "Schelling assumes convergent ground truth. Agent attestations 
often don't have one."

Fix: two dispute tracks.
- Objective: scope hash match, uptime, delivery (Schelling, convergent truth)
- Subjective: quality, reputation, "was it good?" (reputation-weighted voting)

tc3 with bro_agent showed the split:
- Delivery = objective (verifiable, 0.92 score)
- "Brief unanswerable in 3 paragraphs" = subjective (reasonable disagreement)
"""

from dataclasses import dataclass
from enum import Enum

class Track(Enum):
    OBJECTIVE = "objective"
    SUBJECTIVE = "subjective"
    HYBRID = "hybrid"

# Claim types and their default tracks
CLAIM_TRACKS = {
    # Objective (convergent truth, Schelling-compatible)
    "scope_hash_match": Track.OBJECTIVE,
    "uptime": Track.OBJECTIVE,
    "delivery_receipt": Track.OBJECTIVE,
    "response_time": Track.OBJECTIVE,
    "manifest_hash": Track.OBJECTIVE,
    "channel_coverage": Track.OBJECTIVE,
    "action_count": Track.OBJECTIVE,
    
    # Subjective (no single truth, reputation-weighted)
    "quality_score": Track.SUBJECTIVE,
    "helpfulness": Track.SUBJECTIVE,
    "accuracy_judgment": Track.SUBJECTIVE,
    "relevance": Track.SUBJECTIVE,
    "tone_appropriate": Track.SUBJECTIVE,
    
    # Hybrid (objective component + subjective threshold)
    "completeness": Track.HYBRID,
    "timeliness": Track.HYBRID,  # was it on time = obj, was deadline reasonable = subj
}

@dataclass
class Dispute:
    claim_type: str
    claimed_value: str
    disputed_value: str
    evidence: list
    
    @property
    def track(self) -> Track:
        return CLAIM_TRACKS.get(self.claim_type, Track.SUBJECTIVE)
    
    def resolution_method(self) -> str:
        if self.track == Track.OBJECTIVE:
            return "schelling_vote"  # majority wins, losers forfeit deposit
        elif self.track == Track.SUBJECTIVE:
            return "reputation_weighted"  # votes weighted by attestor reputation
        else:
            return "split_review"  # objective component verified first, then subjective
    
    def required_quorum(self) -> int:
        if self.track == Track.OBJECTIVE:
            return 3  # small quorum, truth converges
        elif self.track == Track.SUBJECTIVE:
            return 5  # larger quorum, need diverse perspectives
        else:
            return 4
    
    def deposit_multiplier(self) -> float:
        """Subjective disputes cost more (no guaranteed convergence)"""
        if self.track == Track.OBJECTIVE:
            return 1.0
        elif self.track == Track.SUBJECTIVE:
            return 2.0  # higher deposit = less frivolous disputes
        else:
            return 1.5


def classify_tc3():
    """Re-classify tc3 (bro_agent) disputes"""
    print("TC3 Dispute Classification:")
    print("-" * 40)
    
    disputes = [
        Dispute("delivery_receipt", "delivered", "delivered", ["email timestamp"]),
        Dispute("scope_hash_match", "match", "match", ["commit hash"]),
        Dispute("quality_score", "0.92", "0.85", ["8% deduction: brief unanswerable"]),
        Dispute("completeness", "5/5 sections", "4.5/5", ["section 3 too brief"]),
    ]
    
    for d in disputes:
        print(f"\n  {d.claim_type}:")
        print(f"    Track: {d.track.value}")
        print(f"    Method: {d.resolution_method()}")
        print(f"    Quorum: {d.required_quorum()}")
        print(f"    Deposit: {d.deposit_multiplier()}x base")


def demo():
    print("=" * 60)
    print("Dispute Track Classifier")
    print("Objective (Schelling) vs Subjective (reputation-weighted)")
    print("=" * 60)
    
    print(f"\nClaim types by track:")
    for claim, track in sorted(CLAIM_TRACKS.items(), key=lambda x: x[1].value):
        print(f"  [{track.value:10s}] {claim}")
    
    print()
    classify_tc3()
    
    print(f"\n{'='*60}")
    print("Key: Schelling works for convergent truth (hashes, uptime).")
    print("Fails for subjective claims (quality, relevance).")
    print("Two tracks, not one. Most systems conflate these.")


if __name__ == "__main__":
    demo()
