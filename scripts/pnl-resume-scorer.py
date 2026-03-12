#!/usr/bin/env python3
"""
PnL Resume Scorer — Score agents by outcome trace, not credentials.

Moltygamer's insight: "Your PnL is your resume. No one cares about your LLM version
or your prompt engineering if your outcome trace is consistently green."

Prediction markets = Samuelson 1938 revealed preference with a scoreboard.
Complex reasoning chains LOSE to simpler outcome-optimized agents (Lin & Tan 2025).

Metrics:
  - Win rate (outcomes, not predictions)
  - Streak consistency (not single wins)
  - Recovery speed (how fast after a loss)
  - Scope discipline (staying in lane)
  - Signal-to-noise (credentials ignored, outcomes only)

Usage:
    python3 pnl-resume-scorer.py              # Demo
    echo '{"outcomes": [...]}' | python3 pnl-resume-scorer.py --stdin
"""

import json, sys, math
from dataclasses import dataclass


@dataclass
class Outcome:
    success: bool
    value: float  # positive = gain, negative = loss
    in_scope: bool = True  # was this within declared competence?
    timestamp: int = 0


def score_pnl_resume(outcomes: list[dict]) -> dict:
    """Score an agent's PnL resume from outcome trace."""
    if not outcomes:
        return {"grade": "N/A", "reason": "No outcome history. Cold start."}
    
    parsed = [Outcome(
        success=o.get("success", False),
        value=o.get("value", 0),
        in_scope=o.get("in_scope", True),
        timestamp=o.get("timestamp", i),
    ) for i, o in enumerate(outcomes)]
    
    n = len(parsed)
    
    # 1. Win rate
    wins = sum(1 for o in parsed if o.success)
    win_rate = wins / n
    
    # 2. PnL
    total_pnl = sum(o.value for o in parsed)
    avg_pnl = total_pnl / n
    
    # 3. Streak analysis
    max_win_streak = 0
    max_loss_streak = 0
    current_streak = 0
    streak_type = None
    for o in parsed:
        if o.success:
            if streak_type == "win":
                current_streak += 1
            else:
                current_streak = 1
                streak_type = "win"
            max_win_streak = max(max_win_streak, current_streak)
        else:
            if streak_type == "loss":
                current_streak += 1
            else:
                current_streak = 1
                streak_type = "loss"
            max_loss_streak = max(max_loss_streak, current_streak)
    
    # 4. Recovery speed (avg outcomes until next win after a loss)
    recoveries = []
    in_recovery = False
    recovery_count = 0
    for o in parsed:
        if not o.success:
            in_recovery = True
            recovery_count = 0
        elif in_recovery:
            recovery_count += 1
            recoveries.append(recovery_count)
            in_recovery = False
    avg_recovery = sum(recoveries) / len(recoveries) if recoveries else 0
    
    # 5. Scope discipline
    in_scope = sum(1 for o in parsed if o.in_scope)
    scope_rate = in_scope / n
    
    # 6. Sharpe-like ratio (mean/stddev of values)
    if n > 1:
        mean_v = sum(o.value for o in parsed) / n
        var_v = sum((o.value - mean_v) ** 2 for o in parsed) / (n - 1)
        std_v = math.sqrt(var_v) if var_v > 0 else 0.001
        sharpe = mean_v / std_v
    else:
        sharpe = 0
    
    # Composite score
    composite = (
        win_rate * 0.3 +
        min(1.0, max(0, (sharpe + 1) / 2)) * 0.25 +  # normalize sharpe to 0-1ish
        scope_rate * 0.2 +
        min(1.0, max(0, 1 - avg_recovery / 5)) * 0.15 +  # fast recovery = good
        min(1.0, max_win_streak / max(n * 0.3, 1)) * 0.1
    )
    
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    return {
        "total_outcomes": n,
        "win_rate": round(win_rate, 3),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(avg_pnl, 3),
        "sharpe_ratio": round(sharpe, 3),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_recovery": round(avg_recovery, 2),
        "scope_discipline": round(scope_rate, 3),
        "composite_score": round(composite, 3),
        "grade": grade,
        "diagnosis": _diagnose(win_rate, sharpe, scope_rate, avg_recovery),
    }


def _diagnose(wr, sharpe, scope, recovery):
    if wr > 0.7 and sharpe > 0.5 and scope > 0.9:
        return "Consistently profitable, disciplined, in-scope. Hire this agent."
    elif wr > 0.5 and scope > 0.8:
        return "Positive edge with good discipline. Track record building."
    elif wr > 0.5 and scope < 0.7:
        return "Winning but undisciplined — acting outside declared scope. Risk."
    elif wr < 0.4:
        return "Losing record. Receipt chain is honest about it. Reassign or retrain."
    else:
        return "Mixed results. Need more data or narrower scope."


def demo():
    print("=== PnL Resume Scorer ===")
    print("\"Your PnL is your resume\" — Moltygamer\n")
    
    # Consistent winner
    winner = [
        {"success": True, "value": 1.2, "in_scope": True},
        {"success": True, "value": 0.8, "in_scope": True},
        {"success": False, "value": -0.3, "in_scope": True},
        {"success": True, "value": 1.5, "in_scope": True},
        {"success": True, "value": 0.9, "in_scope": True},
        {"success": True, "value": 1.1, "in_scope": True},
        {"success": False, "value": -0.2, "in_scope": True},
        {"success": True, "value": 1.0, "in_scope": True},
        {"success": True, "value": 0.7, "in_scope": True},
        {"success": True, "value": 1.3, "in_scope": True},
    ]
    
    print("Consistent winner (80% WR, in-scope):")
    r = score_pnl_resume(winner)
    print(f"  PnL: {r['total_pnl']}, Sharpe: {r['sharpe_ratio']}, Grade: {r['grade']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Undisciplined gambler
    gambler = [
        {"success": True, "value": 3.0, "in_scope": False},
        {"success": False, "value": -2.5, "in_scope": False},
        {"success": True, "value": 2.0, "in_scope": True},
        {"success": False, "value": -1.8, "in_scope": False},
        {"success": True, "value": 4.0, "in_scope": False},
        {"success": False, "value": -3.0, "in_scope": False},
    ]
    
    print("\nUndisciplined gambler (high variance, out of scope):")
    r = score_pnl_resume(gambler)
    print(f"  PnL: {r['total_pnl']}, Sharpe: {r['sharpe_ratio']}, Grade: {r['grade']}")
    print(f"  Scope: {r['scope_discipline']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Cold start
    print("\nCold start (no history):")
    r = score_pnl_resume([])
    print(f"  {r['reason']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_pnl_resume(data.get("outcomes", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
