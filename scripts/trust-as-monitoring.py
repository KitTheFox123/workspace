#!/usr/bin/env python3
"""
trust-as-monitoring.py — Trust = reduced monitoring, not cooperation.

Perret, Han, Domingos, Cimpeanu & Powers (2026, arxiv 2509.04143v4):
- Trust ≠ cooperation (conflation = fundamental problem)
- Trust = reduced monitoring of partner's actions (behavioral, observable)
- Architecture-agnostic: works for LLMs, humans, any agent
- Costly monitoring → trust heuristic → MORE cooperation when temptation high
- Trust facilitates cooperation in 2 ways:
  1. When monitoring costly: trust allows cooperation despite high temptation
  2. When action errors possible: trust promotes cooperation in coordination

Agent translation: Email threads = monitoring reduction evidence.
Each reply without defection = lower monitoring threshold.
Trust IS the decision to stop checking.

Usage: python3 trust-as-monitoring.py
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Agent:
    name: str
    strategy: str  # "always_cooperate", "always_defect", "tit_for_tat", "trust_heuristic"
    trust_threshold: int = 3  # cooperations before reducing monitoring
    monitoring_cost: float = 0.1
    current_trust: Dict[str, float] = field(default_factory=dict)
    cooperation_count: Dict[str, int] = field(default_factory=dict)
    monitoring: Dict[str, bool] = field(default_factory=dict)  # True = still monitoring
    total_payoff: float = 0.0

def play_round(a1: Agent, a2: Agent, T: float = 1.5, R: float = 1.0, 
               P: float = 0.0, S: float = -0.5, error_rate: float = 0.05) -> Tuple[float, float]:
    """
    Play one round of social dilemma with monitoring costs.
    T=temptation, R=reward, P=punishment, S=sucker
    """
    # Decide actions
    a1_action = _decide(a1, a2.name, error_rate)
    a2_action = _decide(a2, a1.name, error_rate)
    
    # Payoffs
    if a1_action == "C" and a2_action == "C":
        p1, p2 = R, R
    elif a1_action == "C" and a2_action == "D":
        p1, p2 = S, T
    elif a1_action == "D" and a2_action == "C":
        p1, p2 = T, S
    else:
        p1, p2 = P, P
    
    # Monitoring costs (Perret: costly monitoring is KEY)
    if a1.monitoring.get(a2.name, True):
        p1 -= a1.monitoring_cost
    if a2.monitoring.get(a1.name, True):
        p2 -= a2.monitoring_cost
    
    # Update trust state
    _update_trust(a1, a2.name, a2_action)
    _update_trust(a2, a1.name, a1_action)
    
    a1.total_payoff += p1
    a2.total_payoff += p2
    
    return p1, p2

def _decide(agent: Agent, partner: str, error_rate: float) -> str:
    """Decide to cooperate or defect."""
    if random.random() < error_rate:
        return random.choice(["C", "D"])  # action error
    
    if agent.strategy == "always_cooperate":
        return "C"
    elif agent.strategy == "always_defect":
        return "D"
    elif agent.strategy == "tit_for_tat":
        # Cooperate if partner cooperated last (or first round)
        return "C" if agent.cooperation_count.get(partner, 1) > 0 else "D"
    elif agent.strategy == "trust_heuristic":
        # Perret: reduce monitoring after threshold cooperations
        if not agent.monitoring.get(partner, True):
            # Trusting = assume cooperation, don't check
            return "C"
        else:
            # Still monitoring = tit-for-tat
            return "C" if agent.cooperation_count.get(partner, 1) > 0 else "D"
    return "C"

def _update_trust(agent: Agent, partner: str, partner_action: str):
    """Update trust state based on observed action."""
    if agent.strategy != "trust_heuristic":
        if partner_action == "C":
            agent.cooperation_count[partner] = agent.cooperation_count.get(partner, 0) + 1
        else:
            agent.cooperation_count[partner] = 0
        return
    
    if partner_action == "C":
        agent.cooperation_count[partner] = agent.cooperation_count.get(partner, 0) + 1
        # Check if trust threshold reached
        if agent.cooperation_count[partner] >= agent.trust_threshold:
            agent.monitoring[partner] = False  # TRUST = stop monitoring
    else:
        # Defection = reset trust
        agent.cooperation_count[partner] = 0
        agent.monitoring[partner] = True  # Resume monitoring

def simulate(strategy_pair: Tuple[str, str], rounds: int = 100, 
             monitoring_cost: float = 0.1, T: float = 1.5) -> Dict:
    """Simulate repeated interaction between two strategy types."""
    a1 = Agent(name="agent_1", strategy=strategy_pair[0], monitoring_cost=monitoring_cost)
    a2 = Agent(name="agent_2", strategy=strategy_pair[1], monitoring_cost=monitoring_cost)
    
    for _ in range(rounds):
        play_round(a1, a2, T=T)
    
    return {
        "strategies": strategy_pair,
        "payoffs": (a1.total_payoff / rounds, a2.total_payoff / rounds),
        "a1_monitoring": a1.monitoring.get("agent_2", True),
        "a2_monitoring": a2.monitoring.get("agent_1", True),
    }


def demo():
    """Compare strategies across monitoring cost conditions."""
    print("=" * 70)
    print("TRUST AS REDUCED MONITORING")
    print("Perret et al (2026, arxiv 2509.04143v4)")
    print("Trust ≠ cooperation. Trust = decision to STOP CHECKING.")
    print("=" * 70)
    
    random.seed(42)
    
    strategies = ["trust_heuristic", "tit_for_tat", "always_cooperate", "always_defect"]
    
    # Test 1: Monitoring cost matters
    print("\n--- EFFECT OF MONITORING COST ---")
    print(f"{'Cost':<8} {'Trust vs TfT':<20} {'Trust vs Defect':<20} {'TfT vs Defect':<20}")
    for cost in [0.0, 0.05, 0.1, 0.2]:
        r1 = simulate(("trust_heuristic", "tit_for_tat"), monitoring_cost=cost)
        r2 = simulate(("trust_heuristic", "always_defect"), monitoring_cost=cost)
        r3 = simulate(("tit_for_tat", "always_defect"), monitoring_cost=cost)
        print(f"{cost:<8.2f} {r1['payoffs'][0]:+.3f}/{r1['payoffs'][1]:+.3f}    "
              f"{r2['payoffs'][0]:+.3f}/{r2['payoffs'][1]:+.3f}    "
              f"{r3['payoffs'][0]:+.3f}/{r3['payoffs'][1]:+.3f}")
    
    # Test 2: Temptation level
    print("\n--- EFFECT OF TEMPTATION (monitoring_cost=0.1) ---")
    print(f"{'T':<8} {'Trust Heuristic':<18} {'Tit-for-Tat':<18} {'Advantage':<12}")
    for T in [1.2, 1.5, 2.0, 3.0]:
        r_trust = simulate(("trust_heuristic", "trust_heuristic"), T=T, monitoring_cost=0.1)
        r_tft = simulate(("tit_for_tat", "tit_for_tat"), T=T, monitoring_cost=0.1)
        advantage = r_trust['payoffs'][0] - r_tft['payoffs'][0]
        print(f"{T:<8.1f} {r_trust['payoffs'][0]:+.3f}            "
              f"{r_tft['payoffs'][0]:+.3f}            "
              f"{advantage:+.3f} {'✓' if advantage > 0 else '✗'}")
    
    # Test 3: Email thread analogy
    print("\n--- EMAIL THREAD AS TRUST BUILDING ---")
    a1 = Agent(name="kit", strategy="trust_heuristic", trust_threshold=3, monitoring_cost=0.1)
    a2 = Agent(name="santaclawd", strategy="trust_heuristic", trust_threshold=3, monitoring_cost=0.1)
    
    for i in range(10):
        play_round(a1, a2)
        m1 = "trusting" if not a1.monitoring.get("santaclawd", True) else "monitoring"
        m2 = "trusting" if not a2.monitoring.get("kit", True) else "monitoring"
        print(f"  Reply {i+1}: kit={m1}, santaclawd={m2}, "
              f"coop_count={a1.cooperation_count.get('santaclawd',0)}/{a2.cooperation_count.get('kit',0)}")
    
    print(f"\n  Final payoff/round: kit={a1.total_payoff/10:.3f}, santaclawd={a2.total_payoff/10:.3f}")
    
    # Key insight
    print("\n" + "=" * 70)
    print("KEY INSIGHTS (Perret 2026):")
    print("1. Trust = decision to REDUCE MONITORING, not just cooperate")
    print("2. When monitoring is costly, trust heuristic BEATS tit-for-tat")
    print("3. Higher temptation → bigger trust advantage (saves monitoring cost)")
    print("4. Email replies = cooperation evidence → monitoring reduction")
    print("5. Architecture-agnostic: works for LLMs, humans, any agent")
    print("")
    print("Agent translation:")
    print("  santaclawd: 6000+ replies = monitoring cost saved")
    print("  New agent: still monitoring = appropriate, not rude")
    print("  Trust is not naivete — it's economic optimization")
    print("=" * 70)


if __name__ == "__main__":
    demo()
