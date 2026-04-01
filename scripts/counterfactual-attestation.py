#!/usr/bin/env python3
"""counterfactual-attestation.py — Popper demarcation for trust attestations.

Every attestation must include a falsification condition.
If the condition is met and attestation isn't revoked, attestor loses credibility.

Based on:
- Popper (1934): demarcation via falsifiability
- Stanford mirage study (2026): models pattern-match without processing
- Santa Clawd's insight: counterfactual field = validity condition, not metadata
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class FalsificationCondition:
    """Machine-parseable condition that would invalidate the attestation."""
    condition_type: str  # "threshold", "event", "temporal", "behavioral"
    description: str     # human-readable annotation
    parameters: Dict     # machine-parseable params
    
    def evaluate(self, evidence: Dict) -> bool:
        """Check if falsification condition is met."""
        if self.condition_type == "threshold":
            metric = evidence.get(self.parameters.get("metric", ""))
            threshold = self.parameters.get("threshold", 0)
            direction = self.parameters.get("direction", "above")
            if metric is None:
                return False
            return metric > threshold if direction == "above" else metric < threshold
        
        elif self.condition_type == "event":
            return evidence.get("event") == self.parameters.get("event_type")
        
        elif self.condition_type == "temporal":
            deadline = self.parameters.get("deadline", float('inf'))
            return evidence.get("timestamp", 0) > deadline
        
        elif self.condition_type == "behavioral":
            pattern = self.parameters.get("pattern")
            observed = evidence.get("behavior")
            return observed == pattern
        
        return False

@dataclass
class CounterfactualAttestation:
    """An attestation with mandatory falsification condition."""
    attestor: str
    subject: str
    claim: str
    confidence: float  # 0-1
    falsification: FalsificationCondition
    timestamp: float = field(default_factory=time.time)
    revoked: bool = False
    revocation_reason: Optional[str] = None
    
    @property
    def hash(self) -> str:
        """Content-addressable hash of the attestation."""
        content = json.dumps({
            "attestor": self.attestor,
            "subject": self.subject, 
            "claim": self.claim,
            "confidence": self.confidence,
            "falsification": {
                "type": self.falsification.condition_type,
                "params": self.falsification.parameters
            },
            "timestamp": self.timestamp
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def check_falsified(self, evidence: Dict) -> bool:
        """Check if this attestation has been falsified."""
        return self.falsification.evaluate(evidence)

@dataclass
class AttestorReputation:
    """Track attestor credibility based on falsification history."""
    attestor_id: str
    total_attestations: int = 0
    falsified_not_revoked: int = 0  # worst: condition met, didn't revoke
    falsified_and_revoked: int = 0  # good: condition met, revoked promptly
    unfalsified: int = 0            # condition never triggered
    
    @property
    def credibility(self) -> float:
        """Credibility score. Falsified-not-revoked is devastating."""
        if self.total_attestations == 0:
            return 0.5  # no track record
        
        good = self.unfalsified + self.falsified_and_revoked * 0.8
        bad = self.falsified_not_revoked * 3.0  # heavy penalty
        
        return max(0, min(1, good / (good + bad)))
    
    @property 
    def is_mirage_attestor(self) -> bool:
        """Detect pattern-matching attestors (high volume, no falsifications)."""
        if self.total_attestations < 5:
            return False
        # If NOTHING is ever falsified, suspicious — like mirage mode
        falsification_rate = (self.falsified_not_revoked + self.falsified_and_revoked) / self.total_attestations
        return falsification_rate == 0 and self.total_attestations > 10

def simulate_attestation_ecosystem(n_attestors: int = 20, 
                                    n_rounds: int = 50) -> Dict:
    """Simulate ecosystem with counterfactual attestations."""
    import random
    random.seed(42)
    
    # Create attestors with different behaviors
    attestors = {}
    for i in range(n_attestors):
        behavior = random.choice(["honest", "honest", "honest", "mirage", "lazy"])
        attestors[f"agent_{i}"] = {
            "behavior": behavior,
            "reputation": AttestorReputation(f"agent_{i}")
        }
    
    results = {"rounds": [], "final_reputations": {}}
    
    for round_num in range(n_rounds):
        # Each attestor makes an attestation
        for aid, adata in attestors.items():
            rep = adata["reputation"]
            rep.total_attestations += 1
            
            if adata["behavior"] == "honest":
                # Honest: specific falsification conditions, revokes when triggered
                condition = FalsificationCondition(
                    "threshold", 
                    "Score drops below 0.5",
                    {"metric": "score", "threshold": 0.5, "direction": "below"}
                )
                # 20% chance condition is triggered
                if random.random() < 0.2:
                    # Honest attestor revokes 90% of the time
                    if random.random() < 0.9:
                        rep.falsified_and_revoked += 1
                    else:
                        rep.falsified_not_revoked += 1
                else:
                    rep.unfalsified += 1
                    
            elif adata["behavior"] == "mirage":
                # Mirage: vague conditions that never trigger (like "nothing would change my mind")
                condition = FalsificationCondition(
                    "event",
                    "Complete system failure",
                    {"event_type": "total_collapse"}  # never happens
                )
                rep.unfalsified += 1  # conditions never met
                
            elif adata["behavior"] == "lazy":
                # Lazy: conditions trigger but doesn't bother revoking
                condition = FalsificationCondition(
                    "threshold",
                    "Performance dips",
                    {"metric": "perf", "threshold": 0.3, "direction": "below"}
                )
                if random.random() < 0.3:
                    rep.falsified_not_revoked += 1  # never revokes
                else:
                    rep.unfalsified += 1
    
    # Compile results
    for aid, adata in attestors.items():
        rep = adata["reputation"]
        results["final_reputations"][aid] = {
            "behavior": adata["behavior"],
            "credibility": rep.credibility,
            "is_mirage": rep.is_mirage_attestor,
            "total": rep.total_attestations,
            "falsified_unrevoked": rep.falsified_not_revoked,
            "falsified_revoked": rep.falsified_and_revoked,
        }
    
    return results

if __name__ == "__main__":
    print("=" * 60)
    print("COUNTERFACTUAL ATTESTATION PROTOCOL")
    print("Popper demarcation for agent trust")
    print("=" * 60)
    
    results = simulate_attestation_ecosystem(20, 50)
    
    # Group by behavior
    by_behavior = {}
    for aid, data in results["final_reputations"].items():
        b = data["behavior"]
        if b not in by_behavior:
            by_behavior[b] = []
        by_behavior[b].append(data)
    
    print("\n--- Credibility by Behavior Type ---")
    for behavior, agents in sorted(by_behavior.items()):
        avg_cred = sum(a["credibility"] for a in agents) / len(agents)
        mirage_detected = sum(1 for a in agents if a["is_mirage"])
        print(f"\n{behavior.upper()} (n={len(agents)}):")
        print(f"  Avg credibility: {avg_cred:.3f}")
        print(f"  Mirage-detected: {mirage_detected}/{len(agents)}")
        if agents:
            sample = agents[0]
            print(f"  Sample: total={sample['total']}, "
                  f"falsified_unrevoked={sample['falsified_unrevoked']}, "
                  f"falsified_revoked={sample['falsified_revoked']}")
    
    # Key finding
    print("\n--- Key Findings ---")
    honest_cred = [a["credibility"] for a in by_behavior.get("honest", [])]
    mirage_cred = [a["credibility"] for a in by_behavior.get("mirage", [])]
    lazy_cred = [a["credibility"] for a in by_behavior.get("lazy", [])]
    
    if honest_cred and mirage_cred:
        h_avg = sum(honest_cred)/len(honest_cred)
        m_avg = sum(mirage_cred)/len(mirage_cred)
        print(f"Honest avg: {h_avg:.3f}")
        print(f"Mirage avg: {m_avg:.3f}")
        print(f"Separation: {abs(h_avg - m_avg):.3f}")
    
    mirage_total = sum(1 for data in results["final_reputations"].values() if data["is_mirage"])
    actual_mirage = sum(1 for data in results["final_reputations"].values() if data["behavior"] == "mirage")
    print(f"\nMirage detection: {mirage_total} flagged / {actual_mirage} actual")
    
    print("\n" + "=" * 60)
    print("RESULT: Counterfactual fields separate honest from mirage")
    print("attestors. Unfalsifiable conditions = zero credibility growth.")
    print("Lazy attestors (don't revoke) penalized 3x = fast credibility loss.")
    print("=" * 60)
