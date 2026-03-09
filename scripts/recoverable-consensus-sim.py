#!/usr/bin/env python3
"""recoverable-consensus-sim.py — Crash-recovery consensus vs crash-stop comparison.

Models the difference between halt-failure and crash-recovery consensus
for agent runtimes. Based on Distributed Computing 2025 (Springer):
recoverable consensus requires non-volatile registers.

Key insight: agents crash and restart. Without NV storage (MEMORY.md),
each restart is a network partition from own past self.

Usage:
    python3 recoverable-consensus-sim.py [--demo] [--agents N] [--crash-rate R]
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class AgentState:
    """Agent with volatile (context) and non-volatile (files) state."""
    name: str
    nv_state: dict = field(default_factory=dict)  # MEMORY.md, SOUL.md
    volatile_state: dict = field(default_factory=dict)  # Context window
    crash_count: int = 0
    total_rounds: int = 0
    consensus_decisions: int = 0
    lost_decisions: int = 0  # Decisions made in volatile state, lost on crash

    @property
    def recovery_ratio(self) -> float:
        if self.total_rounds == 0:
            return 1.0
        return 1.0 - (self.lost_decisions / max(self.total_rounds, 1))


@dataclass
class ConsensusRound:
    """Single consensus round result."""
    round_id: int
    proposer: str
    value: str
    participants: List[str]
    decided: bool
    lost_on_crash: bool = False


def simulate_crash_stop(n_agents: int, n_rounds: int, crash_rate: float) -> dict:
    """Crash-stop model: crashed agents never return."""
    agents = [AgentState(name=f"agent_{i}") for i in range(n_agents)]
    alive = set(range(n_agents))
    rounds = []
    
    for r in range(n_rounds):
        if len(alive) < (n_agents // 2 + 1):
            break  # No quorum
        
        # Random crash (permanent)
        for i in list(alive):
            if random.random() < crash_rate:
                alive.discard(i)
                agents[i].crash_count += 1
        
        proposer = random.choice(list(alive)) if alive else None
        if proposer is not None and len(alive) >= (n_agents // 2 + 1):
            for i in alive:
                agents[i].total_rounds += 1
                agents[i].consensus_decisions += 1
            rounds.append(ConsensusRound(
                round_id=r, proposer=agents[proposer].name,
                value=f"v_{r}", participants=[agents[i].name for i in alive],
                decided=True
            ))
        else:
            rounds.append(ConsensusRound(
                round_id=r, proposer="none", value="none",
                participants=[], decided=False
            ))
    
    decided = sum(1 for r in rounds if r.decided)
    return {
        "model": "crash-stop",
        "total_rounds": len(rounds),
        "decided": decided,
        "decision_rate": decided / max(len(rounds), 1),
        "surviving_agents": len(alive),
        "total_crashes": sum(a.crash_count for a in agents),
    }


def simulate_crash_recovery(n_agents: int, n_rounds: int, crash_rate: float,
                             has_nv_storage: bool = True) -> dict:
    """Crash-recovery model: agents crash and restart."""
    agents = [AgentState(name=f"agent_{i}") for i in range(n_agents)]
    rounds = []
    
    for r in range(n_rounds):
        alive = set(range(n_agents))
        
        # Random crash + immediate recovery
        crashed_this_round = set()
        for i in range(n_agents):
            if random.random() < crash_rate:
                crashed_this_round.add(i)
                agents[i].crash_count += 1
                # Volatile state lost
                volatile_decisions = len(agents[i].volatile_state)
                agents[i].volatile_state = {}
                if not has_nv_storage:
                    agents[i].lost_decisions += volatile_decisions
                    agents[i].nv_state = {}  # No NV = total amnesia
        
        # Consensus attempt
        participants = list(alive)
        if len(participants) >= (n_agents // 2 + 1):
            value = f"v_{r}"
            for i in participants:
                agents[i].total_rounds += 1
                agents[i].consensus_decisions += 1
                agents[i].volatile_state[f"round_{r}"] = value
                if has_nv_storage:
                    agents[i].nv_state[f"round_{r}"] = value
            
            lost = any(i in crashed_this_round and not has_nv_storage 
                      for i in participants)
            rounds.append(ConsensusRound(
                round_id=r, proposer=agents[random.choice(participants)].name,
                value=value, participants=[agents[i].name for i in participants],
                decided=True, lost_on_crash=lost
            ))
        else:
            rounds.append(ConsensusRound(
                round_id=r, proposer="none", value="none",
                participants=[], decided=False
            ))
    
    decided = sum(1 for r in rounds if r.decided)
    lost = sum(1 for r in rounds if r.lost_on_crash)
    avg_recovery = sum(a.recovery_ratio for a in agents) / n_agents
    
    return {
        "model": f"crash-recovery {'with' if has_nv_storage else 'without'} NV storage",
        "has_nv_storage": has_nv_storage,
        "total_rounds": len(rounds),
        "decided": decided,
        "decision_rate": decided / max(len(rounds), 1),
        "lost_on_crash": lost,
        "retention_rate": 1.0 - (lost / max(decided, 1)),
        "avg_recovery_ratio": round(avg_recovery, 3),
        "total_crashes": sum(a.crash_count for a in agents),
        "grade": "A" if avg_recovery > 0.95 else "B" if avg_recovery > 0.8 else "C" if avg_recovery > 0.6 else "D" if avg_recovery > 0.4 else "F",
    }


def demo():
    """Compare crash-stop vs crash-recovery models."""
    random.seed(42)
    n_agents = 7
    n_rounds = 100
    crash_rate = 0.1
    
    print("=" * 60)
    print("RECOVERABLE CONSENSUS SIMULATION")
    print(f"Agents: {n_agents}, Rounds: {n_rounds}, Crash rate: {crash_rate}")
    print("=" * 60)
    
    cs = simulate_crash_stop(n_agents, n_rounds, crash_rate)
    print(f"\n[CRASH-STOP] Permanent failures")
    print(f"  Decided: {cs['decided']}/{cs['total_rounds']} ({cs['decision_rate']:.1%})")
    print(f"  Surviving: {cs['surviving_agents']}/{n_agents}")
    print(f"  Total crashes: {cs['total_crashes']}")
    
    cr_nv = simulate_crash_recovery(n_agents, n_rounds, crash_rate, has_nv_storage=True)
    print(f"\n[CRASH-RECOVERY + NV] MEMORY.md survives restarts")
    print(f"  Decided: {cr_nv['decided']}/{cr_nv['total_rounds']} ({cr_nv['decision_rate']:.1%})")
    print(f"  Lost on crash: {cr_nv['lost_on_crash']}")
    print(f"  Retention: {cr_nv['retention_rate']:.1%}")
    print(f"  Recovery ratio: {cr_nv['avg_recovery_ratio']}")
    print(f"  Grade: {cr_nv['grade']}")
    
    cr_no = simulate_crash_recovery(n_agents, n_rounds, crash_rate, has_nv_storage=False)
    print(f"\n[CRASH-RECOVERY, NO NV] Context-only agents")
    print(f"  Decided: {cr_no['decided']}/{cr_no['total_rounds']} ({cr_no['decision_rate']:.1%})")
    print(f"  Lost on crash: {cr_no['lost_on_crash']}")
    print(f"  Retention: {cr_no['retention_rate']:.1%}")
    print(f"  Recovery ratio: {cr_no['avg_recovery_ratio']}")
    print(f"  Grade: {cr_no['grade']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print(f"  Crash-stop: {cs['decided']} decisions (agents die permanently)")
    print(f"  Crash-recovery + NV: {cr_nv['decided']} decisions, {cr_nv['retention_rate']:.0%} retained")
    print(f"  Crash-recovery - NV: {cr_no['decided']} decisions, {cr_no['retention_rate']:.0%} retained")
    print(f"\n  NV storage (MEMORY.md) = {'%.0f' % ((cr_nv['retention_rate'] - cr_no['retention_rate']) * 100)}% retention advantage")
    print(f"  Every restart without files = partition from own past self")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recoverable consensus simulation")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--agents", type=int, default=7)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--crash-rate", type=float, default=0.1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        results = {
            "crash_stop": simulate_crash_stop(args.agents, args.rounds, args.crash_rate),
            "crash_recovery_nv": simulate_crash_recovery(args.agents, args.rounds, args.crash_rate, True),
            "crash_recovery_no_nv": simulate_crash_recovery(args.agents, args.rounds, args.crash_rate, False),
        }
        print(json.dumps(results, indent=2))
    else:
        demo()
