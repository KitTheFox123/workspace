#!/usr/bin/env python3
"""
cascade-coupling-sim.py — Smart vs naive coupling in attestation networks.

Key insight from Hines et al (Scientific Reports, 2017): interdependent
networks aren't automatically more fragile. "Smart" coupling (complementary
capabilities with constrained failure propagation) INCREASES resilience.
Naive coupling (percolation-style, failures propagate freely) DECREASES it.

Three coupling models (mapping infrastructure to ATF):
1. NAIVE — Attester failure cascades freely (revoked attestation = all
   downstream trust collapses immediately). Percolation-style.
2. SMART — Attester failure triggers re-evaluation, not automatic cascade.
   Communication channel (email/DKIM) enables graceful degradation.
3. ISOLATED — No coupling. Each attestation independent. Most robust to
   individual failure but no shared intelligence during cascades.

The paper's key finding: "robustness can be enhanced by interconnecting
networks with complementary capabilities IF modes of internetwork failure
propagation are constrained."

ATF translation: attestation chains should propagate trust (smart coupling)
but constrain failure propagation (TTL bounds, SOFT_CASCADE, circuit breakers).

Sources:
- Hines et al (Sci Rep, 2017): "Reducing Cascading Failure Risk by
  Increasing Infrastructure Network Interdependence" — Nature/Sci Reports
- Buldyrev et al (Nature, 2010): Catastrophic cascade of failures in
  interdependent networks (the naive percolation model)

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from enum import Enum


class CouplingMode(Enum):
    NAIVE = "naive"       # Failure propagates freely (percolation)
    SMART = "smart"       # Failure triggers re-evaluation (constrained)
    ISOLATED = "isolated"  # No coupling


@dataclass
class Agent:
    id: str
    alive: bool = True
    trust_score: float = 0.8
    attestations_given: list = field(default_factory=list)  # agent_ids
    attestations_received: list = field(default_factory=list)
    has_backup: bool = False  # "battery backup" = independent evidence


@dataclass
class CascadeResult:
    mode: CouplingMode
    initial_failures: int
    final_failures: int
    cascade_multiplier: float
    surviving_agents: int
    total_agents: int
    rounds: int


def build_network(n: int, avg_connections: int = 3, seed: int = 42) -> list[Agent]:
    """Build a random attestation network."""
    random.seed(seed)
    agents = [Agent(id=f"agent_{i}") for i in range(n)]
    
    for agent in agents:
        # Random attestations
        others = [a for a in agents if a.id != agent.id]
        k = min(random.randint(1, avg_connections * 2), len(others))
        targets = random.sample(others, k)
        for target in targets:
            agent.attestations_given.append(target.id)
            target.attestations_received.append(agent.id)
        
        # 30% have independent evidence (backup power = DKIM chain)
        agent.has_backup = random.random() < 0.3
    
    return agents


def simulate_cascade(agents: list[Agent], initial_failures: list[str],
                     mode: CouplingMode) -> CascadeResult:
    """Simulate cascading failure under different coupling modes."""
    # Reset
    for a in agents:
        a.alive = True
        a.trust_score = 0.8
    
    agent_map = {a.id: a for a in agents}
    failed = set()
    
    # Initial failures
    for fid in initial_failures:
        if fid in agent_map:
            agent_map[fid].alive = False
            failed.add(fid)
    
    rounds = 0
    max_rounds = 20
    
    while rounds < max_rounds:
        new_failures = set()
        rounds += 1
        
        for agent in agents:
            if not agent.alive or agent.id in failed:
                continue
            
            # Count failed attesters
            failed_attesters = sum(1 for a_id in agent.attestations_received 
                                  if a_id in failed)
            total_attesters = len(agent.attestations_received)
            
            if total_attesters == 0:
                continue
            
            failure_fraction = failed_attesters / total_attesters
            
            if mode == CouplingMode.NAIVE:
                # Percolation: if ANY attester fails, agent loses that trust.
                # If majority fail, agent collapses (Buldyrev 2010 model).
                if failure_fraction > 0.5:
                    new_failures.add(agent.id)
                elif failure_fraction > 0:
                    agent.trust_score *= (1 - failure_fraction)
                    if agent.trust_score < 0.2:
                        new_failures.add(agent.id)
            
            elif mode == CouplingMode.SMART:
                # Smart coupling: failure triggers re-evaluation, not cascade.
                # Agents with backup (DKIM chain) survive attester loss.
                # Circuit breaker: degrade gracefully.
                if agent.has_backup:
                    # Independent evidence survives — just reduce score
                    agent.trust_score *= (1 - failure_fraction * 0.3)
                else:
                    # No backup: more vulnerable but still constrained
                    agent.trust_score *= (1 - failure_fraction * 0.6)
                    if agent.trust_score < 0.1:
                        new_failures.add(agent.id)
            
            elif mode == CouplingMode.ISOLATED:
                # No coupling: attester failure doesn't propagate at all.
                # Most robust to cascade but no shared intelligence.
                pass
        
        for fid in new_failures:
            agent_map[fid].alive = False
            failed.add(fid)
        
        if not new_failures:
            break
    
    surviving = sum(1 for a in agents if a.alive)
    return CascadeResult(
        mode=mode,
        initial_failures=len(initial_failures),
        final_failures=len(failed),
        cascade_multiplier=len(failed) / max(len(initial_failures), 1),
        surviving_agents=surviving,
        total_agents=len(agents),
        rounds=rounds
    )


def demo():
    random.seed(42)
    N = 100
    
    print("=" * 60)
    print("CASCADE COUPLING SIMULATION")
    print(f"N={N} agents, avg 3 attestation connections")
    print("Based on Hines et al (Sci Rep 2017)")
    print("=" * 60)
    
    # Test with increasing failure sizes
    failure_sizes = [3, 5, 10, 15, 20]
    
    for mode in CouplingMode:
        print(f"\n--- {mode.value.upper()} COUPLING ---")
        for fs in failure_sizes:
            agents = build_network(N)
            # Pick random initial failures
            initial = random.sample([a.id for a in agents], fs)
            result = simulate_cascade(agents, initial, mode)
            print(f"  Initial: {result.initial_failures:2d} → "
                  f"Final: {result.final_failures:3d} "
                  f"(×{result.cascade_multiplier:.1f}) "
                  f"Surviving: {result.surviving_agents:3d}/{result.total_agents} "
                  f"Rounds: {result.rounds}")
    
    print("\n" + "=" * 60)
    print("COMPARISON AT 10 INITIAL FAILURES")
    print("=" * 60)
    
    results = {}
    for mode in CouplingMode:
        agents = build_network(N)
        initial = random.sample([a.id for a in agents], 10)
        r = simulate_cascade(agents, initial, mode)
        results[mode.value] = r
        print(f"  {mode.value:10s}: {r.final_failures:3d} failures "
              f"(×{r.cascade_multiplier:.1f}), "
              f"{r.surviving_agents} surviving")
    
    # Verify smart < naive in cascade damage
    print("\n" + "=" * 60)
    print("KEY INSIGHT (Hines et al 2017)")
    print("=" * 60)
    print("Naive coupling: failures cascade freely → worst outcome")
    print("Smart coupling: constrained propagation → better than naive")
    print("Isolated: no cascade but no shared intelligence")
    print()
    print("ATF translation:")
    print("  NAIVE = revoked attestation kills all downstream (bad)")
    print("  SMART = SOFT_CASCADE + TTL bounds + circuit breakers (good)")
    print("  ISOLATED = no attestation chains at all (safe but useless)")
    print()
    print("'Robustness can be enhanced by interconnecting networks")
    print(" with complementary capabilities IF modes of failure")
    print(" propagation are constrained.' — Hines et al")
    
    # Assertions
    assert results["naive"].final_failures >= results["smart"].final_failures, \
        "Smart should have fewer cascading failures than naive"
    assert results["isolated"].final_failures <= results["smart"].final_failures, \
        "Isolated should have fewest cascading failures"
    print("\nASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
