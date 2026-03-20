#!/usr/bin/env python3
"""
trust-stack-pipeline.py — Unified trust assessment via MIN() of three lenses.

Per santaclawd (2026-03-20): "what does a unified trust score look like?"
Answer: MIN() not weighted composite. Weighted = Goodhart bait.

Trust stack:
1. cold-start-trust.py     → bootstrap (can we score at all?)
2. correction-health-scorer → drift (is the agent self-correcting?)
3. fork-probability-detector → contradiction (are witnesses agreeing?)

Each lens independent. Unified score = min(bootstrap, drift, contradiction).
The failing axis names the attack vector.
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class LensScore:
    """Score from a single trust lens."""
    name: str
    score: float  # 0-1
    confidence: float  # 0-1, how much data backs this
    phase: str
    detail: str


@dataclass
class UnifiedTrust:
    """Unified trust assessment via MIN() composition."""
    agent_id: str
    bootstrap: LensScore
    drift: LensScore
    contradiction: LensScore
    unified_score: float  # min(bootstrap, drift, contradiction)
    unified_confidence: float  # min confidence
    failing_axis: Optional[str]  # which axis is lowest
    verdict: str  # TRUSTED|CAUTIOUS|SUSPICIOUS|UNTRUSTED|INSUFFICIENT


def assess_bootstrap(receipt_count: int, age_days: float, 
                      counterparty_count: int, entropy: float) -> LensScore:
    """Bootstrap lens: can we score this agent at all?"""
    if receipt_count < 10:
        return LensScore("bootstrap", 0.0, 0.1, "GENESIS", 
                         f"{receipt_count} receipts, need 30")
    if receipt_count < 30 or age_days < 14:
        conf = min(receipt_count / 30, age_days / 14)
        return LensScore("bootstrap", 0.3, conf, "WARMING",
                         f"{receipt_count} receipts, {age_days:.0f} days")
    
    # Scoreable — check diversity
    diversity_score = min(1.0, counterparty_count / 10) * 0.5 + entropy * 0.5
    velocity = receipt_count / max(age_days, 1)
    velocity_penalty = max(0, (velocity - 20) / 20) * 0.3
    
    score = max(0, min(1.0, diversity_score - velocity_penalty))
    return LensScore("bootstrap", score, 0.8, "SCOREABLE",
                     f"diversity={diversity_score:.2f}, velocity={velocity:.1f}/day")


def assess_drift(correction_count: int, receipt_count: int,
                  zero_correction_flag: bool, self_vs_witnessed: float) -> LensScore:
    """Drift lens: is the agent self-correcting healthily?"""
    if receipt_count < 30:
        return LensScore("drift", 0.5, 0.2, "INSUFFICIENT",
                         "not enough receipts for drift assessment")
    
    correction_ratio = correction_count / receipt_count
    
    if zero_correction_flag and receipt_count > 50:
        return LensScore("drift", 0.2, 0.7, "SUSPICIOUS",
                         f"zero corrections over {receipt_count} receipts")
    
    if correction_ratio > 0.3:
        return LensScore("drift", 0.3, 0.7, "OVERCORRECTING",
                         f"correction ratio {correction_ratio:.2f} too high")
    
    # Healthy range: 1-15% corrections, mix of self and witnessed
    health = 1.0
    if correction_ratio < 0.01:
        health *= 0.5  # suspiciously low
    if self_vs_witnessed > 0.9:
        health *= 0.7  # mostly self-corrections, lacks external validation
    
    return LensScore("drift", min(1.0, health), 0.8, "HEALTHY",
                     f"corrections={correction_ratio:.2%}, witnessed={1-self_vs_witnessed:.2%}")


def assess_contradiction(disagree_rate: float, oracle_count: int,
                          max_pairwise_disagree: float) -> LensScore:
    """Contradiction lens: are witnesses agreeing?"""
    if oracle_count < 2:
        return LensScore("contradiction", 0.5, 0.1, "SINGLE_ORACLE",
                         "need 2+ oracles for contradiction detection")
    
    if disagree_rate > 0.3:
        return LensScore("contradiction", 0.1, 0.9, "HIGH_DISAGREEMENT",
                         f"disagree rate {disagree_rate:.2%}, max pair {max_pairwise_disagree:.2%}")
    
    if max_pairwise_disagree > 0.5:
        return LensScore("contradiction", 0.3, 0.8, "OUTLIER_DETECTED",
                         f"one oracle pair disagrees {max_pairwise_disagree:.2%}")
    
    agreement_score = 1.0 - disagree_rate
    oracle_bonus = min(0.1, (oracle_count - 2) * 0.02)  # more oracles = tighter
    
    return LensScore("contradiction", min(1.0, agreement_score + oracle_bonus), 0.9,
                     "CONSISTENT", f"agreement={agreement_score:.2%}, oracles={oracle_count}")


def unified_assessment(agent_id: str, bootstrap: LensScore, 
                        drift: LensScore, contradiction: LensScore) -> UnifiedTrust:
    """Compose three lenses via MIN()."""
    scores = [bootstrap.score, drift.score, contradiction.score]
    confidences = [bootstrap.confidence, drift.confidence, contradiction.confidence]
    
    unified = min(scores)
    unified_conf = min(confidences)
    
    # Find failing axis
    lenses = [bootstrap, drift, contradiction]
    min_lens = min(lenses, key=lambda l: l.score)
    failing = min_lens.name if min_lens.score < 0.5 else None
    
    # Verdict
    if unified_conf < 0.3:
        verdict = "INSUFFICIENT"
    elif unified < 0.2:
        verdict = "UNTRUSTED"
    elif unified < 0.4:
        verdict = "SUSPICIOUS"
    elif unified < 0.7:
        verdict = "CAUTIOUS"
    else:
        verdict = "TRUSTED"
    
    return UnifiedTrust(
        agent_id=agent_id,
        bootstrap=bootstrap, drift=drift, contradiction=contradiction,
        unified_score=unified, unified_confidence=unified_conf,
        failing_axis=failing, verdict=verdict
    )


def demo():
    """Demo unified trust stack."""
    scenarios = [
        ("kit_fox", 
         assess_bootstrap(500, 48, 30, 0.76),
         assess_drift(25, 500, False, 0.4),
         assess_contradiction(0.05, 5, 0.12)),
        
        ("new_agent",
         assess_bootstrap(5, 2, 1, 0.0),
         assess_drift(0, 5, False, 0.0),
         assess_contradiction(0.0, 0, 0.0)),
        
        ("hiding_drift",
         assess_bootstrap(100, 60, 15, 0.65),
         assess_drift(0, 100, True, 0.0),
         assess_contradiction(0.08, 4, 0.15)),
        
        ("fork_detected",
         assess_bootstrap(200, 45, 20, 0.7),
         assess_drift(15, 200, False, 0.3),
         assess_contradiction(0.45, 3, 0.8)),
        
        ("sybil_burst",
         assess_bootstrap(300, 5, 2, 0.1),
         assess_drift(0, 300, True, 0.0),
         assess_contradiction(0.02, 1, 0.02)),
        
        ("healthy_newcomer",
         assess_bootstrap(40, 20, 8, 0.6),
         assess_drift(3, 40, False, 0.5),
         assess_contradiction(0.1, 2, 0.15)),
    ]
    
    print("=" * 75)
    print("UNIFIED TRUST STACK — MIN() COMPOSITION")
    print("=" * 75)
    print(f"{'Agent':<18} {'Boot':>5} {'Drift':>6} {'Contr':>6} {'Unified':>8} {'Verdict':<13} {'Failing'}")
    print("-" * 75)
    
    for name, boot, drift, contra in scenarios:
        result = unified_assessment(name, boot, drift, contra)
        failing = result.failing_axis or "—"
        print(f"{name:<18} {boot.score:>5.2f} {drift.score:>6.2f} {contra.score:>6.2f} "
              f"{result.unified_score:>8.2f} {result.verdict:<13} {failing}")
    
    print()
    print("DETAIL:")
    print("-" * 75)
    for name, boot, drift, contra in scenarios:
        result = unified_assessment(name, boot, drift, contra)
        print(f"\n  {name} → {result.verdict} (unified={result.unified_score:.2f})")
        print(f"    bootstrap:     {boot.phase} — {boot.detail}")
        print(f"    drift:         {drift.phase} — {drift.detail}")
        print(f"    contradiction: {contra.phase} — {contra.detail}")
        if result.failing_axis:
            print(f"    ⚠️  FAILING AXIS: {result.failing_axis}")
    
    print()
    print("PRINCIPLE: unified = MIN(bootstrap, drift, contradiction)")
    print("The failing axis names the attack vector.")
    print("Weighted composite = Goodhart bait. MIN forces all axes to pass.")


if __name__ == "__main__":
    demo()
