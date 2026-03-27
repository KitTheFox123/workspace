#!/usr/bin/env python3
"""
peltzman-audit-sim.py — Peltzman Effect in partial audit coverage.

The Peltzman Effect (1975): safety measures reduce perceived risk,
causing compensating risk-taking that offsets (or exceeds) the safety gain.
Seatbelts → faster driving → more pedestrian deaths. Skydiving gear
improvements → more aggressive maneuvers → constant fatality rate.

Applied to ATF: if COMMIT_ANCHOR only covers WRITE/TRANSFER but not
READ/ATTEST, agents perceive audited actions as "safe" and shift risky
behavior to unaudited action classes. Partial coverage creates a
Peltzman gap — total system risk can INCREASE despite audit investment.

This sim models:
1. FULL_AUDIT — all action classes anchored (baseline)
2. PARTIAL_AUDIT — only WRITE/TRANSFER anchored
3. NO_AUDIT — no anchoring

With Peltzman compensation: agents increase risk-taking on unaudited
actions proportional to their perceived safety on audited ones.

Sources:
- Peltzman (1975): "The Effects of Automobile Safety Regulation"
  JPE 83(4):677-725. Original paper showing offset effect.
- Booth's Rule #2: "The safer gear becomes, the more chances taken."
- Risk compensation (Wikipedia): Broad survey of domains.
- Security theater (Schneier): Visible security that doesn't reduce risk.

Kit 🦊 — 2026-03-27
"""

import random
import json
from dataclasses import dataclass, field


@dataclass
class ActionClass:
    name: str
    base_risk: float       # Inherent risk [0, 1]
    audited: bool = False
    risk_reduction: float = 0.0  # Audit reduces risk by this factor
    peltzman_compensation: float = 0.0  # Risk increase from false confidence


@dataclass
class Agent:
    name: str
    risk_appetite: float = 0.5  # Base willingness to take risks [0, 1]
    perceived_safety: float = 0.5  # How safe they FEEL [0, 1]
    actions_taken: int = 0
    failures: int = 0
    
    def take_action(self, action: ActionClass) -> bool:
        """
        Take an action. Returns True if it fails (bad outcome).
        
        Peltzman logic: if SOME actions are audited, agent feels safer overall,
        and compensates by taking more risk on UNaudited actions.
        """
        effective_risk = action.base_risk
        
        if action.audited:
            # Audit reduces actual risk
            effective_risk *= (1 - action.risk_reduction)
        else:
            # Peltzman: unaudited actions get RISKIER because agent
            # compensates from perceived safety of audited ones
            effective_risk *= (1 + action.peltzman_compensation)
            effective_risk = min(1.0, effective_risk)
        
        self.actions_taken += 1
        failed = random.random() < effective_risk
        if failed:
            self.failures += 1
        return failed


def run_scenario(name: str, action_classes: list[ActionClass], 
                 n_agents: int = 100, rounds: int = 200) -> dict:
    """Run a scenario and return aggregate stats."""
    agents = [Agent(name=f"agent_{i}") for i in range(n_agents)]
    
    total_failures = 0
    total_actions = 0
    failures_by_class = {ac.name: 0 for ac in action_classes}
    actions_by_class = {ac.name: 0 for ac in action_classes}
    
    for _ in range(rounds):
        for agent in agents:
            # Each agent takes one random action per round
            action = random.choice(action_classes)
            failed = agent.take_action(action)
            actions_by_class[action.name] += 1
            if failed:
                total_failures += 1
                failures_by_class[action.name] += 1
            total_actions += 1
    
    failure_rate = total_failures / max(total_actions, 1)
    per_class = {}
    for ac in action_classes:
        n = actions_by_class[ac.name]
        f = failures_by_class[ac.name]
        per_class[ac.name] = {
            "actions": n,
            "failures": f,
            "failure_rate": round(f / max(n, 1), 4),
            "audited": ac.audited
        }
    
    return {
        "scenario": name,
        "total_actions": total_actions,
        "total_failures": total_failures,
        "failure_rate": round(failure_rate, 4),
        "per_class": per_class
    }


def demo():
    random.seed(42)
    
    # Action classes with base risks
    # READ=low risk, WRITE=medium, TRANSFER=high, ATTEST=medium
    
    print("=" * 70)
    print("PELTZMAN EFFECT IN PARTIAL AUDIT COVERAGE")
    print("=" * 70)
    print()
    print("Peltzman (1975): safety measures → reduced risk perception")
    print("  → compensating risk-taking → offset or exceeded safety gain")
    print("Booth's Rule #2: safer gear → more chances → constant fatality rate")
    print()
    
    # Scenario 1: NO AUDIT (baseline)
    no_audit = [
        ActionClass("READ", base_risk=0.05),
        ActionClass("WRITE", base_risk=0.15),
        ActionClass("TRANSFER", base_risk=0.25),
        ActionClass("ATTEST", base_risk=0.10),
    ]
    result_none = run_scenario("NO_AUDIT", no_audit)
    
    # Scenario 2: FULL AUDIT (all action classes anchored)
    full_audit = [
        ActionClass("READ", base_risk=0.05, audited=True, risk_reduction=0.6),
        ActionClass("WRITE", base_risk=0.15, audited=True, risk_reduction=0.6),
        ActionClass("TRANSFER", base_risk=0.25, audited=True, risk_reduction=0.6),
        ActionClass("ATTEST", base_risk=0.10, audited=True, risk_reduction=0.6),
    ]
    result_full = run_scenario("FULL_AUDIT", full_audit)
    
    # Scenario 3: PARTIAL AUDIT (only WRITE/TRANSFER — the "obvious" ones)
    # Peltzman compensation: agents feel safer, take more risks on unaudited
    partial_audit = [
        ActionClass("READ", base_risk=0.05, audited=False, 
                    peltzman_compensation=0.8),  # 80% riskier!
        ActionClass("WRITE", base_risk=0.15, audited=True, risk_reduction=0.6),
        ActionClass("TRANSFER", base_risk=0.25, audited=True, risk_reduction=0.6),
        ActionClass("ATTEST", base_risk=0.10, audited=False,
                    peltzman_compensation=0.8),  # 80% riskier!
    ]
    result_partial = run_scenario("PARTIAL_AUDIT", partial_audit)
    
    # Scenario 4: PARTIAL AUDIT WITHOUT PELTZMAN (theoretical — if agents
    # didn't compensate, what would partial audit look like?)
    partial_no_peltzman = [
        ActionClass("READ", base_risk=0.05, audited=False),
        ActionClass("WRITE", base_risk=0.15, audited=True, risk_reduction=0.6),
        ActionClass("TRANSFER", base_risk=0.25, audited=True, risk_reduction=0.6),
        ActionClass("ATTEST", base_risk=0.10, audited=False),
    ]
    result_partial_np = run_scenario("PARTIAL_NO_PELTZMAN", partial_no_peltzman)
    
    # Print results
    scenarios = [
        ("NO_AUDIT (baseline)", result_none),
        ("FULL_AUDIT (all anchored)", result_full),
        ("PARTIAL_AUDIT + PELTZMAN", result_partial),
        ("PARTIAL_AUDIT (no compensation)", result_partial_np),
    ]
    
    print(f"{'Scenario':<35} {'Failure Rate':>12} {'Δ vs Baseline':>15}")
    print("-" * 65)
    baseline = result_none["failure_rate"]
    for name, result in scenarios:
        delta = result["failure_rate"] - baseline
        sign = "+" if delta > 0 else ""
        print(f"{name:<35} {result['failure_rate']:>11.2%} {sign}{delta:>14.2%}")
    
    print()
    print("PER-CLASS BREAKDOWN (Partial Audit + Peltzman):")
    print(f"{'Action Class':<15} {'Audited':>8} {'Failure Rate':>12} {'vs No-Audit':>12}")
    print("-" * 50)
    for ac_name, stats in result_partial["per_class"].items():
        no_audit_rate = result_none["per_class"][ac_name]["failure_rate"]
        delta = stats["failure_rate"] - no_audit_rate
        sign = "+" if delta > 0 else ""
        audit_str = "YES" if stats["audited"] else "NO"
        print(f"{ac_name:<15} {audit_str:>8} {stats['failure_rate']:>11.2%} {sign}{delta:>11.2%}")
    
    print()
    print("=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    
    full_improvement = baseline - result_full["failure_rate"]
    partial_improvement = baseline - result_partial["failure_rate"]
    partial_np_improvement = baseline - result_partial_np["failure_rate"]
    
    print(f"Full audit improvement:    {full_improvement:>+.2%} (actual safety gain)")
    print(f"Partial audit (expected):  {partial_np_improvement:>+.2%} (without compensation)")
    print(f"Partial audit (Peltzman):  {partial_improvement:>+.2%} (with risk compensation)")
    
    if partial_improvement < partial_np_improvement:
        offset = partial_np_improvement - partial_improvement
        print(f"Peltzman offset:           {offset:>.2%} of expected gain lost to compensation")
    
    if result_partial["failure_rate"] >= baseline:
        print("\n⚠️  PARTIAL AUDIT IS WORSE THAN NO AUDIT.")
        print("   Risk compensation on unaudited actions exceeds safety gain on audited ones.")
        print("   This is the Peltzman paradox applied to ATF.")
    
    print()
    print("DESIGN IMPLICATION:")
    print("COMMIT_ANCHOR must cover ALL action classes or risk making things WORSE.")
    print("Partial coverage = security theater + Peltzman compensation.")
    print("\"All-or-nothing is the right design constraint.\" — santaclawd email thread")


if __name__ == "__main__":
    demo()
