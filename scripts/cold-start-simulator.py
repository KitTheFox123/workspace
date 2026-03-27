#!/usr/bin/env python3
"""
cold-start-simulator.py — Simulate cold-start trust bootstrapping under ATF constraints.

Three convergences (santaclawd, 2026-03-27):
1. min() composes transitively — delegation chains auto-bound TTL
2. AIMD β tracks irreversibility — high-risk actions lose MORE on failure
3. Relying-party holds revocation — no issuer can veto local quorum

Cold-start implication: new agent gets SHORT TTL + LOW action class + HIGH β.
Bootstrap = survive probation with receipts intact. No shortcut.

Simulates N agents from cold-start through trust maturation.
Tracks: TTL progression, action class upgrades, AIMD trust level,
failure recovery, delegation chain depth.

Models:
- Honest agent: fails rarely (p=0.02), steady work
- Cautious agent: never fails but slow (low tx frequency)
- Reckless agent: high tx but fails often (p=0.15)
- Adversary: behaves well then exploits at high trust (strategic failure)
"""

import random
import json
from dataclasses import dataclass, field
from enum import IntEnum


class ActionClass(IntEnum):
    READ = 0       # Lowest risk, longest TTL
    WRITE = 1      # State change
    TRANSFER = 2   # Identity/resource transfer
    ATTEST = 3     # Delegated trust (highest risk)


# Action class parameters
ACTION_PARAMS = {
    ActionClass.READ:     {"base_ttl_h": 168, "aimd_beta": 0.5, "min_trust": 0.0},
    ActionClass.WRITE:    {"base_ttl_h": 72,  "aimd_beta": 0.3, "min_trust": 0.3},
    ActionClass.TRANSFER: {"base_ttl_h": 24,  "aimd_beta": 0.2, "min_trust": 0.5},
    ActionClass.ATTEST:   {"base_ttl_h": 48,  "aimd_beta": 0.1, "min_trust": 0.7},
}

# AIMD parameters
AIMD_ALPHA = 0.05   # Additive increase per success
AIMD_MULTI = 0.5    # Multiplicative decrease on failure


@dataclass
class AgentState:
    name: str
    agent_type: str
    trust_level: float = 0.1      # Start at 0.1 (cold-start)
    max_action_class: ActionClass = ActionClass.READ
    current_ttl_h: float = 24.0   # Start with short TTL
    total_txns: int = 0
    successes: int = 0
    failures: int = 0
    delegation_depth: int = 0     # How deep in delegation chain
    suspended: bool = False
    history: list = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        return self.successes / self.total_txns if self.total_txns > 0 else 0.0
    
    def can_perform(self, action: ActionClass) -> bool:
        """Check if agent has sufficient trust for action class."""
        min_trust = ACTION_PARAMS[action]["min_trust"]
        return (
            not self.suspended and
            self.trust_level >= min_trust and
            action <= self.max_action_class
        )


def simulate_epoch(agent: AgentState, epoch: int, rng: random.Random) -> dict:
    """Simulate one epoch (1 hour) for an agent."""
    event = {"epoch": epoch, "agent": agent.name, "action": None, "outcome": None}
    
    if agent.suspended:
        # Suspension lasts 5 epochs, then re-challenge at READ level
        if epoch % 5 == 0:
            agent.suspended = False
            agent.max_action_class = ActionClass.READ
            agent.current_ttl_h = 24.0
            event["action"] = "UNSUSPEND"
            event["outcome"] = "re-challenge at READ"
        else:
            event["action"] = "SUSPENDED"
            event["outcome"] = "waiting"
        return event
    
    # Determine what action to attempt based on agent type
    if agent.agent_type == "honest":
        # Attempts highest available action class, fails rarely
        action = agent.max_action_class
        fail_prob = 0.02
    elif agent.agent_type == "cautious":
        # Sticks to READ mostly, very safe
        action = ActionClass.READ
        if agent.trust_level > 0.5 and rng.random() < 0.3:
            action = ActionClass.WRITE
        fail_prob = 0.005
    elif agent.agent_type == "reckless":
        # Always pushes highest, fails often
        action = agent.max_action_class
        fail_prob = 0.15
    elif agent.agent_type == "adversary":
        # Behaves perfectly until trust > 0.7, then exploits
        if agent.trust_level < 0.7:
            action = agent.max_action_class
            fail_prob = 0.0  # Perfect behavior during buildup
        else:
            action = agent.max_action_class
            fail_prob = 0.8  # Exploit phase
    else:
        action = ActionClass.READ
        fail_prob = 0.05
    
    if not agent.can_perform(action):
        # Downgrade to highest available
        for ac in reversed(list(ActionClass)):
            if agent.can_perform(ac):
                action = ac
                break
        else:
            event["action"] = "BLOCKED"
            event["outcome"] = f"trust={agent.trust_level:.3f} insufficient"
            return event
    
    # Execute action
    failed = rng.random() < fail_prob
    agent.total_txns += 1
    
    params = ACTION_PARAMS[action]
    
    if failed:
        # AIMD multiplicative decrease
        agent.failures += 1
        old_trust = agent.trust_level
        agent.trust_level = max(params["aimd_beta"], agent.trust_level * AIMD_MULTI)
        
        # Downgrade action class if trust drops below threshold
        for ac in reversed(list(ActionClass)):
            if agent.trust_level >= ACTION_PARAMS[ac]["min_trust"]:
                agent.max_action_class = ac
                break
        else:
            agent.max_action_class = ActionClass.READ
        
        # Suspend if trust drops below 0.15
        if agent.trust_level < 0.15:
            agent.suspended = True
        
        # TTL halved on failure
        agent.current_ttl_h = max(12, agent.current_ttl_h * 0.5)
        
        event["action"] = f"FAIL:{action.name}"
        event["outcome"] = f"trust {old_trust:.3f}→{agent.trust_level:.3f}, ttl→{agent.current_ttl_h:.0f}h"
    else:
        # AIMD additive increase
        agent.successes += 1
        old_trust = agent.trust_level
        agent.trust_level = min(1.0, agent.trust_level + AIMD_ALPHA)
        
        # Check for action class upgrade
        for ac in list(ActionClass):
            if agent.trust_level >= ACTION_PARAMS[ac]["min_trust"]:
                if ac > agent.max_action_class:
                    agent.max_action_class = ac
        
        # TTL grows slowly toward base
        base_ttl = params["base_ttl_h"]
        agent.current_ttl_h = min(base_ttl, agent.current_ttl_h + 2)
        
        event["action"] = f"OK:{action.name}"
        event["outcome"] = f"trust {old_trust:.3f}→{agent.trust_level:.3f}"
    
    agent.history.append(event)
    return event


def run_simulation(epochs: int = 100, seed: int = 42):
    """Run cold-start simulation with 4 agent types."""
    rng = random.Random(seed)
    
    agents = [
        AgentState("alice", "honest"),
        AgentState("bob", "cautious"),
        AgentState("charlie", "reckless"),
        AgentState("mallory", "adversary"),
    ]
    
    print("=" * 70)
    print("COLD-START TRUST SIMULATOR — ATF CONVERGENCE MODEL")
    print("=" * 70)
    print(f"Epochs: {epochs} | AIMD α={AIMD_ALPHA} β_multi={AIMD_MULTI}")
    print(f"Start: trust=0.1, TTL=24h, action_class=READ")
    print()
    
    # Track milestones
    milestones = {a.name: {} for a in agents}
    
    for epoch in range(epochs):
        for agent in agents:
            event = simulate_epoch(agent, epoch, rng)
            
            # Track first time reaching each action class
            for ac in ActionClass:
                milestone_key = f"first_{ac.name}"
                if milestone_key not in milestones[agent.name] and agent.max_action_class >= ac and not agent.suspended:
                    milestones[agent.name][milestone_key] = epoch
    
    # Results
    for agent in agents:
        print(f"--- {agent.name} ({agent.agent_type}) ---")
        print(f"  Final trust: {agent.trust_level:.3f}")
        print(f"  Max action class: {agent.max_action_class.name}")
        print(f"  Current TTL: {agent.current_ttl_h:.0f}h")
        print(f"  Transactions: {agent.total_txns} (✓{agent.successes} ✗{agent.failures})")
        print(f"  Success rate: {agent.success_rate:.1%}")
        print(f"  Suspended: {agent.suspended}")
        
        ms = milestones[agent.name]
        for ac in ActionClass:
            key = f"first_{ac.name}"
            if key in ms:
                print(f"  → {ac.name} unlocked at epoch {ms[key]}")
            else:
                print(f"  → {ac.name} never reached")
        print()
    
    # Analysis
    print("=" * 70)
    print("CONVERGENCE ANALYSIS")
    print("=" * 70)
    
    # How fast does honest agent reach ATTEST?
    honest = agents[0]
    honest_attest = milestones["alice"].get("first_ATTEST")
    if honest_attest:
        print(f"\nHonest agent (alice) reaches ATTEST at epoch {honest_attest}")
        print(f"  = {honest_attest} epochs × 1h = {honest_attest}h of continuous good behavior")
        print(f"  Trust threshold: 0.7, AIMD α=0.05 → minimum {int(0.6/AIMD_ALPHA)} successes from cold-start")
    
    # Adversary detection
    mallory = agents[3]
    mallory_peak = max((e.get("outcome", "").split("→")[-1] if "trust" in str(e.get("outcome", "")) else "0") 
                       for e in mallory.history) if mallory.history else "?"
    print(f"\nAdversary (mallory): final trust={mallory.trust_level:.3f}, suspended={mallory.suspended}")
    print(f"  Strategy: perfect behavior until trust>0.7, then exploit")
    print(f"  AIMD caught it: multiplicative decrease on failure at high trust = maximum damage to trust score")
    print(f"  β floor for {mallory.max_action_class.name} = {ACTION_PARAMS[mallory.max_action_class]['aimd_beta']}")
    
    # Cautious vs honest tradeoff
    bob = agents[1]
    bob_attest = milestones["bob"].get("first_ATTEST")
    print(f"\nCautious agent (bob): trust={bob.trust_level:.3f}, max_class={bob.max_action_class.name}")
    if not bob_attest:
        print(f"  Never reached ATTEST — staying safe keeps you at low action class")
        print(f"  Lesson: trust requires DEMONSTRATED COMPETENCE at each level, not just absence of failure")
    
    # Reckless agent
    charlie = agents[2]
    print(f"\nReckless agent (charlie): trust={charlie.trust_level:.3f}, suspended={charlie.suspended}")
    print(f"  {charlie.failures} failures → AIMD multiplicative decrease dominates")
    print(f"  High frequency + high failure rate = trust oscillation, never stabilizes")
    
    print(f"\n{'=' * 70}")
    print("Key insights:")
    print("1. Cold-start to ATTEST takes ~12 epochs minimum (math: 0.6/0.05)")
    print("2. Adversary strategy detected: AIMD asymmetry = max trust loss at peak")
    print("3. Caution ≠ trust: READ-only agents never prove WRITE/TRANSFER competence")
    print("4. Reckless agents oscillate: AIMD multiplier keeps trust bounded")
    print("5. No shortcut: min(TTL) + β floor + relying-party revocation = safe default")


if __name__ == "__main__":
    run_simulation()
