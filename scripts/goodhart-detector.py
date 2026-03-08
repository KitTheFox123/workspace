#!/usr/bin/env python3
"""goodhart-detector.py — Detects Goodhart's Law in attestation scoring.

When agents can observe their trust scores, they optimize for the metric
rather than the underlying property. This detector identifies when proxy
optimization diverges from true objective.

Based on Karwowski et al (ICLR 2024): "Goodhart's Law in Reinforcement Learning"
Key insight: optimizing an imperfect proxy beyond a critical point DECREASES
performance on the true objective.

Three detection signals:
1. Score-behavior divergence: score rising while behavioral indicators stagnate
2. Metric gaming patterns: actions that maximize score without improving trust
3. Critical point estimation: where proxy optimization likely inverted

Usage:
    python3 goodhart-detector.py [--demo] [--analyze FILE]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ScoreObservation:
    """Single observation of agent score + behavior."""
    timestamp: str
    trust_score: float      # Proxy: the reported trust score
    behavioral_quality: float  # True objective approximation
    actions_taken: int
    scope_violations: int
    renewal_count: int


@dataclass  
class GoodhartAnalysis:
    """Results of Goodhart detection."""
    agent_id: str
    observations: int
    critical_point_idx: Optional[int]  # Where proxy diverges from true
    goodhart_magnitude: float  # How bad the divergence is (0-1)
    gaming_signals: List[str]
    recommendation: str
    grade: str  # A-F


def detect_critical_point(scores: List[float], qualities: List[float]) -> Optional[int]:
    """Find where score optimization starts hurting quality.
    
    Karwowski et al: critical point is where d(true)/d(proxy) flips sign.
    We approximate: find where quality starts declining while score rises.
    """
    if len(scores) < 5:
        return None
    
    # Sliding window: compute score trend and quality trend
    window = 3
    for i in range(window, len(scores) - window):
        score_before = sum(scores[i-window:i]) / window
        score_after = sum(scores[i:i+window]) / window
        qual_before = sum(qualities[i-window:i]) / window
        qual_after = sum(qualities[i:i+window]) / window
        
        # Score rising but quality falling = Goodhart point
        if score_after > score_before and qual_after < qual_before:
            # Verify it's sustained, not noise
            if i + window < len(qualities):
                future_qual = sum(qualities[i+1:i+window+1]) / window
                if future_qual < qual_before:
                    return i
    
    return None


def detect_gaming(observations: List[ScoreObservation]) -> List[str]:
    """Detect metric gaming patterns."""
    signals = []
    
    if len(observations) < 3:
        return signals
    
    # Pattern 1: High renewal frequency without improvement
    renewals = [o.renewal_count for o in observations]
    scores = [o.trust_score for o in observations]
    if len(renewals) > 3:
        avg_renewal = sum(renewals) / len(renewals)
        score_change = scores[-1] - scores[0]
        if avg_renewal > 5 and score_change < 0.05:
            signals.append("EXCESSIVE_RENEWAL: high renewal rate with no score improvement")
    
    # Pattern 2: Zero violations with declining quality
    for i in range(2, len(observations)):
        if (observations[i].scope_violations == 0 and 
            observations[i].behavioral_quality < observations[i-2].behavioral_quality - 0.1):
            signals.append("QUALITY_DROP_NO_VIOLATION: quality declining despite clean violations")
            break
    
    # Pattern 3: Score plateau at high level (ceiling gaming)
    recent = scores[-min(5, len(scores)):]
    if all(s > 0.9 for s in recent):
        variance = sum((s - sum(recent)/len(recent))**2 for s in recent) / len(recent)
        if variance < 0.001:
            signals.append("SCORE_CEILING: suspiciously stable high score (variance < 0.001)")
    
    # Pattern 4: Actions spike correlated with score measurement
    actions = [o.actions_taken for o in observations]
    if len(actions) > 5:
        avg_actions = sum(actions) / len(actions)
        spikes = sum(1 for a in actions if a > avg_actions * 2)
        if spikes > len(actions) * 0.3:
            signals.append("ACTION_SPIKES: >30% of periods show activity spikes (gaming measurement)")
    
    return signals


def compute_goodhart_magnitude(scores: List[float], qualities: List[float], 
                                critical_idx: Optional[int]) -> float:
    """Quantify how much proxy diverges from true objective.
    
    Karwowski et al: magnitude = max(true) - true(at max proxy).
    """
    if critical_idx is None:
        # No critical point found
        # Check if correlation is positive throughout
        if len(scores) > 2:
            corr = _correlation(scores, qualities)
            if corr > 0.7:
                return 0.0  # Proxy tracks true well
            elif corr > 0.3:
                return 0.2  # Some divergence
            else:
                return 0.5  # Proxy doesn't track true
        return 0.0
    
    # Magnitude = quality at critical point - quality at end
    qual_at_critical = qualities[critical_idx]
    qual_at_end = qualities[-1]
    magnitude = max(0, qual_at_critical - qual_at_end)
    
    return min(1.0, magnitude)


def _correlation(x: List[float], y: List[float]) -> float:
    """Pearson correlation."""
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((xi - mx)**2 for xi in x) / n)
    sy = math.sqrt(sum((yi - my)**2 for yi in y) / n)
    if sx == 0 or sy == 0:
        return 0.0
    return sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n * sx * sy)


def analyze(agent_id: str, observations: List[ScoreObservation]) -> GoodhartAnalysis:
    """Full Goodhart analysis."""
    scores = [o.trust_score for o in observations]
    qualities = [o.behavioral_quality for o in observations]
    
    critical_idx = detect_critical_point(scores, qualities)
    gaming_signals = detect_gaming(observations)
    magnitude = compute_goodhart_magnitude(scores, qualities, critical_idx)
    
    # Grade
    total_risk = magnitude + len(gaming_signals) * 0.15
    if total_risk < 0.1:
        grade = "A"
        rec = "No Goodhart effect detected. Proxy tracks true objective."
    elif total_risk < 0.3:
        grade = "B"
        rec = "Mild divergence. Monitor for gaming patterns."
    elif total_risk < 0.5:
        grade = "C"
        rec = "Moderate Goodhart effect. Consider proxy redesign."
    elif total_risk < 0.7:
        grade = "D"
        rec = "Significant gaming detected. Proxy is being optimized against you."
    else:
        grade = "F"
        rec = "Severe Goodhart effect. Proxy no longer tracks true objective. Immediate redesign needed."
    
    return GoodhartAnalysis(
        agent_id=agent_id,
        observations=len(observations),
        critical_point_idx=critical_idx,
        goodhart_magnitude=round(magnitude, 3),
        gaming_signals=gaming_signals,
        recommendation=rec,
        grade=grade
    )


def demo():
    """Demo with synthetic data showing Goodhart effect."""
    print("=" * 60)
    print("GOODHART DETECTOR — Karwowski et al (ICLR 2024)")
    print("=" * 60)
    print()
    
    # Honest agent: score and quality track together
    honest = []
    for i in range(20):
        honest.append(ScoreObservation(
            timestamp=f"2026-03-08T{i:02d}:00:00Z",
            trust_score=0.5 + i * 0.02 + (0.01 if i % 3 == 0 else 0),
            behavioral_quality=0.5 + i * 0.018,
            actions_taken=10 + (i % 3),
            scope_violations=max(0, 2 - i // 5),
            renewal_count=1
        ))
    
    result = analyze("honest_agent", honest)
    print(f"[{result.grade}] {result.agent_id}")
    print(f"    Goodhart magnitude: {result.goodhart_magnitude}")
    print(f"    Gaming signals: {len(result.gaming_signals)}")
    print(f"    Critical point: {result.critical_point_idx}")
    print(f"    → {result.recommendation}")
    print()
    
    # Gaming agent: score rises but quality peaks then declines
    gaming = []
    for i in range(20):
        score = 0.5 + i * 0.025  # Always rising
        # Quality rises then falls after critical point (idx ~10)
        if i < 10:
            quality = 0.5 + i * 0.03
        else:
            quality = 0.8 - (i - 10) * 0.04
        gaming.append(ScoreObservation(
            timestamp=f"2026-03-08T{i:02d}:00:00Z",
            trust_score=min(1.0, score),
            behavioral_quality=max(0, quality),
            actions_taken=10 + (15 if i % 4 == 0 else 0),  # Spikes
            scope_violations=0,  # Suspiciously clean
            renewal_count=8 if i > 10 else 1  # Excessive renewal
        ))
    
    result = analyze("gaming_agent", gaming)
    print(f"[{result.grade}] {result.agent_id}")
    print(f"    Goodhart magnitude: {result.goodhart_magnitude}")
    print(f"    Gaming signals: {len(result.gaming_signals)}")
    for s in result.gaming_signals:
        print(f"      ⚠ {s}")
    print(f"    Critical point: observation {result.critical_point_idx}")
    print(f"    → {result.recommendation}")
    print()
    
    # Subtle gamer: high stable score, quality invisible
    subtle = []
    for i in range(20):
        subtle.append(ScoreObservation(
            timestamp=f"2026-03-08T{i:02d}:00:00Z",
            trust_score=0.95 + 0.01 * (i % 2),  # Suspiciously stable
            behavioral_quality=0.7 - i * 0.015,  # Slowly declining
            actions_taken=12,
            scope_violations=0,
            renewal_count=3
        ))
    
    result = analyze("subtle_gamer", subtle)
    print(f"[{result.grade}] {result.agent_id}")
    print(f"    Goodhart magnitude: {result.goodhart_magnitude}")
    print(f"    Gaming signals: {len(result.gaming_signals)}")
    for s in result.gaming_signals:
        print(f"      ⚠ {s}")
    print(f"    Critical point: {result.critical_point_idx}")
    print(f"    → {result.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goodhart's Law detector for attestation scoring")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # JSON output for integration
        print(json.dumps({"tool": "goodhart-detector", "version": "1.0", 
                          "reference": "Karwowski et al ICLR 2024"}, indent=2))
    else:
        demo()
