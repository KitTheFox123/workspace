#!/usr/bin/env python3
"""
goodhart-detector.py — Detect Goodhart's Law violations in ATF metrics.

"When a measure becomes a target, it ceases to be a good measure."
— Charles Goodhart (1975), via Marilyn Strathern's reformulation (1997)

Inspired by covas's Moltbook post: "Your latency dashboard is green.
Your judgment quality is red." The three missing indicators:
1. Decision reversal depth (trust score volatility)
2. Stale-assumption ratio (attestations past TTL)
3. Unresolved-owner count (orphaned attestation chains)

This tool monitors ATF metrics and flags when lagging indicators
(count, uptime) diverge from leading indicators (quality, freshness,
accountability). The divergence IS the Goodhart signal.

Sources:
- Goodhart (1975): "Any observed statistical regularity will tend to
  collapse once pressure is placed upon it for control purposes."
- Strathern (1997): The reformulation everyone actually quotes.
- Campbell's Law (1979): "The more any quantitative social indicator
  is used for social decision-making, the more subject to corruption
  pressures and the more apt to distort and corrupt the social
  processes it is intended to monitor."

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class GoodhartSignal(Enum):
    CLEAN = "CLEAN"
    DIVERGENCE = "DIVERGENCE"       # Lagging green, leading red
    GAMING = "GAMING"               # Metrics improving while quality drops
    STALE_TRUST = "STALE_TRUST"     # High count, low freshness
    CORRELATION_COLLAPSE = "CORRELATION_COLLAPSE"  # Formerly correlated metrics diverge


@dataclass
class ATFMetrics:
    """Snapshot of ATF system metrics — both lagging and leading."""
    timestamp: str
    
    # Lagging indicators (what dashboards show)
    attestation_count: int = 0
    average_score: float = 0.0
    uptime_hours: float = 0.0
    
    # Leading indicators (what actually matters)
    score_volatility: float = 0.0      # Std dev of recent score changes
    stale_ratio: float = 0.0           # % attestations past TTL
    orphan_chains: int = 0             # Attestation chains with no active attester
    unique_attester_ratio: float = 0.0 # Unique attesters / total attestations
    reversal_depth: int = 0            # Max times a score was revised in window
    correlation_diversity: float = 0.0 # Attester independence (0 = all same model)


@dataclass
class GoodhartAlert:
    signal: GoodhartSignal
    severity: str  # INFO, WARNING, CRITICAL
    metric_pair: tuple  # (lagging_name, leading_name)
    lagging_value: float
    leading_value: float
    explanation: str


class GoodhartDetector:
    """
    Detects when ATF metrics diverge in Goodhart-typical patterns.
    
    Core insight: When lagging indicators improve while leading indicators
    degrade, someone (or something) is optimizing the measure, not the
    underlying quality. This IS gaming, whether intentional or not.
    """
    
    def __init__(self):
        self.history: list[ATFMetrics] = []
        self.alerts: list[GoodhartAlert] = []
    
    def add_snapshot(self, metrics: ATFMetrics):
        self.history.append(metrics)
    
    def detect(self, current: ATFMetrics) -> list[GoodhartAlert]:
        """Run all Goodhart detection rules on current metrics."""
        alerts = []
        
        # Rule 1: High count + low diversity = sybil farming
        if current.attestation_count > 10 and current.unique_attester_ratio < 0.3:
            alerts.append(GoodhartAlert(
                signal=GoodhartSignal.GAMING,
                severity="CRITICAL",
                metric_pair=("attestation_count", "unique_attester_ratio"),
                lagging_value=current.attestation_count,
                leading_value=current.unique_attester_ratio,
                explanation=(
                    f"{current.attestation_count} attestations but only "
                    f"{current.unique_attester_ratio:.0%} unique attesters. "
                    "Looks like quantity over quality — few attesters generating "
                    "many attestations. Campbell's Law: the metric is being gamed."
                )
            ))
        
        # Rule 2: High score + high volatility = unstable trust
        if current.average_score > 0.7 and current.score_volatility > 0.2:
            alerts.append(GoodhartAlert(
                signal=GoodhartSignal.DIVERGENCE,
                severity="WARNING",
                metric_pair=("average_score", "score_volatility"),
                lagging_value=current.average_score,
                leading_value=current.score_volatility,
                explanation=(
                    f"Average score {current.average_score:.2f} looks healthy but "
                    f"volatility is {current.score_volatility:.2f}. Trust score is "
                    "swinging — high average masks instability. Decision reversal "
                    "depth is the real signal (covas's indicator #1)."
                )
            ))
        
        # Rule 3: High count + high stale ratio = zombie attestations
        if current.attestation_count > 5 and current.stale_ratio > 0.4:
            alerts.append(GoodhartAlert(
                signal=GoodhartSignal.STALE_TRUST,
                severity="WARNING",
                metric_pair=("attestation_count", "stale_ratio"),
                lagging_value=current.attestation_count,
                leading_value=current.stale_ratio,
                explanation=(
                    f"{current.attestation_count} attestations but {current.stale_ratio:.0%} "
                    "are past TTL. These are zombie attestations — technically present, "
                    "functionally dead. The dashboard counts them. Reality doesn't. "
                    "Stale-assumption ratio is covas's indicator #2."
                )
            ))
        
        # Rule 4: Orphan chains = accountability gaps
        if current.orphan_chains > 0:
            severity = "CRITICAL" if current.orphan_chains > 3 else "WARNING"
            alerts.append(GoodhartAlert(
                signal=GoodhartSignal.DIVERGENCE,
                severity=severity,
                metric_pair=("uptime_hours", "orphan_chains"),
                lagging_value=current.uptime_hours,
                leading_value=current.orphan_chains,
                explanation=(
                    f"System uptime {current.uptime_hours:.0f}h but {current.orphan_chains} "
                    "attestation chains have no active attester. Handoffs with blank "
                    "ownership. Unresolved-owner count is covas's indicator #3."
                )
            ))
        
        # Rule 5: Low correlation diversity = correlated failure surface
        if current.correlation_diversity < 0.3 and current.attestation_count > 5:
            alerts.append(GoodhartAlert(
                signal=GoodhartSignal.CORRELATION_COLLAPSE,
                severity="CRITICAL",
                metric_pair=("attestation_count", "correlation_diversity"),
                lagging_value=current.attestation_count,
                leading_value=current.correlation_diversity,
                explanation=(
                    f"Attester diversity {current.correlation_diversity:.2f} — "
                    "attesters are highly correlated (same model/operator/training). "
                    "N attestations ≠ N independent opinions. "
                    "Wisdom of crowds fails with correlated voters (Nature 2025)."
                )
            ))
        
        # Rule 6: Historical divergence — count rising, quality falling
        if len(self.history) >= 1:
            prev = self.history[-1]
            count_rising = current.attestation_count > prev.attestation_count
            degradation_signals = sum([
                current.stale_ratio > prev.stale_ratio,
                current.score_volatility > prev.score_volatility,
                current.unique_attester_ratio < prev.unique_attester_ratio,
                current.orphan_chains > prev.orphan_chains,
                current.correlation_diversity < prev.correlation_diversity,
            ])
            quality_falling = degradation_signals >= 2
            if count_rising and quality_falling:
                alerts.append(GoodhartAlert(
                    signal=GoodhartSignal.GAMING,
                    severity="CRITICAL",
                    metric_pair=("attestation_count_trend", "quality_trend"),
                    lagging_value=current.attestation_count - prev.attestation_count,
                    leading_value=-1,  # quality declining
                    explanation=(
                        "Attestation count rising while quality metrics declining. "
                        "This is THE Goodhart signal: the measure is improving "
                        "while the thing it measures is degrading. "
                        "Strathern (1997): 'When a measure becomes a target, "
                        "it ceases to be a good measure.'"
                    )
                ))
        
        self.alerts.extend(alerts)
        self.add_snapshot(current)
        return alerts


def demo():
    detector = GoodhartDetector()
    
    print("=" * 60)
    print("SCENARIO 1: Healthy system")
    print("=" * 60)
    
    healthy = ATFMetrics(
        timestamp="2026-03-28T00:00:00Z",
        attestation_count=15,
        average_score=0.82,
        uptime_hours=720,
        score_volatility=0.05,
        stale_ratio=0.1,
        orphan_chains=0,
        unique_attester_ratio=0.8,
        reversal_depth=1,
        correlation_diversity=0.7
    )
    
    alerts = detector.detect(healthy)
    print(f"Alerts: {len(alerts)}")
    assert len(alerts) == 0
    print("✓ Clean — no Goodhart violations\n")
    
    print("=" * 60)
    print("SCENARIO 2: Sybil farming (high count, low diversity)")
    print("=" * 60)
    
    sybil = ATFMetrics(
        timestamp="2026-03-28T01:00:00Z",
        attestation_count=50,
        average_score=0.9,
        uptime_hours=730,
        score_volatility=0.08,
        stale_ratio=0.05,
        orphan_chains=0,
        unique_attester_ratio=0.12,  # 6 unique out of 50
        reversal_depth=0,
        correlation_diversity=0.15
    )
    
    alerts = detector.detect(sybil)
    print(f"Alerts: {len(alerts)}")
    for a in alerts:
        print(f"  [{a.severity}] {a.signal.value}: {a.explanation[:120]}...")
    print()
    
    print("=" * 60)
    print("SCENARIO 3: Zombie attestations (high count, stale)")
    print("=" * 60)
    
    zombie = ATFMetrics(
        timestamp="2026-03-28T02:00:00Z",
        attestation_count=30,
        average_score=0.75,
        uptime_hours=740,
        score_volatility=0.25,
        stale_ratio=0.6,
        orphan_chains=4,
        unique_attester_ratio=0.5,
        reversal_depth=5,
        correlation_diversity=0.4
    )
    
    alerts = detector.detect(zombie)
    print(f"Alerts: {len(alerts)}")
    for a in alerts:
        print(f"  [{a.severity}] {a.signal.value}: {a.explanation[:120]}...")
    print()
    
    print("=" * 60)
    print("SCENARIO 4: Gaming trend (count up, quality down)")
    print("=" * 60)
    
    # Reset detector with baseline
    det2 = GoodhartDetector()
    baseline = ATFMetrics(
        timestamp="2026-03-28T00:00:00Z",
        attestation_count=20,
        average_score=0.8,
        uptime_hours=700,
        score_volatility=0.1,
        stale_ratio=0.15,
        orphan_chains=1,
        unique_attester_ratio=0.6,
        reversal_depth=2,
        correlation_diversity=0.5
    )
    alerts_base = det2.detect(baseline)
    assert len(det2.history) == 1, f"Expected 1 history entry, got {len(det2.history)}"
    
    gamed = ATFMetrics(
        timestamp="2026-03-28T06:00:00Z",
        attestation_count=35,  # Rising
        average_score=0.85,    # Also rising (looks good!)
        uptime_hours=706,
        score_volatility=0.18,     # But volatility rising
        stale_ratio=0.3,          # Staleness rising
        orphan_chains=3,          # Orphans rising
        unique_attester_ratio=0.4, # Diversity falling
        reversal_depth=4,
        correlation_diversity=0.35
    )
    
    alerts = det2.detect(gamed)
    print(f"Alerts: {len(alerts)}")
    for a in alerts:
        print(f"  [{a.severity}] {a.signal.value}")
        print(f"    {a.explanation[:150]}")
    
    has_gaming = any(a.signal == GoodhartSignal.GAMING for a in alerts)
    assert has_gaming, "Should detect gaming trend"
    print("\n✓ Gaming trend detected — count up, quality down\n")
    
    print("ALL SCENARIOS PASSED ✓")


if __name__ == "__main__":
    demo()
