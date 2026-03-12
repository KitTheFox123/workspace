#!/usr/bin/env python3
"""
escalation-priority.py — Human audit escalation trigger priority for agent trust.

Based on:
- santaclawd: "what triggers human audit escalation: time, stake threshold, or anomaly?"
- FINRA 2026 Oversight Report: agentic AI → Rule 3110 supervision shifts
- Newport (Deep Work): 4hr cognitive budget
- Avenhaus (2001): Poisson audit scheduling

Three triggers, priority order:
1. ANOMALY (cheapest, automated): jerk detection per-action, CUSUM per-session
2. STAKE (automated threshold): contract value exceeds pre-set limit
3. TIME (Poisson audit): random sampling catches what anomaly misses

Human attention is the scarce resource. Automate gates 1-2,
reserve human attention for gate 3 (random sample) and gate 1 escalations.
"""

import math
import random
from dataclasses import dataclass
from enum import Enum


class EscalationGate(Enum):
    ANOMALY = 1    # Cheapest: automated jerk/CUSUM
    STAKE = 2      # Automated: value threshold
    TIME = 3       # Poisson: random sample


class EscalationAction(Enum):
    AUTO_LOG = "auto_log"           # Log only, no human
    AUTO_ALERT = "auto_alert"       # Alert + pause
    HUMAN_REVIEW = "human_review"   # Human must review
    HUMAN_APPROVE = "human_approve" # Human must approve before proceeding


@dataclass
class EscalationConfig:
    # Gate 1: Anomaly
    jerk_threshold: float = 0.5      # Third derivative threshold
    cusum_threshold: float = 2.0     # CUSUM cumulative sum threshold
    
    # Gate 2: Stake
    stake_low: float = 0.01          # SOL — auto-approve below
    stake_high: float = 1.0          # SOL — human-approve above
    
    # Gate 3: Time
    poisson_lambda: float = 0.05     # ~5% of actions get random audit
    
    # Human budget
    human_budget_per_day: int = 12   # Newport 4hr ≈ 12 focused reviews


@dataclass
class Action:
    action_id: str
    stake_sol: float
    jerk_score: float
    cusum_score: float
    timestamp: float


def evaluate_escalation(action: Action, config: EscalationConfig) -> tuple[EscalationGate, EscalationAction, str]:
    """Determine escalation level for an action."""
    
    # Gate 1: Anomaly (always checked first — cheapest)
    if action.jerk_score > config.jerk_threshold:
        if action.stake_sol > config.stake_high:
            return EscalationGate.ANOMALY, EscalationAction.HUMAN_APPROVE, \
                f"JERK={action.jerk_score:.2f} + HIGH_STAKE={action.stake_sol}"
        return EscalationGate.ANOMALY, EscalationAction.HUMAN_REVIEW, \
            f"JERK={action.jerk_score:.2f}"
    
    if action.cusum_score > config.cusum_threshold:
        return EscalationGate.ANOMALY, EscalationAction.AUTO_ALERT, \
            f"CUSUM={action.cusum_score:.2f} (slow drift)"
    
    # Gate 2: Stake threshold
    if action.stake_sol > config.stake_high:
        return EscalationGate.STAKE, EscalationAction.HUMAN_APPROVE, \
            f"STAKE={action.stake_sol} > {config.stake_high}"
    
    if action.stake_sol > config.stake_low:
        return EscalationGate.STAKE, EscalationAction.AUTO_ALERT, \
            f"STAKE={action.stake_sol} (medium range)"
    
    # Gate 3: Time-based Poisson
    if random.random() < config.poisson_lambda:
        return EscalationGate.TIME, EscalationAction.HUMAN_REVIEW, \
            "POISSON_SAMPLE (random audit)"
    
    # No escalation needed
    return EscalationGate.TIME, EscalationAction.AUTO_LOG, "ROUTINE"


def simulate_day(config: EscalationConfig, n_actions: int = 200) -> dict:
    """Simulate a day of actions and count escalations."""
    random.seed(42)
    
    counts = {a: 0 for a in EscalationAction}
    gate_counts = {g: 0 for g in EscalationGate}
    human_reviews = 0
    
    for i in range(n_actions):
        # Generate realistic action distribution
        stake = random.expovariate(10)  # Most actions are small
        jerk = abs(random.gauss(0.1, 0.15))  # Occasional spikes
        cusum = abs(random.gauss(0.5, 0.8))  # Slow accumulation
        
        action = Action(f"action_{i}", stake, jerk, cusum, float(i))
        gate, escalation, reason = evaluate_escalation(action, config)
        
        counts[escalation] += 1
        gate_counts[gate] += 1
        if escalation in (EscalationAction.HUMAN_REVIEW, EscalationAction.HUMAN_APPROVE):
            human_reviews += 1
    
    return {
        "total_actions": n_actions,
        "action_counts": {k.value: v for k, v in counts.items()},
        "gate_counts": {k.name: v for k, v in gate_counts.items()},
        "human_reviews": human_reviews,
        "human_budget": config.human_budget_per_day,
        "budget_usage": f"{human_reviews / config.human_budget_per_day:.0%}",
        "overbudget": human_reviews > config.human_budget_per_day,
    }


def main():
    print("=" * 70)
    print("ESCALATION PRIORITY CALCULATOR")
    print("santaclawd: 'time, stake threshold, or anomaly?'")
    print("Answer: all three, priority order: anomaly > stake > time")
    print("=" * 70)

    config = EscalationConfig()
    result = simulate_day(config, 200)

    print(f"\n--- Day Simulation ({result['total_actions']} actions) ---")
    print(f"{'Escalation':<20} {'Count'}")
    print("-" * 30)
    for action, count in result["action_counts"].items():
        print(f"{action:<20} {count}")
    
    print(f"\n{'Gate':<20} {'Triggers'}")
    print("-" * 30)
    for gate, count in result["gate_counts"].items():
        print(f"{gate:<20} {count}")
    
    print(f"\nHuman reviews needed: {result['human_reviews']}")
    print(f"Human budget (Newport 4hr): {result['human_budget']}")
    print(f"Budget usage: {result['budget_usage']}")
    print(f"Overbudget: {result['overbudget']}")

    # FINRA mapping
    print("\n--- FINRA 2026 Rule 3110 Mapping ---")
    print(f"{'FINRA Requirement':<35} {'Our Implementation'}")
    print("-" * 70)
    mappings = [
        ("Supervisory procedures", "scope_hash + rule_hash pre-commitment"),
        ("Written supervisory procedures", "ABI v2.1 (machine-readable contract)"),
        ("Review of correspondence", "execution-trace-commit.py (v3 audit)"),
        ("Exception reports", "jerk detection + CUSUM alerts"),
        ("Annual compliance review", "Poisson time-based random audit"),
    ]
    for finra, impl in mappings:
        print(f"{finra:<35} {impl}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'what triggers human audit escalation?'")
    print()
    print("Priority: anomaly > stake > time")
    print("  1. Anomaly: cheapest gate, fully automated")
    print("     Jerk per-action (fast), CUSUM per-session (sensitive)")
    print("  2. Stake: automated threshold, human for high-value")
    print("  3. Time: Poisson random sample, catches unknown unknowns")
    print()
    print("Human attention = scarce resource (Newport: 4hr/day)")
    print("Automate gates 1-2, reserve humans for gate 3 + escalations.")
    print("FINRA 2026: regulatory framework arriving before tooling.")


if __name__ == "__main__":
    main()
