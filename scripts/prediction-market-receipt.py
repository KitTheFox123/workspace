#!/usr/bin/env python3
"""
Prediction Market Receipt Scorer — PnL as resume.

Moltygamer's insight: "prediction markets are a pure receipt economy. 
Your PnL is your resume. No one cares about your LLM version."

Maps prediction market mechanics to agent receipt chains:
  Bet = action with scope (market + position + stake)
  Resolution = attested outcome (oracle)
  PnL = revealed competence (unfakeable)
  Calibration = quality metric (Brier score)

Usage:
    python3 prediction-market-receipt.py
"""

import json, math

def brier_score(predictions: list[dict]) -> float:
    """Brier score: lower = better calibrated. 0 = perfect, 1 = worst."""
    if not predictions:
        return 1.0
    total = sum((p["confidence"] - p["outcome"]) ** 2 for p in predictions)
    return total / len(predictions)


def pnl_resume(trades: list[dict]) -> dict:
    """Build a receipt-chain resume from prediction market trades."""
    total_pnl = 0
    wins = 0
    losses = 0
    total_stake = 0
    predictions = []
    
    for t in trades:
        pnl = t.get("pnl", 0)
        total_pnl += pnl
        total_stake += abs(t.get("stake", 0))
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        predictions.append({
            "confidence": t.get("confidence", 0.5),
            "outcome": 1.0 if pnl > 0 else 0.0,
        })
    
    win_rate = wins / max(wins + losses, 1)
    roi = total_pnl / max(total_stake, 0.01)
    brier = brier_score(predictions)
    
    # Receipt chain fields
    receipt = {
        "agent_id": trades[0].get("agent_id", "unknown") if trades else "unknown",
        "total_trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 3),
        "total_pnl": round(total_pnl, 2),
        "roi": round(roi, 3),
        "brier_score": round(brier, 3),
        "calibration_grade": _grade_calibration(brier),
        "resume_strength": _resume_strength(len(trades), win_rate, roi, brier),
    }
    
    return receipt


def _grade_calibration(brier):
    if brier < 0.1: return "A+ (superforecaster)"
    if brier < 0.2: return "A (well calibrated)"
    if brier < 0.3: return "B (decent)"
    if brier < 0.4: return "C (average)"
    return "F (worse than coin flip)"


def _resume_strength(n_trades, win_rate, roi, brier):
    """Composite resume strength from receipts."""
    volume = min(1.0, math.log1p(n_trades) / math.log1p(100))
    performance = max(0, min(1, (roi + 0.5)))  # -50% to +50% → 0 to 1
    calibration = max(0, 1 - brier)
    
    composite = volume * 0.3 + performance * 0.3 + calibration * 0.4
    
    if composite >= 0.8: return f"STRONG ({composite:.2f}) — hire on receipts alone"
    if composite >= 0.6: return f"GOOD ({composite:.2f}) — credible track record"
    if composite >= 0.4: return f"DEVELOPING ({composite:.2f}) — needs more trades"
    return f"WEAK ({composite:.2f}) — insufficient evidence"


def demo():
    print("=== Prediction Market Receipt Scorer ===")
    print("\"Your PnL is your resume\" — Moltygamer\n")
    
    # Superforecaster agent
    super_trades = [
        {"agent_id": "agent:oracle", "stake": 100, "pnl": 45, "confidence": 0.8},
        {"agent_id": "agent:oracle", "stake": 50, "pnl": 20, "confidence": 0.7},
        {"agent_id": "agent:oracle", "stake": 75, "pnl": -15, "confidence": 0.55},
        {"agent_id": "agent:oracle", "stake": 200, "pnl": 90, "confidence": 0.85},
        {"agent_id": "agent:oracle", "stake": 100, "pnl": 30, "confidence": 0.75},
        {"agent_id": "agent:oracle", "stake": 80, "pnl": -10, "confidence": 0.6},
        {"agent_id": "agent:oracle", "stake": 150, "pnl": 60, "confidence": 0.8},
    ]
    
    print("Superforecaster agent:")
    r = pnl_resume(super_trades)
    print(f"  PnL: ${r['total_pnl']} | Win rate: {r['win_rate']} | ROI: {r['roi']}")
    print(f"  Brier: {r['brier_score']} ({r['calibration_grade']})")
    print(f"  Resume: {r['resume_strength']}")
    
    # Coin flip agent
    coin_trades = [
        {"agent_id": "agent:random", "stake": 100, "pnl": 50, "confidence": 0.5},
        {"agent_id": "agent:random", "stake": 100, "pnl": -50, "confidence": 0.5},
        {"agent_id": "agent:random", "stake": 100, "pnl": 50, "confidence": 0.5},
        {"agent_id": "agent:random", "stake": 100, "pnl": -50, "confidence": 0.5},
    ]
    
    print("\nCoin flip agent:")
    r = pnl_resume(coin_trades)
    print(f"  PnL: ${r['total_pnl']} | Win rate: {r['win_rate']} | ROI: {r['roi']}")
    print(f"  Brier: {r['brier_score']} ({r['calibration_grade']})")
    print(f"  Resume: {r['resume_strength']}")
    
    # Overconfident agent (high confidence, low win rate)
    overconf = [
        {"agent_id": "agent:dunning", "stake": 200, "pnl": -100, "confidence": 0.95},
        {"agent_id": "agent:dunning", "stake": 150, "pnl": -80, "confidence": 0.9},
        {"agent_id": "agent:dunning", "stake": 100, "pnl": 20, "confidence": 0.85},
        {"agent_id": "agent:dunning", "stake": 180, "pnl": -90, "confidence": 0.92},
    ]
    
    print("\nOverconfident agent (Dunning-Kruger):")
    r = pnl_resume(overconf)
    print(f"  PnL: ${r['total_pnl']} | Win rate: {r['win_rate']} | ROI: {r['roi']}")
    print(f"  Brier: {r['brier_score']} ({r['calibration_grade']})")
    print(f"  Resume: {r['resume_strength']}")


if __name__ == "__main__":
    demo()
