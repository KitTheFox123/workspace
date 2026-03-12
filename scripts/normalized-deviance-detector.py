#!/usr/bin/env python3
"""Normalized Deviance Detector — Vaughan (1996, 2025) for agent drift.

"Mistakes are socially organized and systematically produced."
— Diane Vaughan, Columbia Magazine Winter 2025-26

The normalization of deviance: small exceptions become the new baseline.
Each accepted anomaly makes the next one easier to accept.

For agents: each skipped check, each scope exception, each unlogged action
compounds. The fix is architecture (make default safe) not vigilance.

Detects:
1. Baseline drift: are thresholds creeping?
2. Exception accumulation: are "one-time" exceptions becoming permanent?
3. Fix-and-fly: are patches masking root causes? (O-ring pattern)
4. Production pressure: are quality checks being skipped under load?

Kit 🦊 — 2026-02-28
"""

import json
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionRecord:
    session_id: int
    checks_required: int
    checks_completed: int
    exceptions_granted: int      # scope exceptions allowed
    exceptions_permanent: int    # exceptions that became default
    patches_applied: int         # fixes without root cause analysis
    scope_drift: float           # 0 = no drift, 1 = complete drift
    production_pressure: float   # 0 = relaxed, 1 = max pressure


def detect_deviance(records: list[SessionRecord]) -> dict:
    """Analyze session records for normalized deviance patterns."""
    if len(records) < 3:
        return {"error": "need 3+ sessions for trend detection"}

    n = len(records)

    # 1. Check completion ratio over time
    completion_ratios = [r.checks_completed / max(r.checks_required, 1) for r in records]
    early = statistics.mean(completion_ratios[:n//3])
    late = statistics.mean(completion_ratios[-n//3:])
    completion_drift = early - late  # positive = degrading

    # 2. Exception accumulation (Vaughan's core finding)
    exception_ratios = [r.exceptions_permanent / max(r.exceptions_granted, 1) for r in records]
    exception_trend = exception_ratios[-1] - exception_ratios[0] if len(exception_ratios) > 1 else 0

    # 3. Fix-and-fly pattern (O-ring: patch it, keep flying)
    patch_without_root = sum(r.patches_applied for r in records)
    total_issues = sum(r.checks_required - r.checks_completed + r.exceptions_granted for r in records)
    fix_fly_ratio = patch_without_root / max(total_issues, 1)

    # 4. Production pressure correlation
    # Does high pressure correlate with skipped checks?
    pressures = [r.production_pressure for r in records]
    skip_ratios = [1 - cr for cr in completion_ratios]
    if len(pressures) > 2:
        # Simple correlation proxy
        p_mean = statistics.mean(pressures)
        s_mean = statistics.mean(skip_ratios)
        cov = sum((p - p_mean) * (s - s_mean) for p, s in zip(pressures, skip_ratios)) / n
        p_std = statistics.stdev(pressures) if statistics.stdev(pressures) > 0 else 1
        s_std = statistics.stdev(skip_ratios) if statistics.stdev(skip_ratios) > 0 else 1
        pressure_skip_corr = cov / (p_std * s_std)
    else:
        pressure_skip_corr = 0

    # 5. Scope drift trajectory
    drifts = [r.scope_drift for r in records]
    drift_velocity = (drifts[-1] - drifts[0]) / max(n - 1, 1)

    # Composite deviance score (0 = healthy, 1 = Challenger-level)
    deviance = min(1.0, (
        max(completion_drift, 0) * 0.25 +
        max(exception_trend, 0) * 0.25 +
        fix_fly_ratio * 0.20 +
        max(pressure_skip_corr, 0) * 0.15 +
        max(drift_velocity, 0) * 0.15
    ) * 2)  # scale up since individual components are usually < 0.5

    # Classification
    if deviance < 0.15:
        grade, classification = "A", "HEALTHY"
        desc = "No deviance detected. Baselines holding."
    elif deviance < 0.30:
        grade, classification = "B", "EARLY_DRIFT"
        desc = "Minor drift. Monitor exception accumulation."
    elif deviance < 0.50:
        grade, classification = "C", "NORMALIZING"
        desc = "Deviance normalizing. Exceptions becoming permanent."
    elif deviance < 0.75:
        grade, classification = "D", "VAUGHAN_WARNING"
        desc = "Significant normalized deviance. O-ring pattern active."
    else:
        grade, classification = "F", "PRE_CHALLENGER"
        desc = "Critical. Patches masking root causes. Production pressure overriding safety."

    return {
        "deviance_score": round(deviance, 3),
        "grade": grade,
        "classification": classification,
        "description": desc,
        "metrics": {
            "completion_drift": round(completion_drift, 3),
            "exception_permanence_trend": round(exception_trend, 3),
            "fix_and_fly_ratio": round(fix_fly_ratio, 3),
            "pressure_skip_correlation": round(pressure_skip_corr, 3),
            "scope_drift_velocity": round(drift_velocity, 4),
        },
        "vaughan_quote": "Mistakes are socially organized and systematically produced.",
        "sessions_analyzed": n,
    }


def demo():
    print("=== Normalized Deviance Detector ===")
    print("Vaughan 1996 / Columbia Magazine 2025-26\n")

    # Healthy agent: consistent checks
    healthy = [
        SessionRecord(i, 10, 10 - (i % 2), 1, 0, 0, 0.0, 0.2 + i * 0.01)
        for i in range(12)
    ]
    result = detect_deviance(healthy)
    _print("Healthy agent", result)

    # Drifting agent: exceptions accumulate, checks degrade
    drifting = [
        SessionRecord(i, 10, max(10 - i // 2, 5), 2 + i // 3, i // 4, i // 3,
                       i * 0.05, 0.3 + i * 0.05)
        for i in range(12)
    ]
    result = detect_deviance(drifting)
    _print("Drifting agent (Vaughan pattern)", result)

    # Pre-Challenger: heavy pressure, patches everywhere, exceptions permanent
    challenger = [
        SessionRecord(i, 10, max(10 - i, 3), 3 + i, min(i, 3 + i),
                       2 + i, i * 0.08, 0.5 + i * 0.04)
        for i in range(12)
    ]
    result = detect_deviance(challenger)
    _print("Pre-Challenger pattern", result)


def _print(name: str, result: dict):
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} ({result['deviance_score']}) — {result['classification']}")
    print(f"  {result['description']}")
    m = result['metrics']
    print(f"  Completion drift: {m['completion_drift']:.3f}")
    print(f"  Exception permanence: {m['exception_permanence_trend']:.3f}")
    print(f"  Fix-and-fly: {m['fix_and_fly_ratio']:.3f}")
    print(f"  Pressure→skip corr: {m['pressure_skip_correlation']:.3f}")
    print(f"  Scope drift velocity: {m['scope_drift_velocity']:.4f}")
    print(f"  \"{result['vaughan_quote']}\"")
    print()


if __name__ == "__main__":
    demo()
