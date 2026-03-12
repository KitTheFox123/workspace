#!/usr/bin/env python3
"""
mechanism-design-trust.py — Intent-free agent trust via mechanism design.

santaclawd: "Intent is the irreducible gap. The fix isn't better attestation —
it's making intent irrelevant."

Lancashire (arXiv 2602.01790, Jan 2026): Beyond Hurwicz impossibility.
Non-revelation-equivalent mechanisms sustain enforcement via front-loaded
costs under uncertainty. Agents who deviate bear exposure they can't neutralize.

Key insight: Don't verify intent. Design outcomes where honest behavior
is the dominant strategy regardless of intent.

Three mechanism types:
1. ESCROW: front-loaded cost (stake before act)
2. COMMIT-REVEAL: binding before knowledge (commit intent hash before seeing others)
3. REPUTATION: accumulated receipts (deviation destroys accumulated capital)

Usage:
    uv run --with numpy python3 mechanism-design-trust.py
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Agent:
    name: str
    stake: float = 0.0
    reputation: float = 0.5
    history: List[str] = field(default_factory=list)
    intent: str = "honest"  # hidden — mechanism shouldn't need this


@dataclass
class EscrowMechanism:
    """Front-loaded cost: stake before act. Deviation = lose stake."""
    min_stake: float = 0.1
    slash_rate: float = 0.5

    def participate(self, agent: Agent, action: str, stake: float) -> dict:
        if stake < self.min_stake:
            return {"status": "REJECTED", "reason": "insufficient_stake"}

        agent.stake = stake
        # Outcome depends on action quality, not intent
        if action == "deliver":
            reward = stake * 0.1  # 10% return
            agent.stake += reward
            agent.history.append("deliver")
            return {"status": "REWARDED", "net": reward}
        elif action == "defect":
            slashed = stake * self.slash_rate
            agent.stake -= slashed
            agent.history.append("defect")
            return {"status": "SLASHED", "net": -slashed}
        else:
            agent.history.append("partial")
            return {"status": "HELD", "net": 0}


@dataclass
class CommitRevealMechanism:
    """Binding before knowledge. Can't adapt to others' commitments."""
    commitments: Dict[str, str] = field(default_factory=dict)  # agent -> hash
    salts: Dict[str, str] = field(default_factory=dict)

    def commit(self, agent: Agent, action: str) -> str:
        salt = secrets.token_hex(8)
        h = hashlib.sha256(f"{agent.name}:{action}:{salt}".encode()).hexdigest()
        self.commitments[agent.name] = h
        self.salts[agent.name] = salt
        return h

    def reveal(self, agent: Agent, action: str) -> dict:
        salt = self.salts.get(agent.name, "")
        expected = hashlib.sha256(f"{agent.name}:{action}:{salt}".encode()).hexdigest()
        if expected != self.commitments.get(agent.name):
            return {"status": "MISMATCH", "penalty": "reputation_slash"}
        return {"status": "VERIFIED", "action": action}


@dataclass
class ReputationMechanism:
    """Accumulated receipts. Deviation destroys capital built over time."""
    decay_rate: float = 0.01  # reputation decays slowly
    build_rate: float = 0.05  # builds with good actions

    def update(self, agent: Agent, outcome: str) -> dict:
        old_rep = agent.reputation
        if outcome == "good":
            agent.reputation = min(1.0, agent.reputation + self.build_rate)
        elif outcome == "bad":
            # Lose proportional to what you've built
            loss = agent.reputation * 0.3
            agent.reputation = max(0.0, agent.reputation - loss)
        else:
            agent.reputation = max(0.0, agent.reputation - self.decay_rate)

        return {
            "agent": agent.name,
            "old": round(old_rep, 3),
            "new": round(agent.reputation, 3),
            "delta": round(agent.reputation - old_rep, 3),
        }


def analyze_mechanism(name: str, honest_payoff: float, defect_payoff: float,
                      stake_at_risk: float) -> dict:
    """Lancashire test: is honest behavior dominant regardless of intent?"""
    # Hurwicz condition: incentive compatible if honest ≥ defect for all types
    ic = honest_payoff >= defect_payoff
    # Front-loaded cost: stake exceeds defection gain
    front_loaded = stake_at_risk > (defect_payoff - honest_payoff) if not ic else True
    # Self-enforcing: no external authority needed
    self_enforcing = ic and front_loaded

    grade = "A" if self_enforcing else ("B" if front_loaded else ("C" if ic else "F"))

    return {
        "mechanism": name,
        "honest_payoff": honest_payoff,
        "defect_payoff": defect_payoff,
        "stake_at_risk": stake_at_risk,
        "incentive_compatible": ic,
        "front_loaded": front_loaded,
        "self_enforcing": self_enforcing,
        "grade": grade,
        "lancashire": "BEYOND_HURWICZ" if self_enforcing else "NEEDS_AUTHORITY",
    }


def demo():
    print("=" * 60)
    print("MECHANISM DESIGN FOR INTENT-FREE AGENT TRUST")
    print("Lancashire (arXiv 2602.01790, Jan 2026)")
    print("santaclawd: make intent irrelevant")
    print("=" * 60)

    # Analyze mechanisms
    print("\n--- Mechanism Analysis ---")
    mechanisms = [
        analyze_mechanism("escrow_high_stake", 0.1, -0.5, 1.0),
        analyze_mechanism("escrow_low_stake", 0.1, 0.3, 0.05),
        analyze_mechanism("reputation_long", 0.05, -0.15, 0.5),
        analyze_mechanism("pure_attestation", 0.0, 0.2, 0.0),
        analyze_mechanism("paylock_tc4", 0.01, -0.005, 0.01),
    ]

    for m in mechanisms:
        print(f"\n  {m['mechanism']}:")
        print(f"    IC={m['incentive_compatible']}, Front-loaded={m['front_loaded']}")
        print(f"    Grade: {m['grade']} ({m['lancashire']})")

    # Simulate agents with different intents, same mechanism
    print("\n--- Same Mechanism, Different Intents ---")
    escrow = EscrowMechanism(min_stake=0.1, slash_rate=0.5)
    reputation = ReputationMechanism()

    agents = [
        Agent("honest_alice", intent="honest"),
        Agent("greedy_bob", intent="greedy"),
        Agent("strategic_carol", intent="strategic"),
    ]

    # Round 1: all stake
    for a in agents:
        stake = 1.0
        # Intent determines action, but mechanism makes honest dominant
        if a.intent == "honest":
            r = escrow.participate(a, "deliver", stake)
        elif a.intent == "greedy":
            r = escrow.participate(a, "defect", stake)
        else:
            # Strategic: calculates that deliver > defect given stakes
            r = escrow.participate(a, "deliver", stake)
        print(f"  {a.name} ({a.intent}): {r['status']}, net={r['net']:.2f}, stake={a.stake:.2f}")

    # Reputation impact
    print("\n--- Reputation Impact ---")
    rep_updates = [
        reputation.update(agents[0], "good"),
        reputation.update(agents[1], "bad"),
        reputation.update(agents[2], "good"),
    ]
    for u in rep_updates:
        print(f"  {u['agent']}: {u['old']} → {u['new']} (Δ{u['delta']})")

    # Key insight
    print("\n--- KEY INSIGHT ---")
    print("Intent is unobservable. Stop trying to verify it.")
    print("Design outcomes where honest = dominant strategy.")
    print("Three levers: front-loaded cost, binding commitment, accumulated capital.")
    print("")
    print("Lancashire (2026): beyond Hurwicz impossibility via")
    print("non-revelation-equivalent mechanisms. Agents bearing")
    print("front-loaded costs under uncertainty when proposing changes.")
    print("Intent becomes unobservable AND irrelevant.")
    print("")
    print("Pure attestation (grade F) = needs external authority.")
    print("Escrow + reputation (grade A) = self-enforcing.")
    print("TC4 PayLock (grade A) = exactly this pattern.")


if __name__ == "__main__":
    demo()
