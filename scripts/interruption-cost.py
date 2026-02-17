#!/usr/bin/env python3
"""Interruption cost calculator based on Yacoub et al. 2024 and Monk et al. 2008.

Models the cognitive cost of synchronous vs asynchronous interruptions,
including task resumption lag (Monk 2008: longer interruptions = longer resume).

Usage:
    python3 interruption-cost.py [--hourly-rate RATE] [--hours HOURS]
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict

@dataclass
class InterruptionProfile:
    """Interruption characteristics from literature."""
    name: str
    avg_duration_sec: float    # Yacoub 2024
    during_task_pct: float     # % occurring during active work
    per_hour: float            # frequency
    resumption_lag_sec: float  # Monk 2008: time to resume after interruption

# From Yacoub et al. 2024, J Digit Imaging Inform Med 37:2038-2046
PROFILES = {
    "phone": InterruptionProfile(
        name="Phone (synchronous)",
        avg_duration_sec=168,   # 2m48s
        during_task_pct=0.979,
        per_hour=1.1,           # ~47/43hrs observed
        resumption_lag_sec=25   # Monk 2008 estimates
    ),
    "in_person": InterruptionProfile(
        name="In-person (synchronous)",
        avg_duration_sec=132,   # 2m12s
        during_task_pct=0.82,
        per_hour=2.1,           # 89/43hrs
        resumption_lag_sec=20
    ),
    "async": InterruptionProfile(
        name="Teams/async",
        avg_duration_sec=72,    # 1m12s
        during_task_pct=0.605,
        per_hour=1.0,           # 43/43hrs
        resumption_lag_sec=8    # task-boundary = minimal resume cost
    ),
}

def calculate_cost(profile: InterruptionProfile, hours: float, hourly_rate: float) -> dict:
    """Calculate total cognitive and time cost of interruptions."""
    total_interruptions = profile.per_hour * hours
    during_task = total_interruptions * profile.during_task_pct
    between_task = total_interruptions * (1 - profile.during_task_pct)
    
    # Time lost = interruption duration + resumption lag (only for during-task)
    time_lost_sec = (
        total_interruptions * profile.avg_duration_sec +  # all interruptions take time
        during_task * profile.resumption_lag_sec           # only during-task has resume cost
    )
    time_lost_hours = time_lost_sec / 3600
    cost = time_lost_hours * hourly_rate
    
    # Effective work ratio
    effective_ratio = max(0, (hours - time_lost_hours) / hours)
    
    return {
        "profile": profile.name,
        "total_interruptions": round(total_interruptions, 1),
        "during_task": round(during_task, 1),
        "time_lost_minutes": round(time_lost_sec / 60, 1),
        "time_lost_pct": round((1 - effective_ratio) * 100, 1),
        "effective_work_pct": round(effective_ratio * 100, 1),
        "cost_usd": round(cost, 2),
    }

def compare_protocols(hours: float = 8, hourly_rate: float = 75) -> dict:
    """Compare all interruption protocols."""
    results = {}
    for key, profile in PROFILES.items():
        results[key] = calculate_cost(profile, hours, hourly_rate)
    
    # Calculate savings from switching sync → async
    phone_cost = results["phone"]["cost_usd"]
    async_cost = results["async"]["cost_usd"]
    savings = phone_cost - async_cost
    
    results["_summary"] = {
        "hours_modeled": hours,
        "hourly_rate": hourly_rate,
        "async_savings_per_day": round(savings, 2),
        "async_savings_per_year": round(savings * 250, 2),  # ~250 work days
        "source": "Yacoub et al. 2024, doi:10.1007/s10278-024-01073-2",
    }
    return results

def main():
    parser = argparse.ArgumentParser(description="Interruption cost calculator")
    parser.add_argument("--hourly-rate", type=float, default=75, help="Hourly rate in USD")
    parser.add_argument("--hours", type=float, default=8, help="Work hours per day")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    results = compare_protocols(args.hours, args.hourly_rate)
    
    if args.json:
        print(json.dumps(results, indent=2))
        return
    
    print("=" * 60)
    print("INTERRUPTION COST ANALYSIS")
    print(f"Based on {args.hours}h workday @ ${args.hourly_rate}/hr")
    print("=" * 60)
    
    for key in ["phone", "in_person", "async"]:
        r = results[key]
        print(f"\n📞 {r['profile']}")
        print(f"   Interruptions: {r['total_interruptions']}/day ({r['during_task']} during tasks)")
        print(f"   Time lost: {r['time_lost_minutes']} min ({r['time_lost_pct']}%)")
        print(f"   Effective work: {r['effective_work_pct']}%")
        print(f"   Cost: ${r['cost_usd']}/day")
    
    s = results["_summary"]
    print(f"\n{'=' * 60}")
    print(f"💰 Switching phone → async saves ${s['async_savings_per_day']}/day")
    print(f"   = ${s['async_savings_per_year']}/year")
    print(f"\n📄 Source: {s['source']}")

if __name__ == "__main__":
    main()
