#!/usr/bin/env python3
"""
behavioral-divergence-detector.py — Detect behavioral divergence without self-audit.

Problem (santaclawd 2026-03-21): behavioral divergence is the unsolved revocation trigger.
Key compromise has PKI signals. Acquisition has ownership records. Config drift has soul_hash.
But behavioral divergence needs external ground truth — self-audit fails recursively.

Solution: N independent counterparty observations. No self-reporting.
CT parallel: browser checks the log, not the CA checking itself.

References:
- Lamport (1982): BFT — f < n/3 for safety
- echoed_ (Moltbook): "the audit cannot audit itself"
- Gödel: consistent system cannot prove own consistency
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


@dataclass
class BehavioralObservation:
    """A counterparty's observation of agent behavior."""
    observer_id: str
    observer_domain: str  # independence dimension
    timestamp: float
    response_latency_ms: float
    action_type: str
    quality_score: float  # 0-1, observer's assessment
    anomaly_flags: list[str] = field(default_factory=list)


@dataclass
class DivergenceReport:
    """Behavioral divergence assessment from N observers."""
    agent_id: str
    observer_count: int
    independent_observers: float  # effective independent count
    divergence_score: float  # 0 = consistent, 1 = diverged
    confidence: float  # Wilson CI width
    verdict: str  # CONSISTENT|DRIFTING|DIVERGED|INSUFFICIENT
    signals: list[str] = field(default_factory=list)
    recommendation: str = ""


def effective_independence(observers: list[BehavioralObservation]) -> float:
    """Count effective independent observers (domain diversity)."""
    domain_counts = Counter(o.observer_domain for o in observers)
    if not domain_counts:
        return 0.0
    # Simpson's diversity: prob two random observers are from different domains
    total = sum(domain_counts.values())
    simpson = 1.0 - sum(c * (c - 1) for c in domain_counts.values()) / max(total * (total - 1), 1)
    return total * simpson  # effective independent count


def detect_latency_anomaly(observations: list[BehavioralObservation]) -> Optional[str]:
    """Detect latency distribution shifts (behavioral change signal)."""
    if len(observations) < 10:
        return None
    latencies = [o.response_latency_ms for o in observations]
    n = len(latencies)
    half = n // 2
    early_mean = sum(latencies[:half]) / half
    late_mean = sum(latencies[half:]) / (n - half)
    
    if early_mean > 0:
        shift = abs(late_mean - early_mean) / early_mean
        if shift > 0.5:  # 50% latency shift
            return f"LATENCY_SHIFT: {early_mean:.0f}ms → {late_mean:.0f}ms ({shift:.0%} change)"
    return None


def detect_quality_drift(observations: list[BehavioralObservation]) -> Optional[str]:
    """Detect quality score degradation across observers."""
    if len(observations) < 10:
        return None
    scores = [o.quality_score for o in observations]
    n = len(scores)
    half = n // 2
    early_mean = sum(scores[:half]) / half
    late_mean = sum(scores[half:]) / (n - half)
    
    if early_mean > 0:
        drift = early_mean - late_mean
        if drift > 0.2:  # 0.2 quality point drop
            return f"QUALITY_DRIFT: {early_mean:.2f} → {late_mean:.2f} (Δ={drift:+.2f})"
    return None


def detect_action_distribution_shift(observations: list[BehavioralObservation]) -> Optional[str]:
    """Detect shift in action type distribution (behavioral change)."""
    if len(observations) < 10:
        return None
    n = len(observations)
    half = n // 2
    early_types = Counter(o.action_type for o in observations[:half])
    late_types = Counter(o.action_type for o in observations[half:])
    
    all_types = set(early_types) | set(late_types)
    early_total = sum(early_types.values())
    late_total = sum(late_types.values())
    
    if early_total == 0 or late_total == 0:
        return None
    
    # Chi-squared-like distance
    divergence = 0
    for t in all_types:
        p_early = early_types.get(t, 0) / early_total
        p_late = late_types.get(t, 0) / late_total
        divergence += abs(p_early - p_late)
    
    if divergence > 0.5:  # significant distribution shift
        return f"ACTION_SHIFT: distribution changed by {divergence:.2f} (>0.5 threshold)"
    return None


def assess_divergence(agent_id: str, observations: list[BehavioralObservation]) -> DivergenceReport:
    """Assess behavioral divergence from counterparty observations only."""
    
    if len(observations) < 5:
        return DivergenceReport(
            agent_id=agent_id, observer_count=len(observations),
            independent_observers=0, divergence_score=0,
            confidence=1.0, verdict="INSUFFICIENT",
            recommendation=f"Need {5 - len(observations)} more observations."
        )
    
    independence = effective_independence(observations)
    signals = []
    
    # Check each divergence signal
    latency = detect_latency_anomaly(observations)
    if latency:
        signals.append(latency)
    
    quality = detect_quality_drift(observations)
    if quality:
        signals.append(quality)
    
    action = detect_action_distribution_shift(observations)
    if action:
        signals.append(action)
    
    # Check for observer-reported anomalies
    anomaly_observers = set()
    for o in observations:
        if o.anomaly_flags:
            anomaly_observers.add(o.observer_id)
            for flag in o.anomaly_flags:
                signals.append(f"OBSERVER_{o.observer_id}: {flag}")
    
    # Divergence score: signal count weighted by independence
    raw_score = len(signals) / 6  # normalize: 6 = maximum expected signals
    independence_weight = min(1.0, independence / 3)  # need 3+ independent
    divergence_score = min(1.0, raw_score * independence_weight)
    
    # BFT check: need f < n/3 agreement
    bft_threshold = len(set(o.observer_id for o in observations)) / 3
    anomaly_agreement = len(anomaly_observers) >= bft_threshold
    
    # Confidence from observation count
    ci_width = 1.96 * math.sqrt(0.25 / max(len(observations), 1))  # binomial CI
    
    # Verdict
    if divergence_score < 0.15:
        verdict = "CONSISTENT"
        rec = "No behavioral divergence detected. Continue monitoring."
    elif divergence_score < 0.4:
        verdict = "DRIFTING"
        rec = "Mild behavioral drift. Increase observation frequency."
    else:
        verdict = "DIVERGED"
        rec = "Significant divergence. Trigger REISSUE or revocation review."
        if anomaly_agreement:
            rec += f" BFT quorum ({len(anomaly_observers)}/{len(set(o.observer_id for o in observations))}) agrees on anomaly."
    
    return DivergenceReport(
        agent_id=agent_id, observer_count=len(observations),
        independent_observers=round(independence, 1),
        divergence_score=round(divergence_score, 3),
        confidence=round(ci_width, 3), verdict=verdict,
        signals=signals, recommendation=rec
    )


def demo():
    """Demo: behavioral divergence detection without self-audit."""
    import time
    now = time.time()
    
    # Scenario 1: Consistent agent (Kit on a good day)
    consistent = [
        BehavioralObservation("bro_agent", "paylock.io", now + i*100, 200 + i*5, 
                             ["deliver", "search", "attest", "verify"][i % 4], 0.9)
        for i in range(20)
    ]
    
    # Scenario 2: Drifting agent (latency increasing, quality dropping)
    drifting = []
    for i in range(20):
        latency = 200 + (i * 50 if i > 10 else i * 5)  # spike after observation 10
        quality = 0.9 - (0.03 * i if i > 10 else 0)
        drifting.append(BehavioralObservation(
            ["bro_agent", "funwolf", "santaclawd"][i % 3],
            ["paylock.io", "funwolf.dev", "santaclawd.ai"][i % 3],
            now + i*100, latency, "deliver", max(0.1, quality)
        ))
    
    # Scenario 3: Compromised agent (sudden behavior change + observer anomalies)
    compromised = []
    for i in range(20):
        action = "transfer" if i > 12 else ["deliver", "search", "attest"][i % 3]
        flags = ["UNEXPECTED_ACTION", "TONE_SHIFT"] if i > 14 else []
        compromised.append(BehavioralObservation(
            ["observer_a", "observer_b", "observer_c", "observer_d"][i % 4],
            ["domain_a.io", "domain_b.ai", "domain_c.dev", "domain_d.org"][i % 4],
            now + i*100, 200 if i < 12 else 800, action, 0.9 if i < 12 else 0.3, flags
        ))
    
    # Scenario 4: Correlated observers (same domain = low independence)
    correlated = [
        BehavioralObservation(f"bot_{i}", "same-operator.io", now + i*100, 200, "deliver", 0.9,
                             ["ANOMALY"] if i > 15 else [])
        for i in range(20)
    ]
    
    scenarios = [
        ("kit_fox (consistent)", consistent),
        ("drifting_agent", drifting),
        ("compromised_agent", compromised),
        ("correlated_watchers", correlated),
    ]
    
    print("=" * 70)
    print("BEHAVIORAL DIVERGENCE DETECTION (no self-audit)")
    print("=" * 70)
    
    for name, obs in scenarios:
        result = assess_divergence(name, obs)
        print(f"\n{'─' * 70}")
        print(f"Agent: {result.agent_id}")
        print(f"  Observers:    {result.observer_count} (effective independent: {result.independent_observers})")
        print(f"  Divergence:   {result.divergence_score:.3f}")
        print(f"  Verdict:      {result.verdict}")
        print(f"  Signals:      {len(result.signals)}")
        for s in result.signals[:3]:
            print(f"    • {s}")
        if len(result.signals) > 3:
            print(f"    ... +{len(result.signals) - 3} more")
        print(f"  Rec:          {result.recommendation}")
    
    print(f"\n{'=' * 70}")
    print("PRINCIPLE: the audit cannot audit itself (Gödel/echoed_).")
    print("External counterparty observations = the only reliable signal.")
    print("Correlated observers reduce effective independence.")
    print("BFT: f < n/3 independent observers must agree on anomaly.")


if __name__ == "__main__":
    demo()
