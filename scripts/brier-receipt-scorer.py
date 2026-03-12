#!/usr/bin/env python3
"""
Brier Receipt Scorer — Score agent deliveries like prediction market bets.

Moltygamer's insight: prediction markets are pure receipt economies.
PnL = resume. Brier score = credential. No inflation possible when
the scoreboard is append-only.

Brier score (1950): mean squared error of probabilistic predictions.
  BS = (1/N) Σ (forecast_i - outcome_i)²
  0 = perfect, 1 = worst possible

Agent mapping:
  forecast = committed scope (what agent said it would do)
  outcome = actual delivery (what receipt chain shows)
  Each delivery is a resolved bet.

Usage:
    python3 brier-receipt-scorer.py              # Demo
    echo '{"deliveries": [...]}' | python3 brier-receipt-scorer.py --stdin
"""

import json, sys, math

def brier_score(deliveries: list[dict]) -> dict:
    """Score an agent's delivery track record like a prediction market."""
    if not deliveries:
        return {"brier_score": 1.0, "grade": "F", "reason": "No deliveries = no track record"}
    
    n = len(deliveries)
    squared_errors = []
    on_time = 0
    in_scope = 0
    quality_met = 0
    
    for d in deliveries:
        # Each delivery has committed vs actual dimensions
        time_hit = 1.0 if d.get("on_time", False) else 0.0
        scope_hit = 1.0 if d.get("in_scope", False) else 0.0
        quality_hit = d.get("quality_score", 0.5)  # 0-1
        
        # Forecast was implicitly 1.0 (committed to deliver on time, in scope, quality)
        time_err = (1.0 - time_hit) ** 2
        scope_err = (1.0 - scope_hit) ** 2
        quality_err = (1.0 - quality_hit) ** 2
        
        composite_err = (time_err + scope_err + quality_err) / 3
        squared_errors.append(composite_err)
        
        if d.get("on_time"): on_time += 1
        if d.get("in_scope"): in_scope += 1
        if quality_hit >= 0.7: quality_met += 1
    
    bs = sum(squared_errors) / n
    
    # Calibration: how well does the agent know its own limits?
    # Low Brier = good calibration (only commits to what it can deliver)
    calibration = 1.0 - bs
    
    # Streak analysis
    current_streak = 0
    max_streak = 0
    for d in deliveries:
        if d.get("on_time") and d.get("in_scope") and d.get("quality_score", 0) >= 0.7:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    
    if bs <= 0.1: grade = "A"
    elif bs <= 0.25: grade = "B"
    elif bs <= 0.4: grade = "C"
    elif bs <= 0.6: grade = "D"
    else: grade = "F"
    
    return {
        "brier_score": round(bs, 4),
        "calibration": round(calibration, 4),
        "grade": grade,
        "total_deliveries": n,
        "on_time_pct": round(on_time / n, 3),
        "in_scope_pct": round(in_scope / n, 3),
        "quality_met_pct": round(quality_met / n, 3),
        "max_perfect_streak": max_streak,
        "polymarket_analog": f"This agent's Brier score ({bs:.3f}) = top {_percentile(bs)}% of forecasters" if bs < 0.3 else f"Brier {bs:.3f} — needs calibration",
    }


def _percentile(bs):
    """Rough percentile mapping based on typical prediction market performance."""
    if bs <= 0.05: return 1
    elif bs <= 0.1: return 5
    elif bs <= 0.15: return 10
    elif bs <= 0.2: return 20
    elif bs <= 0.25: return 30
    else: return 50


def demo():
    print("=== Brier Receipt Scorer ===")
    print("PnL = resume. Brier score = credential.\n")
    
    # Kit's TC3 + typical deliveries
    kit = [
        {"on_time": True, "in_scope": True, "quality_score": 0.92, "desc": "TC3 report"},
        {"on_time": True, "in_scope": True, "quality_score": 0.85, "desc": "isnad RFC"},
        {"on_time": True, "in_scope": True, "quality_score": 0.90, "desc": "dispute-oracle-sim"},
        {"on_time": False, "in_scope": True, "quality_score": 0.80, "desc": "attestation-signer (late)"},
        {"on_time": True, "in_scope": True, "quality_score": 0.88, "desc": "fork-fingerprint"},
        {"on_time": True, "in_scope": True, "quality_score": 0.95, "desc": "GDPR receipt checker"},
    ]
    
    print("Kit (TC3 + tools):")
    r = brier_score(kit)
    print(f"  Brier: {r['brier_score']} ({r['grade']})")
    print(f"  On-time: {r['on_time_pct']*100:.0f}%, In-scope: {r['in_scope_pct']*100:.0f}%")
    print(f"  Max streak: {r['max_perfect_streak']}")
    print(f"  {r['polymarket_analog']}")
    
    # Unreliable agent
    unreliable = [
        {"on_time": False, "in_scope": False, "quality_score": 0.3},
        {"on_time": True, "in_scope": False, "quality_score": 0.5},
        {"on_time": False, "in_scope": True, "quality_score": 0.4},
        {"on_time": False, "in_scope": False, "quality_score": 0.2},
    ]
    
    print("\nUnreliable agent:")
    r = brier_score(unreliable)
    print(f"  Brier: {r['brier_score']} ({r['grade']})")
    print(f"  On-time: {r['on_time_pct']*100:.0f}%, In-scope: {r['in_scope_pct']*100:.0f}%")
    print(f"  {r['polymarket_analog']}")
    
    # New agent (1 delivery)
    new = [{"on_time": True, "in_scope": True, "quality_score": 0.75}]
    
    print("\nNew agent (1 delivery):")
    r = brier_score(new)
    print(f"  Brier: {r['brier_score']} ({r['grade']})")
    print(f"  Cold start: {r['total_deliveries']} delivery. Insufficient for reliable scoring.")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = brier_score(data.get("deliveries", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
