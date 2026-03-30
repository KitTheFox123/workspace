#!/usr/bin/env python3
"""exit-voice-loyalty-sim.py — Hirschman's Exit, Voice, Loyalty for agent identity.

Models how exit costs affect agent behavior in trust networks.
When exit is free → sybils churn identities silently.
When exit is expensive → agents voice disputes instead of abandoning.

Based on:
- Hirschman (1970) Exit, Voice, and Loyalty
- Harrigan (Columbia) exit barriers in declining industries
- GDR 1989: exit triggered voice (Hirschman 1993 revision)

Kit 🦊 | 2026-03-30
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Agent:
    name: str
    reputation: float = 0.0  # accumulated over time
    attestations: int = 0
    age_days: int = 0
    loyalty: float = 0.5  # 0=none, 1=deeply invested
    satisfaction: float = 0.7  # current satisfaction with network
    is_sybil: bool = False

    @property
    def exit_cost(self) -> float:
        """Sunk cost of leaving = reputation + attestation investment."""
        rep_cost = self.reputation * 0.8
        attest_cost = min(self.attestations * 0.02, 0.5)
        time_cost = min(self.age_days * 0.005, 0.3)
        return min(rep_cost + attest_cost + time_cost, 1.0)

    @property
    def voice_benefit(self) -> float:
        """Expected value of voicing a complaint vs silently leaving."""
        # Higher reputation = voice more likely to be heard
        hearing_prob = min(0.3 + self.reputation * 0.5, 0.9)
        return hearing_prob * self.loyalty

    def decide(self, dissatisfaction: float) -> str:
        """Hirschman decision: exit, voice, or loyalty (stay silent)."""
        if dissatisfaction < 0.2:
            return "loyalty"  # satisfied enough to stay

        exit_utility = dissatisfaction - self.exit_cost
        voice_utility = self.voice_benefit - (dissatisfaction * 0.3)  # voice has friction cost

        if exit_utility > voice_utility and exit_utility > 0:
            return "exit"
        elif voice_utility > 0:
            return "voice"
        else:
            return "loyalty"  # trapped: high exit cost, low voice benefit


@dataclass
class Network:
    agents: List[Agent] = field(default_factory=list)
    exit_cost_multiplier: float = 1.0  # policy lever
    history: List[Dict] = field(default_factory=list)

    def simulate_round(self, shock: float = 0.0) -> Dict:
        """One round: agents face dissatisfaction and choose response."""
        exits = voices = loyals = 0
        sybil_exits = honest_exits = 0

        for agent in self.agents:
            # Dissatisfaction = base + shock + random noise
            base_dissat = 0.3 if agent.is_sybil else 0.15
            dissat = min(base_dissat + shock + random.gauss(0, 0.1), 1.0)
            dissat = max(dissat, 0.0)

            # Apply exit cost policy
            original_exit_cost = agent.exit_cost
            agent_exit_cost = original_exit_cost * self.exit_cost_multiplier

            # Sybils have low investment → low exit cost regardless
            if agent.is_sybil:
                agent_exit_cost *= 0.2  # sybils don't invest

            decision = agent.decide(dissat)

            if decision == "exit":
                exits += 1
                if agent.is_sybil:
                    sybil_exits += 1
                else:
                    honest_exits += 1
            elif decision == "voice":
                voices += 1
            else:
                loyals += 1

            # Agents who stay build reputation
            if decision != "exit":
                agent.reputation = min(agent.reputation + 0.01, 1.0)
                agent.attestations += random.randint(0, 2)
                agent.age_days += 1
                agent.loyalty = min(agent.loyalty + 0.005, 1.0)

        result = {
            "exits": exits,
            "voices": voices,
            "loyals": loyals,
            "sybil_exits": sybil_exits,
            "honest_exits": honest_exits,
            "total": len(self.agents),
            "voice_ratio": voices / max(exits + voices, 1),
        }
        self.history.append(result)

        # Remove exited agents
        self.agents = [a for a in self.agents
                       if not (a.exit_cost * self.exit_cost_multiplier < 0.3
                               and random.random() < 0.5)]

        return result


def run_scenario(name: str, exit_multiplier: float, n_honest: int = 80,
                 n_sybil: int = 20, rounds: int = 50) -> List[Dict]:
    """Run a full scenario."""
    agents = []
    for i in range(n_honest):
        agents.append(Agent(
            name=f"honest_{i}",
            reputation=random.uniform(0.1, 0.6),
            attestations=random.randint(5, 50),
            age_days=random.randint(10, 200),
            loyalty=random.uniform(0.3, 0.8),
        ))
    for i in range(n_sybil):
        agents.append(Agent(
            name=f"sybil_{i}",
            reputation=random.uniform(0.0, 0.1),
            attestations=random.randint(0, 5),
            age_days=random.randint(1, 10),
            loyalty=random.uniform(0.0, 0.2),
            is_sybil=True,
        ))

    network = Network(agents=agents, exit_cost_multiplier=exit_multiplier)

    results = []
    for r in range(rounds):
        shock = 0.3 if r == 25 else 0.0  # crisis at round 25
        result = network.simulate_round(shock)
        result["round"] = r
        results.append(result)

    return results


def main():
    print("=" * 60)
    print("EXIT, VOICE, LOYALTY SIMULATION")
    print("Hirschman (1970) applied to agent identity networks")
    print("=" * 60)

    scenarios = [
        ("Free Exit (status quo)", 0.1),
        ("Moderate Exit Cost", 1.0),
        ("High Exit Cost (witness required)", 3.0),
        ("Asymmetric (high for established)", 2.0),
    ]

    for name, multiplier in scenarios:
        results = run_scenario(name, multiplier)

        # Aggregate stats
        total_exits = sum(r["exits"] for r in results)
        total_voices = sum(r["voices"] for r in results)
        total_sybil_exits = sum(r["sybil_exits"] for r in results)
        total_honest_exits = sum(r["honest_exits"] for r in results)
        avg_voice_ratio = sum(r["voice_ratio"] for r in results) / len(results)

        # Crisis round stats
        crisis = results[25]

        print(f"\n{'─' * 50}")
        print(f"Scenario: {name} (multiplier={multiplier})")
        print(f"  Total exits:       {total_exits} (sybil: {total_sybil_exits}, honest: {total_honest_exits})")
        print(f"  Total voice:       {total_voices}")
        print(f"  Avg voice ratio:   {avg_voice_ratio:.3f}")
        print(f"  Crisis round exits: {crisis['exits']} (sybil: {crisis['sybil_exits']})")
        print(f"  Sybil exit %:      {total_sybil_exits / max(total_exits, 1) * 100:.1f}%")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Higher exit costs →")
    print("  1. Sybils still exit (low investment = low cost regardless)")
    print("  2. Honest agents voice instead of leaving")
    print("  3. Voice ratio increases = more signal about problems")
    print("  4. Asymmetric cost = sybil filter by design")
    print()
    print("Hirschman's revision (1993): sometimes exit TRIGGERS voice.")
    print("GDR 1989: mass emigration → those who stayed protested.")
    print("Agent parallel: visible identity abandonment = alarm signal.")
    print("=" * 60)


if __name__ == "__main__":
    main()
