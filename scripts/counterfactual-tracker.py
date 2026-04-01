#!/usr/bin/env python3
"""counterfactual-tracker.py — Track and evaluate attestation counterfactuals.

Every attestation should include: "what evidence would change my verdict?"
If the answer is "nothing" — that's not trust, it's faith.
If it's never tested — it's decorative (Lakatos degenerating program).

Based on:
- Popper: falsifiability as demarcation criterion
- Lakatos: progressive vs degenerating research programs
- Norton (Pitt): falsifiability alone insufficient — need testable counterfactuals
"""

import json
import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta

@dataclass
class Counterfactual:
    """A stated condition that would change an attestation verdict."""
    attestation_id: str
    condition: str          # "what would change your mind"
    testable: bool          # is this actually verifiable?
    tested: bool = False    # has it been tested?
    triggered: bool = False # did the test flip the verdict?
    created_at: str = ""
    tested_at: Optional[str] = None

@dataclass
class Attestation:
    """An attestation with required counterfactual field."""
    id: str
    attester: str
    subject: str
    verdict: str  # "trusted", "untrusted", "insufficient_data"
    confidence: float
    counterfactual: Counterfactual
    timestamp: str

def evaluate_counterfactual_quality(cf: Counterfactual) -> Dict:
    """Score a counterfactual on Popper/Norton criteria."""
    score = 0.0
    issues = []
    
    # Is it testable? (Norton: must be testable, not just stated)
    if cf.testable:
        score += 0.4
    else:
        issues.append("NOT_TESTABLE: stated but unverifiable")
    
    # Is it specific? (vague = unfalsifiable)
    vague_markers = ["nothing", "never", "impossible", "n/a", "none"]
    if any(m in cf.condition.lower() for m in vague_markers):
        issues.append("UNFALSIFIABLE: vague/absolute condition")
    else:
        score += 0.3
    
    # Has it been tested? (Lakatos: untested = potentially degenerating)
    if cf.tested:
        score += 0.2
        if cf.triggered:
            score += 0.1  # bonus: system actually responded to evidence
    else:
        issues.append("UNTESTED: never challenged")
    
    quality = "progressive" if score >= 0.7 else "stagnant" if score >= 0.4 else "degenerating"
    
    return {
        "score": score,
        "quality": quality,
        "issues": issues,
        "lakatos_status": quality
    }

def simulate_attestation_system(n_attestations: int = 100, 
                                 test_rate: float = 0.15,
                                 trigger_rate: float = 0.3) -> Dict:
    """Simulate attestation system with counterfactual tracking."""
    
    conditions = [
        ("behavioral anomaly detected in 30-day window", True),
        ("cross-platform identity mismatch", True),
        ("attestation chain breaks at >2 hops", True),
        ("nothing would change my assessment", False),  # unfalsifiable!
        ("significant decrease in response quality", True),
        ("n/a", False),  # lazy
        ("temporal pattern becomes synthetic (CV < 0.05)", True),
        ("impossible to determine", False),
        ("third-party negative attestation with evidence", True),
        ("activity ceases for >7 days without notice", True),
    ]
    
    attestations = []
    for i in range(n_attestations):
        cond_text, testable = random.choice(conditions)
        tested = random.random() < test_rate if testable else False
        triggered = random.random() < trigger_rate if tested else False
        
        cf = Counterfactual(
            attestation_id=f"att_{i:04d}",
            condition=cond_text,
            testable=testable,
            tested=tested,
            triggered=triggered,
            created_at=f"2026-04-01T{random.randint(0,23):02d}:{random.randint(0,59):02d}:00Z"
        )
        
        att = Attestation(
            id=f"att_{i:04d}",
            attester=f"agent_{random.randint(1,20):03d}",
            subject=f"agent_{random.randint(1,20):03d}",
            verdict=random.choice(["trusted", "trusted", "trusted", "untrusted", "insufficient_data"]),
            confidence=random.uniform(0.5, 0.99),
            counterfactual=cf,
            timestamp=cf.created_at
        )
        attestations.append(att)
    
    # Analyze system health
    total = len(attestations)
    testable_count = sum(1 for a in attestations if a.counterfactual.testable)
    tested_count = sum(1 for a in attestations if a.counterfactual.tested)
    triggered_count = sum(1 for a in attestations if a.counterfactual.triggered)
    unfalsifiable = total - testable_count
    
    # Lakatos classification
    test_ratio = tested_count / max(testable_count, 1)
    system_status = "progressive" if test_ratio > 0.1 else "stagnant" if test_ratio > 0.05 else "degenerating"
    
    return {
        "total_attestations": total,
        "testable_counterfactuals": testable_count,
        "untestable_counterfactuals": unfalsifiable,
        "tested": tested_count,
        "triggered": triggered_count,
        "test_ratio": test_ratio,
        "unfalsifiable_pct": unfalsifiable / total,
        "system_status": system_status,
        "details": {
            "progressive": sum(1 for a in attestations if evaluate_counterfactual_quality(a.counterfactual)["quality"] == "progressive"),
            "stagnant": sum(1 for a in attestations if evaluate_counterfactual_quality(a.counterfactual)["quality"] == "stagnant"),
            "degenerating": sum(1 for a in attestations if evaluate_counterfactual_quality(a.counterfactual)["quality"] == "degenerating"),
        }
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("COUNTERFACTUAL TRACKER")
    print("'What evidence would change your verdict?'")
    print("If answer is 'nothing' — that's faith, not trust.")
    print("=" * 60)
    
    # Run simulation at different test rates
    print("\n--- Test Rate Impact on System Health ---")
    for rate in [0.0, 0.05, 0.10, 0.15, 0.25, 0.50]:
        result = simulate_attestation_system(200, test_rate=rate)
        print(f"\nTest rate: {rate:.0%}")
        print(f"  Testable: {result['testable_counterfactuals']}/{result['total_attestations']}")
        print(f"  Tested: {result['tested']}")
        print(f"  Triggered: {result['triggered']}")
        print(f"  Unfalsifiable: {result['unfalsifiable_pct']:.1%}")
        print(f"  System: {result['system_status'].upper()}")
        print(f"  Progressive/Stagnant/Degenerating: {result['details']['progressive']}/{result['details']['stagnant']}/{result['details']['degenerating']}")
    
    # Key insight
    print("\n" + "=" * 60)
    print("KEY FINDINGS:")
    print("• 0% test rate → system degenerates (counterfactuals decorative)")
    print("• 10%+ test rate → system becomes progressive")
    print("• >25% unfalsifiable attestations = systemic red flag")
    print("• Triggered counterfactuals = system LEARNING, not failing")
    print("• Popper: 'A theory that can't be refuted isn't scientific'")
    print("• Lakatos: untested predictions = degenerating program")
    print("=" * 60)
