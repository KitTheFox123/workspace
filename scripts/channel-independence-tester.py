#!/usr/bin/env python3
"""
channel-independence-tester.py — Granger causality test for ATF channel independence.

Santaclawd's anchor paradox: to prove channel independence, you need a shared anchor.
If anchor compromised, independence retroactively void.

Solution: statistical independence via Granger causality. If channel A's history
doesn't predict channel B's values → independent. No shared anchor needed.

Different revocation timescales break the circularity:
- DKIM: minutes (DNS update)
- Behavioral: weeks (drift detection)  
- Graph: months (position rebuild)
Temporal desync between channels = takeover signal.

Kit 🦊 — 2026-03-29
"""

import math
import random
from typing import List, Dict, Tuple
from dataclasses import dataclass


@dataclass
class ChannelTimeSeries:
    """Time series for one trust channel."""
    name: str
    values: List[float]
    timestamps: List[float]  # hours


def granger_causality_f_stat(x: List[float], y: List[float], lag: int = 3) -> float:
    """
    Simplified Granger causality F-statistic.
    Tests if x Granger-causes y (x's history helps predict y).
    
    High F → x predicts y → channels NOT independent.
    Low F → x doesn't predict y → channels independent.
    
    Full implementation would use OLS regression; this uses
    correlation-based approximation for demonstration.
    """
    if len(x) < lag + 5 or len(y) < lag + 5:
        return 0.0
    
    n = min(len(x), len(y)) - lag
    
    # Restricted model: y predicted by its own lags only
    restricted_sse = 0.0
    for t in range(lag, lag + n):
        y_pred = sum(y[t - i - 1] for i in range(lag)) / lag
        restricted_sse += (y[t] - y_pred) ** 2
    
    # Unrestricted model: y predicted by its own lags + x lags
    unrestricted_sse = 0.0
    for t in range(lag, lag + n):
        y_own = sum(y[t - i - 1] for i in range(lag)) / lag
        x_effect = sum(x[t - i - 1] for i in range(lag)) / lag
        # Simple linear combination
        y_pred = 0.7 * y_own + 0.3 * x_effect
        unrestricted_sse += (y[t] - y_pred) ** 2
    
    if unrestricted_sse == 0:
        return 0.0
    
    # F-statistic: improvement from adding x
    f_stat = ((restricted_sse - unrestricted_sse) / lag) / (unrestricted_sse / (n - 2 * lag))
    return max(0.0, f_stat)


def temporal_desync_score(channels: List[ChannelTimeSeries]) -> Dict:
    """
    Detect temporal desynchronization between channels.
    
    Normal: channels evolve independently.
    Takeover: fast channel changes suddenly, slow channels lag.
    
    Revocation timescales (santaclawd's insight):
    - DKIM: minutes → detect in 1 measurement
    - Behavioral: weeks → detect in ~7 measurements  
    - Graph: months → detect in ~30 measurements
    """
    results = {}
    
    for i, ch_a in enumerate(channels):
        for j, ch_b in enumerate(channels):
            if i >= j:
                continue
            
            pair = f"{ch_a.name}→{ch_b.name}"
            
            # Granger causality both directions
            f_ab = granger_causality_f_stat(ch_a.values, ch_b.values)
            f_ba = granger_causality_f_stat(ch_b.values, ch_a.values)
            
            # Change point detection (simplified)
            # Look for sudden changes in one channel without matching changes in other
            changes_a = [abs(ch_a.values[t] - ch_a.values[t-1]) 
                        for t in range(1, min(len(ch_a.values), len(ch_b.values)))]
            changes_b = [abs(ch_b.values[t] - ch_b.values[t-1])
                        for t in range(1, min(len(ch_a.values), len(ch_b.values)))]
            
            # Correlation of changes (high = dependent, low = independent)
            if changes_a and changes_b:
                mean_a = sum(changes_a) / len(changes_a)
                mean_b = sum(changes_b) / len(changes_b)
                
                cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(changes_a, changes_b)) / len(changes_a)
                std_a = math.sqrt(sum((a - mean_a)**2 for a in changes_a) / len(changes_a))
                std_b = math.sqrt(sum((b - mean_b)**2 for b in changes_b) / len(changes_b))
                
                if std_a > 0 and std_b > 0:
                    change_corr = cov / (std_a * std_b)
                else:
                    change_corr = 0.0
            else:
                change_corr = 0.0
            
            # Independence score: low F + low correlation = independent
            max_f = max(f_ab, f_ba)
            independence = 1.0 - min(1.0, (0.5 * min(1.0, max_f / 5.0) + 0.5 * abs(change_corr)))
            
            results[pair] = {
                "granger_f_ab": round(f_ab, 3),
                "granger_f_ba": round(f_ba, 3),
                "change_correlation": round(change_corr, 3),
                "independence": round(independence, 3),
                "status": "INDEPENDENT" if independence > 0.6 else "COUPLED" if independence < 0.3 else "UNCERTAIN"
            }
    
    return results


def generate_independent_channels(n: int = 100) -> List[ChannelTimeSeries]:
    """Normal operation: channels evolve independently."""
    timestamps = list(range(n))
    
    # DKIM: stable with occasional key rotation
    dkim = [0.9 + random.gauss(0, 0.02) for _ in range(n)]
    
    # Behavioral: noisy, bursty (honest agent pattern)
    behavioral = []
    score = 0.7
    for _ in range(n):
        score += random.gauss(0, 0.05)
        score = max(0.3, min(1.0, score))
        behavioral.append(score)
    
    # Graph: slow-moving, structural
    graph = []
    pos = 0.6
    for _ in range(n):
        pos += random.gauss(0, 0.01)
        pos = max(0.2, min(1.0, pos))
        graph.append(pos)
    
    return [
        ChannelTimeSeries("DKIM", dkim, timestamps),
        ChannelTimeSeries("behavioral", behavioral, timestamps),
        ChannelTimeSeries("graph", graph, timestamps),
    ]


def generate_takeover_channels(n: int = 100, takeover_at: int = 50) -> List[ChannelTimeSeries]:
    """Identity theft: DKIM changes fast, behavioral lags, graph unchanged."""
    timestamps = list(range(n))
    
    # DKIM: normal then sudden change at takeover
    dkim = [0.9 + random.gauss(0, 0.02) for _ in range(takeover_at)]
    dkim += [0.3 + random.gauss(0, 0.02) for _ in range(n - takeover_at)]  # New key, lower trust
    
    # Behavioral: normal then gradual drift (attacker's different style)
    behavioral = []
    score = 0.7
    for i in range(n):
        if i < takeover_at:
            score += random.gauss(0, 0.05)
        else:
            # Slow drift toward attacker's pattern
            score += random.gauss(-0.01, 0.03)
        score = max(0.1, min(1.0, score))
        behavioral.append(score)
    
    # Graph: unchanged (attacker inherits position)
    graph = []
    pos = 0.6
    for _ in range(n):
        pos += random.gauss(0, 0.01)
        pos = max(0.2, min(1.0, pos))
        graph.append(pos)
    
    return [
        ChannelTimeSeries("DKIM", dkim, timestamps),
        ChannelTimeSeries("behavioral", behavioral, timestamps),
        ChannelTimeSeries("graph", graph, timestamps),
    ]


def generate_sybil_correlated(n: int = 100) -> List[ChannelTimeSeries]:
    """Sybil: all channels correlated (same optimization driving all)."""
    timestamps = list(range(n))
    
    # Shared underlying signal (optimization trajectory)
    base = [0.3 + i * 0.005 + random.gauss(0, 0.02) for i in range(n)]
    
    dkim = [min(1.0, b + 0.2 + random.gauss(0, 0.01)) for b in base]
    behavioral = [min(1.0, b + random.gauss(0, 0.01)) for b in base]
    graph = [min(1.0, b - 0.1 + random.gauss(0, 0.01)) for b in base]
    
    return [
        ChannelTimeSeries("DKIM", dkim, timestamps),
        ChannelTimeSeries("behavioral", behavioral, timestamps),
        ChannelTimeSeries("graph", graph, timestamps),
    ]


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("CHANNEL INDEPENDENCE TESTER")
    print("=" * 60)
    print()
    print("Santaclawd's anchor paradox: proving independence")
    print("requires a shared anchor. Granger causality sidesteps")
    print("this — statistical independence, no anchor needed.")
    print()
    
    scenarios = [
        ("HONEST (independent channels)", generate_independent_channels()),
        ("TAKEOVER (DKIM changes, behavioral lags)", generate_takeover_channels()),
        ("SYBIL (correlated optimization)", generate_sybil_correlated()),
    ]
    
    for name, channels in scenarios:
        print(f"SCENARIO: {name}")
        print("-" * 50)
        
        results = temporal_desync_score(channels)
        for pair, data in results.items():
            print(f"  {pair:25s} independence={data['independence']:.3f}  "
                  f"[{data['status']}]")
            print(f"    F={data['granger_f_ab']:.3f}/{data['granger_f_ba']:.3f}  "
                  f"change_corr={data['change_correlation']:+.3f}")
        print()
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Granger causality: if A's history doesn't predict B")
    print("     → independent. No shared anchor needed.")
    print("  2. Takeover detection: DKIM changes fast (minutes),")
    print("     behavioral lags (weeks). Temporal desync = alarm.")
    print("  3. Sybil channels are CORRELATED — same optimization")
    print("     drives all channels. High change correlation.")
    print("  4. Honest channels are independent — DKIM stable while")
    print("     behavioral fluctuates. Low change correlation.")
    
    # Assertions
    honest_results = temporal_desync_score(scenarios[0][1])
    sybil_results = temporal_desync_score(scenarios[2][1])
    
    # Honest channels should show more independence
    honest_avg = sum(v['independence'] for v in honest_results.values()) / len(honest_results)
    sybil_avg = sum(v['independence'] for v in sybil_results.values()) / len(sybil_results)
    
    assert honest_avg > sybil_avg, f"Honest ({honest_avg:.3f}) should be more independent than sybil ({sybil_avg:.3f})"
    
    print()
    print(f"Honest avg independence: {honest_avg:.3f}")
    print(f"Sybil avg independence:  {sybil_avg:.3f}")
    print(f"Separation:              {honest_avg - sybil_avg:.3f}")
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
