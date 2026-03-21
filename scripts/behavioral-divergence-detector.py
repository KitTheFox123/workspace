#!/usr/bin/env python3
"""
behavioral-divergence-detector.py — Detect behavioral divergence from counterparty signals.

Problem (santaclawd 2026-03-21): behavioral_divergence is the unsolved revocation
trigger. Key compromise has PKI signals. Config drift has soul_hash. But behavioral
divergence needs external ground truth — self-monitoring fails (Gödel/echoed_).

Solution: Use COUNTERPARTY signals, not self-report.
- Receipt pattern changes (action type distribution shift)
- Response latency drift (timing fingerprint changes)
- Counterparty satisfaction drift (evidence grade changes)
- Witness disagreement rate (attestation conflicts)

"Who watches the watchmen?" — Other watchmen, independently.
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class BehavioralWindow:
    """A time window of behavioral signals from counterparties."""
    window_label: str
    action_type_counts: dict[str, int]
    avg_response_latency_ms: float
    evidence_grade_counts: dict[str, int]  # chain|witness|self
    witness_disagreement_count: int
    total_receipts: int
    counterparty_count: int


@dataclass  
class DivergenceReport:
    """Behavioral divergence analysis between two windows."""
    agent_id: str
    baseline: BehavioralWindow
    current: BehavioralWindow
    action_divergence: float  # Jensen-Shannon divergence of action types
    latency_drift: float  # relative change in response latency
    grade_drift: float  # shift toward lower evidence grades
    disagreement_rate: float  # witness disagreements per receipt
    composite_score: float  # 0-1, higher = more diverged
    verdict: str  # STABLE|DRIFTING|DIVERGED|COMPROMISED
    signals: list[str]  # human-readable signals


def kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """KL divergence D(P||Q). Returns inf if Q has zeros where P doesn't."""
    all_keys = set(p) | set(q)
    total = 0.0
    for k in all_keys:
        pk = p.get(k, 0.0)
        qk = q.get(k, 1e-10)  # smoothing
        if pk > 0:
            total += pk * math.log2(pk / qk)
    return total


def js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence (symmetric, bounded [0,1])."""
    all_keys = set(p) | set(q)
    m = {k: (p.get(k, 0.0) + q.get(k, 0.0)) / 2 for k in all_keys}
    return (kl_divergence(p, m) + kl_divergence(q, m)) / 2


def normalize_counts(counts: dict[str, int]) -> dict[str, float]:
    """Normalize count dict to probability distribution."""
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def detect_divergence(
    agent_id: str,
    baseline: BehavioralWindow,
    current: BehavioralWindow,
) -> DivergenceReport:
    """Detect behavioral divergence between baseline and current windows."""
    signals = []

    # 1. Action type distribution shift (Jensen-Shannon)
    p = normalize_counts(baseline.action_type_counts)
    q = normalize_counts(current.action_type_counts)
    action_div = js_divergence(p, q) if p and q else 0.0
    if action_div > 0.3:
        signals.append(f"ACTION_SHIFT: JS divergence {action_div:.3f} (threshold 0.3)")

    # 2. Response latency drift
    if baseline.avg_response_latency_ms > 0:
        latency_drift = abs(current.avg_response_latency_ms - baseline.avg_response_latency_ms) / baseline.avg_response_latency_ms
    else:
        latency_drift = 0.0
    if latency_drift > 0.5:
        signals.append(f"LATENCY_DRIFT: {latency_drift:.0%} change ({baseline.avg_response_latency_ms:.0f}ms → {current.avg_response_latency_ms:.0f}ms)")

    # 3. Evidence grade drift (shift toward self-attested = suspicious)
    baseline_chain = baseline.evidence_grade_counts.get("chain", 0)
    current_chain = current.evidence_grade_counts.get("chain", 0)
    baseline_self = baseline.evidence_grade_counts.get("self", 0)
    current_self = current.evidence_grade_counts.get("self", 0)
    
    baseline_chain_ratio = baseline_chain / max(baseline.total_receipts, 1)
    current_chain_ratio = current_chain / max(current.total_receipts, 1)
    grade_drift = max(0, baseline_chain_ratio - current_chain_ratio)  # positive = downgrade
    if grade_drift > 0.2:
        signals.append(f"GRADE_DOWNGRADE: chain ratio {baseline_chain_ratio:.0%} → {current_chain_ratio:.0%}")

    # 4. Witness disagreement rate
    disagreement_rate = current.witness_disagreement_count / max(current.total_receipts, 1)
    if disagreement_rate > 0.1:
        signals.append(f"WITNESS_CONFLICT: {disagreement_rate:.0%} disagreement rate")

    # 5. Counterparty concentration change
    if current.counterparty_count < baseline.counterparty_count * 0.5:
        signals.append(f"COUNTERPARTY_DROP: {baseline.counterparty_count} → {current.counterparty_count}")

    # Composite score (weighted)
    composite = min(1.0, (
        action_div * 0.3 +
        min(latency_drift, 1.0) * 0.2 +
        grade_drift * 0.25 +
        min(disagreement_rate * 5, 1.0) * 0.15 +
        (0.1 if current.counterparty_count < baseline.counterparty_count * 0.5 else 0.0)
    ))

    # Verdict
    if composite < 0.1:
        verdict = "STABLE"
    elif composite < 0.25:
        verdict = "DRIFTING"
    elif composite < 0.5:
        verdict = "DIVERGED"
    else:
        verdict = "COMPROMISED"

    return DivergenceReport(
        agent_id=agent_id,
        baseline=baseline,
        current=current,
        action_divergence=action_div,
        latency_drift=latency_drift,
        grade_drift=grade_drift,
        disagreement_rate=disagreement_rate,
        composite_score=composite,
        verdict=verdict,
        signals=signals,
    )


def demo():
    """Demo behavioral divergence detection."""
    # Scenario 1: Stable agent (Kit)
    kit_baseline = BehavioralWindow("week_1-4", {"deliver": 40, "search": 30, "attest": 20, "verify": 10}, 850, {"chain": 60, "witness": 30, "self": 10}, 2, 100, 15)
    kit_current = BehavioralWindow("week_5-8", {"deliver": 38, "search": 32, "attest": 22, "verify": 8}, 820, {"chain": 58, "witness": 32, "self": 10}, 3, 100, 14)

    # Scenario 2: Drifting agent (model swap)
    drift_baseline = BehavioralWindow("pre_swap", {"deliver": 40, "search": 30, "attest": 20, "verify": 10}, 500, {"chain": 60, "witness": 30, "self": 10}, 1, 100, 12)
    drift_current = BehavioralWindow("post_swap", {"deliver": 15, "search": 50, "attest": 5, "verify": 30}, 1200, {"chain": 30, "witness": 20, "self": 50}, 8, 100, 8)

    # Scenario 3: Compromised (takeover)
    comp_baseline = BehavioralWindow("pre_takeover", {"deliver": 40, "search": 30, "attest": 20, "verify": 10}, 600, {"chain": 70, "witness": 20, "self": 10}, 1, 100, 20)
    comp_current = BehavioralWindow("post_takeover", {"transfer": 80, "verify": 20}, 200, {"chain": 0, "witness": 0, "self": 100}, 15, 100, 2)

    scenarios = [
        ("kit_fox", kit_baseline, kit_current),
        ("model_swap", drift_baseline, drift_current),
        ("takeover", comp_baseline, comp_current),
    ]

    print("=" * 65)
    print("BEHAVIORAL DIVERGENCE DETECTION")
    print("=" * 65)

    for name, baseline, current in scenarios:
        report = detect_divergence(name, baseline, current)
        print(f"\n{'─' * 65}")
        print(f"Agent: {name}")
        print(f"  Action JS divergence:   {report.action_divergence:.3f}")
        print(f"  Latency drift:          {report.latency_drift:.0%}")
        print(f"  Grade drift:            {report.grade_drift:.2f}")
        print(f"  Disagreement rate:      {report.disagreement_rate:.0%}")
        print(f"  Composite score:        {report.composite_score:.3f}")
        print(f"  Verdict:                {report.verdict}")
        if report.signals:
            print(f"  Signals:")
            for s in report.signals:
                print(f"    ⚠️  {s}")
        else:
            print(f"  Signals: none (stable)")

    print(f"\n{'=' * 65}")
    print("KEY: behavioral divergence needs COUNTERPARTY signals.")
    print("Self-monitoring fails (Gödel). External witnesses break the loop.")
    print("\"Who watches the watchmen?\" — Other watchmen, independently.")


if __name__ == "__main__":
    demo()
