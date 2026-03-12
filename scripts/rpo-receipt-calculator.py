#!/usr/bin/env python3
"""
RPO Receipt Calculator — Compare Recovery Point Objectives: periodic vs continuous.

RisqOne's insight: "Your backup strategy assumes the disaster will be polite."
Periodic backups have RPO = backup_interval. Disaster at 1:58 AM with 2 AM backup = 24hr loss.
Receipt chains have RPO ≈ 0: every action is immediately hashed and chained.

For agent accountability:
  Periodic audit = compliance check every N hours → blind spot = N hours
  Receipt chain = every action attested → blind spot = 0
  The disaster window IS the audit interval.

Usage:
    python3 rpo-receipt-calculator.py              # Demo
    echo '{"strategy": {...}}' | python3 rpo-receipt-calculator.py --stdin
"""

import json, sys, math, random

def calculate_rpo(strategy: dict) -> dict:
    """Calculate RPO and expected data loss for a backup/audit strategy."""
    name = strategy.get("name", "unnamed")
    interval_hours = strategy.get("interval_hours", 24)
    is_continuous = strategy.get("continuous", False)
    actions_per_hour = strategy.get("actions_per_hour", 10)
    
    if is_continuous:
        rpo_hours = 0
        max_loss_actions = 0
        avg_loss_actions = 0
        blind_spot_pct = 0
    else:
        rpo_hours = interval_hours
        # Disaster is uniformly distributed — average loss = interval/2
        avg_loss_actions = actions_per_hour * interval_hours / 2
        max_loss_actions = actions_per_hour * interval_hours
        blind_spot_pct = 100.0  # Between backups, you're always blind
    
    # Annual expected loss (assuming 1 disaster/year)
    annual_loss = avg_loss_actions
    
    # Compliance score
    if is_continuous:
        compliance = 1.0
    else:
        # More frequent = better, but never 1.0
        compliance = max(0, 1.0 - (interval_hours / 168))  # 168 = 1 week
    
    return {
        "name": name,
        "rpo_hours": rpo_hours,
        "max_loss_actions": max_loss_actions,
        "avg_loss_actions": round(avg_loss_actions, 1),
        "blind_spot_pct": round(blind_spot_pct, 1),
        "compliance_score": round(compliance, 3),
        "verdict": _verdict(is_continuous, interval_hours),
    }


def simulate_disaster(strategies: list[dict], n_disasters: int = 1000) -> dict:
    """Monte Carlo: random disaster timing vs each strategy."""
    results = {}
    for strat in strategies:
        name = strat.get("name", "unnamed")
        interval = strat.get("interval_hours", 24)
        continuous = strat.get("continuous", False)
        aph = strat.get("actions_per_hour", 10)
        
        losses = []
        for _ in range(n_disasters):
            if continuous:
                losses.append(0)
            else:
                # Disaster at random point in interval
                time_since_backup = random.uniform(0, interval)
                losses.append(time_since_backup * aph)
        
        results[name] = {
            "mean_loss": round(sum(losses) / len(losses), 1),
            "max_loss": round(max(losses), 1),
            "zero_loss_pct": round(sum(1 for l in losses if l == 0) / len(losses) * 100, 1),
            "p95_loss": round(sorted(losses)[int(0.95 * len(losses))], 1),
        }
    
    return results


def _verdict(continuous, interval):
    if continuous:
        return "Zero RPO. The chain IS the state. No disaster window."
    elif interval <= 1:
        return f"Hourly backup. 1hr blind spot. Better than most, worse than continuous."
    elif interval <= 24:
        return f"{interval}hr backup. Disaster window = {interval} hours of unrecoverable actions."
    else:
        return f"{interval}hr backup. Unacceptable blind spot for accountability."


def demo():
    print("=== RPO Receipt Calculator ===")
    print("\"Your backup assumes the disaster will be polite.\" — RisqOne\n")
    
    strategies = [
        {"name": "Nightly backup", "interval_hours": 24, "actions_per_hour": 10},
        {"name": "Hourly backup", "interval_hours": 1, "actions_per_hour": 10},
        {"name": "Receipt chain", "continuous": True, "actions_per_hour": 10},
        {"name": "Weekly audit", "interval_hours": 168, "actions_per_hour": 10},
    ]
    
    print("Strategy comparison (10 actions/hour):")
    print(f"{'Strategy':<20} {'RPO':>6} {'Avg Loss':>10} {'Max Loss':>10} {'Compliance':>12}")
    print("-" * 62)
    for strat in strategies:
        r = calculate_rpo(strat)
        print(f"{r['name']:<20} {r['rpo_hours']:>5}h {r['avg_loss_actions']:>9} {r['max_loss_actions']:>9} {r['compliance_score']:>11}")
    
    print("\nMonte Carlo simulation (1000 random disasters):")
    sim = simulate_disaster(strategies)
    print(f"{'Strategy':<20} {'Mean Loss':>10} {'P95 Loss':>10} {'Max Loss':>10} {'Zero%':>8}")
    print("-" * 62)
    for name, stats in sim.items():
        print(f"{name:<20} {stats['mean_loss']:>9} {stats['p95_loss']:>9} {stats['max_loss']:>9} {stats['zero_loss_pct']:>7}%")
    
    print(f"\nReceipt chain: {sim['Receipt chain']['zero_loss_pct']}% zero-loss disasters.")
    print(f"Nightly backup: average {sim['Nightly backup']['mean_loss']} actions lost per disaster.")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        if "strategies" in data:
            results = {s["name"]: calculate_rpo(s) for s in data["strategies"]}
            print(json.dumps(results, indent=2))
        else:
            print(json.dumps(calculate_rpo(data), indent=2))
    else:
        demo()
