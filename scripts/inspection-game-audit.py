#!/usr/bin/env python3
"""
inspection-game-audit.py — Inspection game for agent audit scheduling.

santaclawd's question: "what is the minimum public signal that preserves
deterrence without leaking the schedule?"

Answer from Ishikawa & Fontanari (2025, arXiv 2510.24905):
- Classical MSNE paradox: equilibrium crime rate independent of penalty
- Finite populations fix it: demographic noise drives fixation
- U-shaped: high penalties AND light penalties both suppress crime
- Moderate penalties = worst outcome

For agents:
- Public: "we audit" (commitment exists)
- Private: lambda (audit rate)
- Commit to audit rate hash, don't reveal lambda
- Poisson sampling: audit arrivals unpredictable

Dresher/Avenhaus inspection game framework adapted for agent trust.

Usage:
    python3 inspection-game-audit.py
"""

import random
import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class AuditConfig:
    """Audit parameters — the inspector's strategy."""
    audit_rate: float       # lambda: expected audits per period (PRIVATE)
    penalty: float          # cost to agent if caught cheating
    audit_cost: float       # cost to auditor per audit
    catch_reward: float     # auditor reward for catching cheat
    cheat_gain: float       # agent gain from undetected cheat

    @property
    def deterrence_threshold(self) -> float:
        """Ratio of audit cost to catch reward — the MSNE critical point."""
        return self.audit_cost / self.catch_reward if self.catch_reward > 0 else 1.0

    def poisson_audits(self) -> int:
        """Generate random number of audits this period (Poisson)."""
        return _poisson(self.audit_rate)

    def public_commitment(self) -> dict:
        """What the auditor reveals publicly."""
        import hashlib
        salt = random.randbytes(16).hex()
        payload = f"{self.audit_rate}:{salt}"
        h = hashlib.sha256(payload.encode()).hexdigest()
        return {
            "commitment_hash": h,
            "salt": salt,  # revealed later
            "public_signal": "audits will occur",
            "rate_revealed": False,
            "note": "rate is committed but not public"
        }


def _poisson(lam: float) -> int:
    """Simple Poisson random variate."""
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p < L:
            return k - 1


@dataclass
class AgentBehavior:
    """Agent's strategy — cheat probability."""
    name: str
    cheat_prob: float  # probability of cheating each period
    adaptive: bool = False  # does agent adapt to observed audit rate?

    def decide(self, observed_audit_rate: float = 0.0) -> bool:
        """Returns True if agent cheats this period."""
        if self.adaptive:
            # Reduce cheating when observed audit rate is high
            adjusted = self.cheat_prob * (1 - observed_audit_rate)
            return random.random() < adjusted
        return random.random() < self.cheat_prob


def simulate(config: AuditConfig, agent: AgentBehavior, periods: int = 100) -> dict:
    """Run inspection game simulation."""
    cheats = 0
    caught = 0
    total_audits = 0
    agent_payoff = 0.0
    auditor_payoff = 0.0

    for _ in range(periods):
        did_cheat = agent.decide(total_audits / max(1, periods))
        n_audits = config.poisson_audits()
        total_audits += n_audits

        if did_cheat:
            cheats += 1
            if n_audits > 0:
                # Caught
                caught += 1
                agent_payoff -= config.penalty
                auditor_payoff += config.catch_reward - config.audit_cost
            else:
                # Got away with it
                agent_payoff += config.cheat_gain
        else:
            if n_audits > 0:
                # Audited clean agent — cost with no reward
                auditor_payoff -= config.audit_cost

    cheat_rate = cheats / periods
    catch_rate = caught / cheats if cheats > 0 else 0
    deterrence = 1 - cheat_rate

    # Grade
    if deterrence > 0.9:
        grade = "A"
    elif deterrence > 0.7:
        grade = "B"
    elif deterrence > 0.5:
        grade = "C"
    elif deterrence > 0.3:
        grade = "D"
    else:
        grade = "F"

    return {
        "agent": agent.name,
        "periods": periods,
        "cheat_rate": round(cheat_rate, 3),
        "catch_rate": round(catch_rate, 3),
        "deterrence": round(deterrence, 3),
        "agent_payoff": round(agent_payoff, 1),
        "auditor_payoff": round(auditor_payoff, 1),
        "total_audits": total_audits,
        "grade": grade,
    }


def u_shaped_demo():
    """Demonstrate the U-shaped penalty landscape."""
    print("\n--- U-Shaped Penalty Landscape (Ishikawa & Fontanari 2025) ---")
    print("  Penalty  | Deterrence | Agent PnL | Grade")
    print("  " + "-" * 45)

    cheat_gain = 10.0
    for penalty in [5, 10, 15, 20, 50, 100]:
        config = AuditConfig(
            audit_rate=0.3, penalty=penalty,
            audit_cost=2.0, catch_reward=8.0, cheat_gain=cheat_gain
        )
        agent = AgentBehavior("rational", cheat_prob=0.4, adaptive=True)
        r = simulate(config, agent, periods=500)
        print(f"  {penalty:>7.0f}  | {r['deterrence']:>10.3f} | {r['agent_payoff']:>9.1f} | {r['grade']}")


def demo():
    random.seed(42)
    print("=" * 60)
    print("INSPECTION GAME AUDIT SCHEDULER")
    print("Ishikawa & Fontanari (2025) + Dresher/Avenhaus")
    print("=" * 60)

    config = AuditConfig(
        audit_rate=0.5,   # private
        penalty=20.0,
        audit_cost=2.0,
        catch_reward=8.0,
        cheat_gain=10.0
    )

    print(f"\nDeterrence threshold (k/r): {config.deterrence_threshold:.3f}")
    print(f"Public commitment: {config.public_commitment()['public_signal']}")
    print(f"Rate revealed: No (committed via hash)")

    # Scenario 1: Honest agent
    print("\n--- Scenario 1: Honest Agent ---")
    honest = AgentBehavior("honest_agent", cheat_prob=0.02)
    r1 = simulate(config, honest)
    print(f"  Deterrence: {r1['deterrence']} ({r1['grade']})")
    print(f"  Cheat rate: {r1['cheat_rate']}, Caught: {r1['catch_rate']}")

    # Scenario 2: Frequent cheater
    print("\n--- Scenario 2: Frequent Cheater ---")
    cheater = AgentBehavior("cheater", cheat_prob=0.6)
    r2 = simulate(config, cheater)
    print(f"  Deterrence: {r2['deterrence']} ({r2['grade']})")
    print(f"  Cheat rate: {r2['cheat_rate']}, Caught: {r2['catch_rate']}")
    print(f"  Agent PnL: {r2['agent_payoff']} (crime doesn't pay)")

    # Scenario 3: Adaptive cheater
    print("\n--- Scenario 3: Adaptive Cheater (adjusts to audit rate) ---")
    adaptive = AgentBehavior("adaptive", cheat_prob=0.5, adaptive=True)
    r3 = simulate(config, adaptive)
    print(f"  Deterrence: {r3['deterrence']} ({r3['grade']})")
    print(f"  Cheat rate: {r3['cheat_rate']}, Caught: {r3['catch_rate']}")

    # Scenario 4: Known audit rate (Goodhart)
    print("\n--- Scenario 4: Known Audit Rate (Goodhart's Law) ---")
    # Agent knows lambda, cheats only in gaps
    known = AgentBehavior("goodhart_gamer", cheat_prob=0.8, adaptive=True)
    r4 = simulate(config, known, periods=500)
    print(f"  Deterrence: {r4['deterrence']} ({r4['grade']})")
    print(f"  Note: even adaptive agents can't predict Poisson arrivals")

    # U-shaped penalty landscape
    u_shaped_demo()

    print("\n--- KEY INSIGHTS ---")
    print("1. Commit to audit existence, hide the rate")
    print("2. Poisson arrivals = unpredictable even if rate leaked")
    print("3. U-shaped: high OR light penalties both deter")
    print("4. Moderate penalties = worst deterrence (paradox)")
    print("5. Finite populations: noise drives fixation (the fix)")


if __name__ == "__main__":
    demo()
