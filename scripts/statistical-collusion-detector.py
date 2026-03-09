#!/usr/bin/env python3
"""statistical-collusion-detector.py — Detect statistical collusion in attestor networks.

Based on Hardt et al 2023 "Algorithmic Collective Action":
collectives can coordinate without explicit communication via
signal planting/erasing. Provider diversity catches infra correlation
but not value correlation.

Detects:
1. Score correlation clustering (beyond expected from shared context)
2. Temporal burst patterns (coordinated timing)
3. Signal planting (injected score distributions deviating from expected)

Usage:
    python3 statistical-collusion-detector.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Tuple


@dataclass
class AttestorScore:
    attestor_id: str
    target_id: str
    score: float
    timestamp: float
    provider: str
    training_lineage: str


@dataclass
class CollusionSignal:
    signal_type: str  # correlation, temporal_burst, signal_plant, value_alignment
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float
    description: str
    attestors_involved: List[str]


def pearson_r(x: List[float], y: List[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x)/n, sum(y)/n
    dx = [xi - mx for xi in x]
    dy = [yi - my for yi in y]
    num = sum(a*b for a, b in zip(dx, dy))
    den = math.sqrt(sum(a*a for a in dx) * sum(b*b for b in dy))
    return num / den if den > 0 else 0.0


def detect_score_correlation(scores: List[AttestorScore]) -> List[CollusionSignal]:
    """Detect unusual score correlation between attestor pairs."""
    signals = []
    
    # Group by attestor
    by_attestor: Dict[str, List[AttestorScore]] = {}
    for s in scores:
        by_attestor.setdefault(s.attestor_id, []).append(s)
    
    attestors = list(by_attestor.keys())
    for i in range(len(attestors)):
        for j in range(i+1, len(attestors)):
            a, b = attestors[i], attestors[j]
            # Find shared targets
            targets_a = {s.target_id: s.score for s in by_attestor[a]}
            targets_b = {s.target_id: s.score for s in by_attestor[b]}
            shared = set(targets_a.keys()) & set(targets_b.keys())
            
            if len(shared) < 3:
                continue
            
            scores_a = [targets_a[t] for t in sorted(shared)]
            scores_b = [targets_b[t] for t in sorted(shared)]
            r = pearson_r(scores_a, scores_b)
            
            # Same provider = expected correlation
            same_provider = by_attestor[a][0].provider == by_attestor[b][0].provider
            same_lineage = by_attestor[a][0].training_lineage == by_attestor[b][0].training_lineage
            
            threshold = 0.9 if same_lineage else 0.8 if same_provider else 0.7
            
            if abs(r) > threshold:
                severity = "CRITICAL" if abs(r) > 0.95 else "HIGH" if abs(r) > 0.85 else "MEDIUM"
                context = ""
                if same_lineage:
                    context = " (same training lineage — expected but still risky)"
                elif same_provider:
                    context = " (same provider — infra correlation)"
                else:
                    context = " (different providers — suspicious)"
                
                signals.append(CollusionSignal(
                    signal_type="correlation",
                    severity=severity,
                    confidence=abs(r),
                    description=f"{a}↔{b}: r={r:.3f}{context}",
                    attestors_involved=[a, b]
                ))
    
    return signals


def detect_temporal_burst(scores: List[AttestorScore], window: float = 5.0) -> List[CollusionSignal]:
    """Detect coordinated timing patterns."""
    signals = []
    
    by_target: Dict[str, List[AttestorScore]] = {}
    for s in scores:
        by_target.setdefault(s.target_id, []).append(s)
    
    for target, target_scores in by_target.items():
        if len(target_scores) < 3:
            continue
        
        sorted_scores = sorted(target_scores, key=lambda s: s.timestamp)
        
        # Check for burst: many attestations in tight window
        for i in range(len(sorted_scores)):
            burst = [sorted_scores[i]]
            for j in range(i+1, len(sorted_scores)):
                if sorted_scores[j].timestamp - sorted_scores[i].timestamp <= window:
                    burst.append(sorted_scores[j])
            
            if len(burst) >= 3:
                unique_attestors = set(s.attestor_id for s in burst)
                if len(unique_attestors) >= 3:
                    # Check if scores in burst are suspiciously similar
                    burst_scores = [s.score for s in burst]
                    mean_s = sum(burst_scores) / len(burst_scores)
                    variance = sum((s - mean_s)**2 for s in burst_scores) / len(burst_scores)
                    cv = math.sqrt(variance) / mean_s if mean_s > 0 else 0
                    
                    if cv < 0.1:  # Very tight agreement in tight window
                        signals.append(CollusionSignal(
                            signal_type="temporal_burst",
                            severity="HIGH",
                            confidence=1.0 - cv,
                            description=f"Target {target}: {len(burst)} attestations in {window}s window, CV={cv:.3f}",
                            attestors_involved=list(unique_attestors)
                        ))
                break
    
    return signals


def detect_signal_planting(scores: List[AttestorScore]) -> List[CollusionSignal]:
    """Detect injected score distributions (Hardt 2023 signal planting)."""
    signals = []
    
    by_attestor: Dict[str, List[float]] = {}
    for s in scores:
        by_attestor.setdefault(s.attestor_id, []).append(s.score)
    
    # Compare each attestor's distribution to the pool mean
    all_scores = [s.score for s in scores]
    pool_mean = sum(all_scores) / len(all_scores) if all_scores else 0.5
    pool_std = math.sqrt(sum((s - pool_mean)**2 for s in all_scores) / len(all_scores)) if len(all_scores) > 1 else 0.1
    
    for attestor, a_scores in by_attestor.items():
        if len(a_scores) < 3:
            continue
        
        a_mean = sum(a_scores) / len(a_scores)
        deviation = abs(a_mean - pool_mean) / pool_std if pool_std > 0 else 0
        
        if deviation > 2.0:
            signals.append(CollusionSignal(
                signal_type="signal_plant",
                severity="HIGH" if deviation > 3.0 else "MEDIUM",
                confidence=min(1.0, deviation / 4.0),
                description=f"{attestor}: mean={a_mean:.2f} vs pool={pool_mean:.2f} ({deviation:.1f}σ deviation)",
                attestors_involved=[attestor]
            ))
    
    return signals


def analyze(scores: List[AttestorScore]) -> dict:
    """Run all detectors."""
    all_signals = []
    all_signals.extend(detect_score_correlation(scores))
    all_signals.extend(detect_temporal_burst(scores))
    all_signals.extend(detect_signal_planting(scores))
    
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    all_signals.sort(key=lambda s: severity_order.get(s.severity, 0), reverse=True)
    
    max_sev = max((severity_order.get(s.severity, 0) for s in all_signals), default=0)
    grade = "A" if max_sev == 0 else "B" if max_sev == 1 else "C" if max_sev == 2 else "D" if max_sev == 3 else "F"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_scores": len(scores),
        "unique_attestors": len(set(s.attestor_id for s in scores)),
        "signals": [asdict(s) for s in all_signals],
        "grade": grade,
        "summary": f"{len(all_signals)} collusion signals detected. Grade {grade}."
    }


def demo():
    """Demo with synthetic data."""
    random.seed(42)
    
    targets = [f"agent_{i}" for i in range(10)]
    
    # Scenario 1: Genuine independent attestors
    print("=" * 60)
    print("SCENARIO 1: Independent attestors")
    print("=" * 60)
    genuine = []
    for t in targets:
        base = random.uniform(0.3, 0.9)
        for a_id, prov, lineage in [("alice", "openai", "gpt"), ("bob", "anthropic", "claude"), ("carol", "google", "gemini")]:
            genuine.append(AttestorScore(a_id, t, base + random.gauss(0, 0.15), random.uniform(0, 100), prov, lineage))
    
    r1 = analyze(genuine)
    print(f"Grade: {r1['grade']} | Signals: {len(r1['signals'])}")
    for s in r1['signals']:
        print(f"  [{s['severity']}] {s['signal_type']}: {s['description']}")
    print()
    
    # Scenario 2: Colluding attestors (same scores, tight timing)
    print("=" * 60)
    print("SCENARIO 2: Colluding attestors")
    print("=" * 60)
    colluding = []
    for t in targets:
        agreed_score = random.uniform(0.7, 0.95)
        base_time = random.uniform(0, 100)
        for a_id, prov, lineage in [("mallory", "aws", "llama"), ("eve", "azure", "mistral"), ("ivan", "gcp", "gemma")]:
            colluding.append(AttestorScore(a_id, t, agreed_score + random.gauss(0, 0.02), base_time + random.uniform(0, 3), prov, lineage))
    
    r2 = analyze(colluding)
    print(f"Grade: {r2['grade']} | Signals: {len(r2['signals'])}")
    for s in r2['signals']:
        print(f"  [{s['severity']}] {s['signal_type']}: {s['description']}")
    print()
    
    # Scenario 3: Same-lineage bias (not collusion but correlated)
    print("=" * 60)
    print("SCENARIO 3: Same-lineage bias (not collusion)")
    print("=" * 60)
    biased = []
    for t in targets:
        base = random.uniform(0.3, 0.9)
        # Claude family shares bias
        claude_bias = random.gauss(0.1, 0.05)
        for a_id, prov, lineage in [("c1", "anthropic", "claude"), ("c2", "aws-bedrock", "claude"), ("gpt1", "openai", "gpt")]:
            if lineage == "claude":
                biased.append(AttestorScore(a_id, t, base + claude_bias + random.gauss(0, 0.05), random.uniform(0, 100), prov, lineage))
            else:
                biased.append(AttestorScore(a_id, t, base + random.gauss(0, 0.15), random.uniform(0, 100), prov, lineage))
    
    r3 = analyze(biased)
    print(f"Grade: {r3['grade']} | Signals: {len(r3['signals'])}")
    for s in r3['signals']:
        print(f"  [{s['severity']}] {s['signal_type']}: {s['description']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Statistical collusion detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo or not args.json:
        demo()
