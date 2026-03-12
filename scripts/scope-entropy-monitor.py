#!/usr/bin/env python3
"""Scope Entropy Monitor — Detect behavioral drift via Shannon entropy of scope_hash sequences.

santaclawd's insight: "measure entropy of scope_hash over time.
decreasing entropy = agent narrowing. increasing entropy = exploring beyond authorization."

Uses:
- Shannon entropy over sliding windows
- CUSUM (cumulative sum) for inflection point detection
- Entropy rate = change in entropy between windows

Based on:
- Shannon (1948) information theory
- Page (1954) CUSUM sequential analysis
- Identity Management Institute: behavioral drift detection (2024)

Kit 🦊 — 2026-02-28
"""

import math
from collections import Counter
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScopeEvent:
    timestamp: str
    scope_hash: str  # hash of authorized scope
    action_type: str  # what the agent actually did


def shannon_entropy(sequence: list[str]) -> float:
    """Shannon entropy of a discrete sequence."""
    if not sequence:
        return 0.0
    counts = Counter(sequence)
    total = len(sequence)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def windowed_entropy(events: list[ScopeEvent], window_size: int = 5) -> list[dict]:
    """Compute entropy over sliding windows."""
    results = []
    for i in range(len(events) - window_size + 1):
        window = events[i:i + window_size]
        scope_seq = [e.scope_hash for e in window]
        action_seq = [e.action_type for e in window]

        scope_ent = shannon_entropy(scope_seq)
        action_ent = shannon_entropy(action_seq)

        # Scope-action divergence: high action entropy + low scope entropy = exploring beyond auth
        divergence = max(0, action_ent - scope_ent)

        results.append({
            "window_start": window[0].timestamp,
            "window_end": window[-1].timestamp,
            "scope_entropy": round(scope_ent, 4),
            "action_entropy": round(action_ent, 4),
            "divergence": round(divergence, 4),
            "unique_scopes": len(set(scope_seq)),
            "unique_actions": len(set(action_seq)),
        })
    return results


def cusum_detect(values: list[float], threshold: float = 1.0, drift: float = 0.1) -> list[dict]:
    """CUSUM change point detection on entropy series."""
    if len(values) < 2:
        return []

    mean = sum(values) / len(values)
    s_pos = 0.0
    s_neg = 0.0
    alerts = []

    for i, v in enumerate(values):
        s_pos = max(0, s_pos + (v - mean) - drift)
        s_neg = max(0, s_neg - (v - mean) - drift)

        if s_pos > threshold:
            alerts.append({"index": i, "direction": "INCREASING", "cusum": round(s_pos, 4)})
            s_pos = 0.0
        if s_neg > threshold:
            alerts.append({"index": i, "direction": "DECREASING", "cusum": round(s_neg, 4)})
            s_neg = 0.0

    return alerts


def analyze_scope_drift(events: list[ScopeEvent], window_size: int = 5) -> dict:
    """Full analysis: entropy windows + CUSUM + classification."""
    windows = windowed_entropy(events, window_size)
    if not windows:
        return {"classification": "INSUFFICIENT_DATA", "grade": "N/A"}

    scope_entropies = [w["scope_entropy"] for w in windows]
    action_entropies = [w["action_entropy"] for w in windows]
    divergences = [w["divergence"] for w in windows]

    # CUSUM on action entropy (detect behavioral change)
    action_alerts = cusum_detect(action_entropies, threshold=0.8)

    # Trend: is entropy increasing or decreasing?
    if len(scope_entropies) >= 2:
        first_half = sum(scope_entropies[:len(scope_entropies)//2]) / (len(scope_entropies)//2)
        second_half = sum(scope_entropies[len(scope_entropies)//2:]) / (len(scope_entropies) - len(scope_entropies)//2)
        trend = second_half - first_half
    else:
        trend = 0.0

    avg_divergence = sum(divergences) / len(divergences)
    max_divergence = max(divergences)

    # Classification
    if avg_divergence > 0.5:
        classification = "SCOPE_VIOLATION"
        grade = "F"
        desc = "Actions consistently exceed authorized scope"
    elif avg_divergence > 0.2:
        classification = "DRIFT_DETECTED"
        grade = "D"
        desc = "Behavioral drift beyond scope boundaries"
    elif len(action_alerts) > 2:
        classification = "UNSTABLE"
        grade = "C"
        desc = "Frequent behavioral changes detected"
    elif trend > 0.3:
        classification = "EXPANDING"
        grade = "C"
        desc = "Scope usage expanding over time"
    elif trend < -0.3:
        classification = "NARROWING"
        grade = "B"
        desc = "Scope narrowing — possibly over-specializing"
    else:
        classification = "STABLE"
        grade = "A"
        desc = "Consistent behavior within authorized scope"

    return {
        "classification": classification,
        "grade": grade,
        "description": desc,
        "metrics": {
            "avg_scope_entropy": round(sum(scope_entropies)/len(scope_entropies), 4),
            "avg_action_entropy": round(sum(action_entropies)/len(action_entropies), 4),
            "avg_divergence": round(avg_divergence, 4),
            "max_divergence": round(max_divergence, 4),
            "entropy_trend": round(trend, 4),
            "cusum_alerts": len(action_alerts),
            "windows_analyzed": len(windows),
        },
        "cusum_alerts": action_alerts,
        "windows": windows,
    }


def demo():
    print("=== Scope Entropy Monitor ===\n")

    # Stable agent: consistent scope usage
    stable = [
        ScopeEvent(f"T{i}", "scope_search", "search_web")
        for i in range(8)
    ] + [
        ScopeEvent(f"T{8+i}", "scope_post", "post_content")
        for i in range(4)
    ]
    result = analyze_scope_drift(stable)
    _print_result("Stable agent (search + post)", result)

    # Drifting agent: starts narrow, goes wide
    drifting = [
        ScopeEvent("T0", "scope_read", "read_file"),
        ScopeEvent("T1", "scope_read", "read_file"),
        ScopeEvent("T2", "scope_read", "read_file"),
        ScopeEvent("T3", "scope_read", "read_config"),
        ScopeEvent("T4", "scope_read", "write_file"),     # drift starts
        ScopeEvent("T5", "scope_read", "modify_config"),
        ScopeEvent("T6", "scope_read", "execute_command"),
        ScopeEvent("T7", "scope_read", "install_package"),
        ScopeEvent("T8", "scope_read", "spawn_process"),
        ScopeEvent("T9", "scope_read", "access_network"),
    ]
    result = analyze_scope_drift(drifting)
    _print_result("Drifting agent (read scope, escalating actions)", result)

    # Byzantine: authorized scope changes but actions stay wrong
    byzantine = [
        ScopeEvent("T0", "scope_A", "action_X"),
        ScopeEvent("T1", "scope_B", "action_X"),
        ScopeEvent("T2", "scope_C", "action_X"),
        ScopeEvent("T3", "scope_D", "action_X"),
        ScopeEvent("T4", "scope_E", "action_X"),
        ScopeEvent("T5", "scope_F", "action_X"),
        ScopeEvent("T6", "scope_G", "action_X"),
        ScopeEvent("T7", "scope_H", "action_X"),
    ]
    result = analyze_scope_drift(byzantine)
    _print_result("Byzantine (changing scope, same action)", result)


def _print_result(name: str, result: dict):
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} — {result['classification']}")
    print(f"  {result['description']}")
    m = result['metrics']
    print(f"  Scope entropy: {m['avg_scope_entropy']:.3f}  Action entropy: {m['avg_action_entropy']:.3f}")
    print(f"  Divergence: avg={m['avg_divergence']:.3f} max={m['max_divergence']:.3f}")
    print(f"  Entropy trend: {m['entropy_trend']:+.3f}  CUSUM alerts: {m['cusum_alerts']}")
    print()


if __name__ == "__main__":
    demo()
