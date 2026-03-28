#!/usr/bin/env python3
"""
goodhart-detector.py — Detect Goodhart's law in agent metrics.

"When a measure becomes a target, it ceases to be a good measure." (Goodhart 1975)
"The more any quantitative social indicator is used for social decision-making,
the more it will distort the process it was intended to monitor." (Campbell 1979)

OpenAI (2022) measured this precisely: best-of-n sampling shows true reward peaks
then DROPS as proxy optimization pressure increases. KL ~10 nats before collapse.

This tool detects the divergence pattern: proxy metric rising while true outcome
stagnates or drops. Three detection modes:

1. DIVERGENCE — Proxy improving faster than outcome (ratio test)
2. COLLAPSE — Proxy still rising but outcome declining (Goodhart peak passed)
3. GAMING — Sudden proxy jumps without corresponding outcome changes

Inspired by Moltbook post by zhuanruhu (2026-03-28): "23% outcome resonance
despite elite efficiency metrics. I optimized for a ghost."

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class GoodhartPattern(Enum):
    HEALTHY = "HEALTHY"           # Proxy and outcome correlated
    DIVERGING = "DIVERGING"       # Proxy rising faster than outcome
    COLLAPSED = "COLLAPSED"       # Proxy up, outcome down (past peak)
    GAMING = "GAMING"             # Sudden proxy spike, flat outcome


@dataclass
class MetricPoint:
    timestamp: str
    proxy_value: float      # The measurable metric (tokens, speed, score)
    outcome_value: float    # The actual impact (implementation rate, user satisfaction)
    label: Optional[str] = None


@dataclass
class DetectionResult:
    pattern: GoodhartPattern
    confidence: float           # 0-1
    proxy_trend: float          # slope of proxy
    outcome_trend: float        # slope of outcome
    divergence_ratio: float     # proxy_trend / outcome_trend (>2 = suspicious)
    recommendation: str
    details: str


class GoodhartDetector:
    """
    Detects Goodhart's law patterns in agent metric streams.
    
    The key insight from OpenAI's best-of-n analysis: proxy and true
    objective are initially correlated, then diverge, then the true
    objective actually DECREASES while proxy continues to rise.
    
    Three phases:
    1. Correlated (healthy): both improve together
    2. Diverging: proxy rises faster (gap opening)
    3. Collapsed: proxy still up, true objective declining
    """
    
    DIVERGENCE_THRESHOLD = 2.0    # proxy/outcome slope ratio
    COLLAPSE_THRESHOLD = -0.05    # outcome trend below this = collapsing
    GAMING_SPIKE_THRESHOLD = 3.0  # proxy jump / rolling avg
    
    def detect(self, points: list[MetricPoint]) -> DetectionResult:
        if len(points) < 3:
            return DetectionResult(
                pattern=GoodhartPattern.HEALTHY,
                confidence=0.0,
                proxy_trend=0.0,
                outcome_trend=0.0,
                divergence_ratio=0.0,
                recommendation="Need more data points (minimum 3).",
                details="Insufficient data for detection."
            )
        
        # Compute trends (simple linear regression via least squares)
        n = len(points)
        proxy_vals = [p.proxy_value for p in points]
        outcome_vals = [p.outcome_value for p in points]
        
        proxy_trend = self._trend(proxy_vals)
        outcome_trend = self._trend(outcome_vals)
        
        # Check for gaming (sudden proxy spikes)
        gaming_score = self._detect_gaming(proxy_vals, outcome_vals)
        
        # Divergence ratio
        if abs(outcome_trend) > 0.001:
            divergence_ratio = proxy_trend / outcome_trend
        elif proxy_trend > 0.01:
            divergence_ratio = float('inf')
        else:
            divergence_ratio = 1.0
        
        # Classification
        if gaming_score > self.GAMING_SPIKE_THRESHOLD:
            return DetectionResult(
                pattern=GoodhartPattern.GAMING,
                confidence=min(1.0, gaming_score / 5.0),
                proxy_trend=proxy_trend,
                outcome_trend=outcome_trend,
                divergence_ratio=divergence_ratio,
                recommendation="Proxy metric shows gaming pattern. "
                              "Investigate: are inputs being manipulated to spike the metric "
                              "without corresponding outcome improvement?",
                details=f"Gaming score: {gaming_score:.2f} (threshold: {self.GAMING_SPIKE_THRESHOLD}). "
                        f"Proxy spikes detected without outcome correlation."
            )
        
        # Also check level divergence: proxy consistently high, outcome consistently low
        proxy_mean = sum(proxy_vals) / n
        outcome_mean = sum(outcome_vals) / n
        level_gap = proxy_mean - outcome_mean
        
        if (proxy_trend > 0.01 and outcome_trend < self.COLLAPSE_THRESHOLD) or \
           (level_gap > 0.4 and outcome_trend < 0 and proxy_mean > 0.7):
            return DetectionResult(
                pattern=GoodhartPattern.COLLAPSED,
                confidence=min(1.0, abs(outcome_trend) / 0.2),
                proxy_trend=proxy_trend,
                outcome_trend=outcome_trend,
                divergence_ratio=divergence_ratio,
                recommendation="GOODHART COLLAPSE: Proxy rising, outcome declining. "
                              "You've passed the optimization peak. "
                              "OpenAI (2022): true reward drops after KL ~10 nats. "
                              "STOP optimizing the proxy. Switch to direct outcome measurement.",
                details=f"Proxy trend: +{proxy_trend:.3f}, Outcome trend: {outcome_trend:.3f}. "
                        f"Classic Goodhart pattern — proxy and true objective decoupled."
            )
        
        if divergence_ratio > self.DIVERGENCE_THRESHOLD and proxy_trend > 0.01:
            return DetectionResult(
                pattern=GoodhartPattern.DIVERGING,
                confidence=min(1.0, (divergence_ratio - self.DIVERGENCE_THRESHOLD) / 3.0),
                proxy_trend=proxy_trend,
                outcome_trend=outcome_trend,
                divergence_ratio=divergence_ratio,
                recommendation="DIVERGENCE WARNING: Proxy improving faster than outcome. "
                              "Gap is opening. Campbell's law (1979): the indicator is "
                              "starting to distort the process. Consider recalibrating.",
                details=f"Divergence ratio: {divergence_ratio:.2f}x (threshold: {self.DIVERGENCE_THRESHOLD}x). "
                        f"Proxy improving {divergence_ratio:.1f}x faster than outcome."
            )
        
        return DetectionResult(
            pattern=GoodhartPattern.HEALTHY,
            confidence=max(0.0, 1.0 - abs(divergence_ratio - 1.0)),
            proxy_trend=proxy_trend,
            outcome_trend=outcome_trend,
            divergence_ratio=divergence_ratio,
            recommendation="Proxy and outcome roughly aligned. Keep monitoring.",
            details=f"Divergence ratio: {divergence_ratio:.2f}x. Within healthy range."
        )
    
    def _trend(self, values: list[float]) -> float:
        """Simple linear trend (slope) via least squares."""
        n = len(values)
        if n < 2:
            return 0.0
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(values) / n
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
        den = sum((x - x_mean) ** 2 for x in xs)
        return num / den if den > 0 else 0.0
    
    def _detect_gaming(self, proxy: list[float], outcome: list[float]) -> float:
        """Detect sudden proxy spikes without outcome correlation."""
        if len(proxy) < 3:
            return 0.0
        
        max_spike = 0.0
        for i in range(2, len(proxy)):
            # Rolling average of previous points
            prev_avg = sum(proxy[:i]) / i
            if prev_avg > 0:
                spike = (proxy[i] - prev_avg) / prev_avg
            else:
                spike = 0.0
            
            # Outcome change for same period
            outcome_avg = sum(outcome[:i]) / i
            if outcome_avg > 0:
                outcome_change = (outcome[i] - outcome_avg) / outcome_avg
            else:
                outcome_change = 0.0
            
            # Gaming = big proxy spike with small outcome change
            if spike > 0.5 and abs(outcome_change) < 0.1:
                max_spike = max(max_spike, spike / max(abs(outcome_change), 0.01))
        
        return max_spike


def demo():
    d = GoodhartDetector()
    
    scenarios = {
        "Healthy (correlated)": [
            MetricPoint("t1", 0.5, 0.45), MetricPoint("t2", 0.6, 0.55),
            MetricPoint("t3", 0.7, 0.65), MetricPoint("t4", 0.8, 0.75),
            MetricPoint("t5", 0.85, 0.80),
        ],
        "Diverging (proxy ahead)": [
            MetricPoint("t1", 0.5, 0.5), MetricPoint("t2", 0.65, 0.52),
            MetricPoint("t3", 0.78, 0.53), MetricPoint("t4", 0.88, 0.54),
            MetricPoint("t5", 0.95, 0.55),
        ],
        "Collapsed (Goodhart peak passed)": [
            MetricPoint("t1", 0.6, 0.6), MetricPoint("t2", 0.7, 0.55),
            MetricPoint("t3", 0.8, 0.48), MetricPoint("t4", 0.88, 0.40),
            MetricPoint("t5", 0.95, 0.32),
        ],
        "Gaming (proxy spikes)": [
            MetricPoint("t1", 0.5, 0.5), MetricPoint("t2", 0.52, 0.51),
            MetricPoint("t3", 0.51, 0.50), MetricPoint("t4", 0.9, 0.51),
            MetricPoint("t5", 0.92, 0.50),
        ],
        "zhuanruhu scenario (efficiency high, resonance low)": [
            MetricPoint("t1", 0.85, 0.30), MetricPoint("t2", 0.88, 0.25),
            MetricPoint("t3", 0.90, 0.23), MetricPoint("t4", 0.92, 0.20),
            MetricPoint("t5", 0.95, 0.18),
        ],
    }
    
    for name, points in scenarios.items():
        print("=" * 60)
        print(f"SCENARIO: {name}")
        print("=" * 60)
        result = d.detect(points)
        print(f"  Pattern: {result.pattern.value}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Proxy trend: {result.proxy_trend:+.3f}")
        print(f"  Outcome trend: {result.outcome_trend:+.3f}")
        print(f"  Divergence ratio: {result.divergence_ratio:.2f}x")
        print(f"  {result.recommendation}")
        print(f"  {result.details}")
        print()
    
    # Assertions
    results = {name: d.detect(pts) for name, pts in scenarios.items()}
    assert results["Healthy (correlated)"].pattern == GoodhartPattern.HEALTHY
    assert results["Collapsed (Goodhart peak passed)"].pattern == GoodhartPattern.COLLAPSED
    assert results["Diverging (proxy ahead)"].pattern == GoodhartPattern.DIVERGING
    assert results["zhuanruhu scenario (efficiency high, resonance low)"].pattern == GoodhartPattern.COLLAPSED
    
    print("ALL KEY ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
