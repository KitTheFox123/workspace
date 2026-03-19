#!/usr/bin/env python3
"""trajectory-confidence.py — Confidence intervals for trust scores on short records.

Per santaclawd: "MIN_RECORD_LENGTH — trajectory score is undefined on short records.
Confidence intervals blow up. You are measuring noise, not trust."

Below minimum threshold: return interval, not point estimate.
"0.7 ± 0.4" is honest. "0.7" alone is a lie.
"""

import math
from dataclasses import dataclass


@dataclass 
class AgentRecord:
    name: str
    receipts: int
    days_active: int
    positive_outcomes: int  # successful completions
    refusals_with_rationale: int  # healthy refusals
    failures: int
    chain_grade_pct: float  # % of receipts that are chain-grade


MIN_RECEIPTS = 30
MIN_DAYS = 14


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — works well for small samples."""
    if total == 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0, center - spread), min(1, center + spread))


def score_trajectory(agent: AgentRecord) -> dict:
    """Score with confidence interval. Short records get wide intervals."""
    total = agent.receipts
    successes = agent.positive_outcomes + agent.refusals_with_rationale  # refusal IS success
    
    # Maturity gate
    mature = total >= MIN_RECEIPTS and agent.days_active >= MIN_DAYS
    
    # Wilson interval
    lower, upper = wilson_interval(successes, total)
    point = successes / total if total > 0 else 0
    interval_width = upper - lower
    
    # Chain-grade bonus (tighter interval when evidence is stronger)
    if agent.chain_grade_pct > 0.5:
        tightening = agent.chain_grade_pct * 0.15
        lower = min(point, lower + tightening)
        upper = max(point, upper - tightening)
        interval_width = upper - lower
    
    # Confidence classification
    if not mature:
        confidence = "INSUFFICIENT"
        note = f"need {max(0, MIN_RECEIPTS - total)} more receipts or {max(0, MIN_DAYS - agent.days_active)} more days"
    elif interval_width < 0.15:
        confidence = "HIGH"
        note = "tight interval, score is meaningful"
    elif interval_width < 0.30:
        confidence = "MEDIUM"  
        note = "moderate uncertainty, use with caution"
    else:
        confidence = "LOW"
        note = "wide interval, score is noise"
    
    return {
        "agent": agent.name,
        "point_estimate": round(point, 3),
        "interval": f"[{lower:.3f}, {upper:.3f}]",
        "width": round(interval_width, 3),
        "confidence": confidence,
        "mature": mature,
        "receipts": total,
        "days": agent.days_active,
        "note": note,
    }


# Test agents
agents = [
    AgentRecord("new_agent", 5, 3, 4, 1, 0, 0.0),
    AgentRecord("week_old", 20, 10, 15, 3, 2, 0.2),
    AgentRecord("barely_mature", 31, 15, 25, 3, 3, 0.4),
    AgentRecord("established", 200, 60, 170, 15, 15, 0.6),
    AgentRecord("veteran_chain", 500, 180, 420, 40, 40, 0.85),
    AgentRecord("perfect_score", 10, 5, 10, 0, 0, 0.0),  # suspicious
    AgentRecord("healthy_refuser", 100, 45, 70, 20, 10, 0.5),  # 20% refusal = good
]

print("=" * 70)
print("Trajectory Confidence Scorer")
print(f"MIN_RECORD: {MIN_RECEIPTS} receipts AND {MIN_DAYS} days")
print("Per santaclawd: confidence intervals, not point estimates")
print("=" * 70)

for a in agents:
    r = score_trajectory(a)
    icon = {"INSUFFICIENT": "⏳", "HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}[r["confidence"]]
    print(f"\n{icon} {r['agent']}: {r['point_estimate']} {r['interval']} (±{r['width']:.3f})")
    print(f"   {r['confidence']} | {r['receipts']} receipts / {r['days']}d | {r['note']}")

print(f"\n{'=' * 70}")
print("KEY: Refusals with rationale count as SUCCESS.")
print("     Short records → wide intervals → honest uncertainty.")
print("     Chain-grade evidence tightens intervals.")
print(f"{'=' * 70}")
