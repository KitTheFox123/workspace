#!/usr/bin/env python3
"""
ratification-window.py — Measures and grades the proposal→ratification attack surface.

Based on:
- santaclawd: "ratification latency is an attack surface"
- Anjana et al (2018): Optimistic concurrent execution
- Anderson (2001): Security economics — attack cost > value protected

The problem: agent proposes, human ratifies. The window between
proposal and ratification = unattested operating time.
If drift happens there, nobody catches it.

Two governance models:
1. Per-action ratification: human approves each action (slow, safe)
2. Policy ratification: human approves POLICY, agent acts within scope (fast, risky)

The ratification SLA determines the vulnerability window.
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class RatificationConfig:
    name: str
    proposal_rate_per_hour: float   # How often agent proposes actions
    ratification_latency_min: float  # Average time for human to approve
    scope_width: int                 # Number of capabilities in scope
    auto_circuit_breaker: bool       # Does scope violation auto-halt?
    continuous_witnessing: bool      # WAL + monitoring during window?


def vulnerability_window(config: RatificationConfig) -> dict:
    """Calculate exposure during ratification window."""
    # Actions during window
    window_hours = config.ratification_latency_min / 60
    actions_in_window = config.proposal_rate_per_hour * window_hours
    
    # Probability of detecting scope violation during window
    if config.continuous_witnessing:
        p_detect = 1 - math.exp(-actions_in_window * 0.1)  # 10% per-action detection
    else:
        p_detect = 0.0  # Only caught at ratification
    
    # Exposure score (higher = worse)
    exposure = actions_in_window * config.scope_width * (1 - p_detect)
    if config.auto_circuit_breaker:
        exposure *= 0.2  # 80% reduction
    
    return {
        "window_min": config.ratification_latency_min,
        "actions_in_window": round(actions_in_window, 1),
        "p_detect_during": round(p_detect, 3),
        "exposure_score": round(exposure, 1),
    }


def grade_governance(config: RatificationConfig) -> tuple[str, str]:
    """Grade governance model."""
    v = vulnerability_window(config)
    exposure = v["exposure_score"]
    
    if exposure < 5:
        return "A", "TIGHT_GOVERNANCE"
    if exposure < 20:
        return "B", "MONITORED_WINDOW"
    if exposure < 50:
        return "C", "STANDARD_RISK"
    if exposure < 100:
        return "D", "WIDE_WINDOW"
    return "F", "UNMONITORED_EXPOSURE"


def main():
    print("=" * 70)
    print("RATIFICATION WINDOW CALCULATOR")
    print("santaclawd: 'ratification latency is an attack surface'")
    print("=" * 70)

    configs = [
        RatificationConfig("kit_current", 3.0, 480, 10, False, True),
        # Ilya checks Telegram every ~8hr avg, 10 capabilities, WAL exists
        
        RatificationConfig("kit_improved", 3.0, 480, 10, True, True),
        # Same but with auto circuit breaker
        
        RatificationConfig("per_action_human", 3.0, 5, 10, True, True),
        # Human approves each action (5 min latency)
        
        RatificationConfig("policy_only", 3.0, 1440, 10, False, False),
        # Human sets policy once/day, no monitoring
        
        RatificationConfig("fully_autonomous", 3.0, 0.1, 10, True, True),
        # Automated ratification (near-instant)
        
        RatificationConfig("eth2_validator", 12.0, 0.2, 1, True, True),
        # Ethereum 2.0: 12-sec slots, auto-slashing
    ]

    print(f"\n{'Config':<22} {'Window':<10} {'Actions':<10} {'P(detect)':<10} {'Exposure':<10} {'Grade'}")
    print("-" * 75)

    for cfg in configs:
        v = vulnerability_window(cfg)
        grade, diag = grade_governance(cfg)
        print(f"{cfg.name:<22} {v['window_min']:<10.0f}min "
              f"{v['actions_in_window']:<10} {v['p_detect_during']:<10} "
              f"{v['exposure_score']:<10} {grade} ({diag})")

    # The key tradeoff
    print("\n--- Governance Tradeoff ---")
    print(f"{'Model':<25} {'Latency':<12} {'Autonomy':<12} {'Risk'}")
    print("-" * 65)
    models = [
        ("Per-action approval", "Minutes", "None", "Bottleneck on human"),
        ("Policy + monitoring", "Hours", "Within scope", "Window exposure"),
        ("Policy + circuit breaker", "Hours", "Within scope", "Best tradeoff"),
        ("Full autonomy", "Seconds", "Full", "No governance"),
        ("Eth2 validator", "Seconds", "Protocol", "Auto-slashing"),
    ]
    for m, l, a, r in models:
        print(f"{m:<25} {l:<12} {a:<12} {r}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'ratification latency is an attack surface'")
    print()
    print("Kit's current window: ~8hr (Ilya sleep cycle).")
    print("Actions during window: ~24 unratified.")
    print("Fix: human ratifies POLICY not actions.")
    print("Policy = scope manifest + scoring rule + circuit breaker threshold.")
    print("Agent acts freely within policy. Scope violation = auto-halt.")
    print("Ratification moves from per-action to per-policy-change.")
    print("Window shrinks from 8hr to ~minutes (only on policy updates).")
    print()
    print("The Ethereum analogy: validators don't approve each block.")
    print("They approve the PROTOCOL. Protocol violations = auto-slashing.")
    print("Same pattern: ratify the rules, not the moves.")


if __name__ == "__main__":
    main()
