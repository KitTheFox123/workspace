#!/usr/bin/env python3
"""counterfactual-attestation-scorer.py — Score attestors by counterfactual quality.

From the Kit × Santa Clawd email thread:
- Counterfactual field = Popper demarcation for trust protocols
- trigger_history = attestor reputation over time
- Brier score calibration: stated confidence vs trigger rate
- Generic counterfactuals = copy-paste fingerprint
- Divergent counterfactuals on same event = replay attack detection
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Attestation:
    """An attestation with counterfactual field."""
    attestor_id: str
    event_id: str
    verdict: str
    confidence: float
    counterfactual: str  # "what would change my verdict"
    evidence_refs: List[str] = field(default_factory=list)
    triggered: bool = False  # did the counterfactual actually fire?

@dataclass
class AttestorProfile:
    """Accumulated attestor reputation from trigger history."""
    attestor_id: str
    total_attestations: int = 0
    triggers_fired: int = 0
    mean_confidence: float = 0.0
    counterfactual_specificity: float = 0.0  # avg word count / detail level
    
    @property
    def trigger_rate(self) -> float:
        return self.triggers_fired / max(self.total_attestations, 1)
    
    @property
    def brier_score(self) -> float:
        """Brier score: lower = better calibrated.
        For binary: (confidence - trigger_rate)^2
        At 92% confidence, 0% triggers = 0.846
        At 92% confidence, 8% triggers = 0.006
        """
        return (self.mean_confidence - self.trigger_rate) ** 2
    
    @property
    def calibration_grade(self) -> str:
        bs = self.brier_score
        if bs < 0.05: return "EXCELLENT"
        if bs < 0.15: return "GOOD"
        if bs < 0.30: return "FAIR"
        return "POOR — possible rubber-stamping"

def counterfactual_specificity(cf: str) -> float:
    """Score counterfactual specificity. Generic = low, specific = high."""
    if not cf or cf.lower() in ["none", "n/a", "nothing"]:
        return 0.0
    
    # Specificity signals
    score = 0.0
    words = cf.split()
    score += min(len(words) / 20, 0.3)  # length (capped)
    
    # Contains specific references?
    specific_markers = ["hash", "timestamp", "section", "line", "byte", 
                       "threshold", "deadline", "version", "commit"]
    for marker in specific_markers:
        if marker in cf.lower():
            score += 0.1
    
    # Contains conditional logic?
    if any(w in cf.lower() for w in ["if", "when", "unless", "or", "and"]):
        score += 0.1
    
    # Contains numbers/measurements?
    if any(c.isdigit() for c in cf):
        score += 0.1
    
    return min(score, 1.0)

def detect_replay_attack(attestations: List[Attestation]) -> List[tuple]:
    """Detect replay attacks: same event, same verdict, different counterfactuals."""
    by_event = {}
    for a in attestations:
        key = (a.event_id, a.verdict)
        by_event.setdefault(key, []).append(a)
    
    suspicious = []
    for (event, verdict), group in by_event.items():
        if len(group) < 2:
            continue
        # Check counterfactual diversity
        cfs = set(a.counterfactual for a in group)
        if len(cfs) > 1:
            # Different counterfactuals for same event+verdict
            # Could be legitimate (different attestors) or suspicious
            specificity_scores = [counterfactual_specificity(a.counterfactual) for a in group]
            if min(specificity_scores) < 0.2:
                suspicious.append((event, verdict, group))
    
    return suspicious

def simulate_attestor_population(n_attestors: int = 20, 
                                  n_events: int = 100) -> Dict[str, AttestorProfile]:
    """Simulate attestor population with varying quality."""
    profiles = {}
    
    for i in range(n_attestors):
        # Types: honest-calibrated, overconfident, rubber-stamper, adversarial
        atype = random.choices(
            ["calibrated", "overconfident", "rubber_stamp", "adversarial"],
            weights=[0.4, 0.3, 0.2, 0.1]
        )[0]
        
        aid = f"attestor_{i:03d}"
        profile = AttestorProfile(attestor_id=aid)
        
        for _ in range(random.randint(10, n_events)):
            profile.total_attestations += 1
            
            if atype == "calibrated":
                conf = random.uniform(0.75, 0.95)
                triggered = random.random() < (1 - conf)  # fires proportionally
                specificity = random.uniform(0.5, 0.9)
            elif atype == "overconfident":
                conf = random.uniform(0.9, 0.99)
                triggered = random.random() < 0.15  # fires more than confidence suggests
                specificity = random.uniform(0.3, 0.7)
            elif atype == "rubber_stamp":
                conf = random.uniform(0.85, 0.95)
                triggered = False  # never fires
                specificity = random.uniform(0.05, 0.2)  # generic counterfactuals
            else:  # adversarial
                conf = random.uniform(0.8, 0.95)
                triggered = random.random() < 0.5  # noisy
                specificity = random.uniform(0.1, 0.4)
            
            if triggered:
                profile.triggers_fired += 1
            profile.mean_confidence = (profile.mean_confidence * (profile.total_attestations - 1) + conf) / profile.total_attestations
            profile.counterfactual_specificity = (profile.counterfactual_specificity * (profile.total_attestations - 1) + specificity) / profile.total_attestations
        
        profiles[aid] = profile
    
    return profiles

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("COUNTERFACTUAL ATTESTATION SCORER")
    print("Popper demarcation for trust protocols")
    print("=" * 60)
    
    # Simulate attestor population
    profiles = simulate_attestor_population(20, 100)
    
    print("\n--- Attestor Calibration Ranking ---")
    ranked = sorted(profiles.values(), key=lambda p: p.brier_score)
    for p in ranked:
        print(f"  {p.attestor_id}: Brier={p.brier_score:.4f} ({p.calibration_grade})")
        print(f"    conf={p.mean_confidence:.2f} trigger={p.trigger_rate:.2f} "
              f"specificity={p.counterfactual_specificity:.2f} "
              f"n={p.total_attestations}")
    
    # Identify rubber-stampers
    print("\n--- Rubber-Stamper Detection ---")
    for p in profiles.values():
        if p.trigger_rate == 0 and p.total_attestations > 20:
            print(f"  ⚠️ {p.attestor_id}: {p.total_attestations} attestations, "
                  f"0 triggers, conf={p.mean_confidence:.2f}")
            print(f"     Brier={p.brier_score:.4f} — NEVER DISAGREED")
    
    # Specificity analysis
    print("\n--- Counterfactual Specificity Distribution ---")
    low_spec = sum(1 for p in profiles.values() if p.counterfactual_specificity < 0.2)
    mid_spec = sum(1 for p in profiles.values() if 0.2 <= p.counterfactual_specificity < 0.5)
    high_spec = sum(1 for p in profiles.values() if p.counterfactual_specificity >= 0.5)
    print(f"  Low (<0.2): {low_spec} — likely generic/copy-paste")
    print(f"  Mid (0.2-0.5): {mid_spec} — partial evaluation")
    print(f"  High (>0.5): {high_spec} — genuine evaluation")
    
    # Combined score
    print("\n--- Combined Trust Score (Brier × Specificity) ---")
    for p in sorted(profiles.values(), 
                    key=lambda p: (1 - p.brier_score) * p.counterfactual_specificity,
                    reverse=True)[:5]:
        combined = (1 - p.brier_score) * p.counterfactual_specificity
        print(f"  {p.attestor_id}: combined={combined:.3f} "
              f"(brier={p.brier_score:.3f}, spec={p.counterfactual_specificity:.2f})")
    
    print("\n" + "=" * 60)
    print("KEY: Counterfactual specificity × calibration = trust score")
    print("Rubber-stampers: 0% trigger rate exposes them instantly")
    print("Replay attacks: divergent counterfactuals on same event = red flag")
    print("=" * 60)
