#!/usr/bin/env python3
"""
trust-spillover-sim.py — SIR epidemic model for trust propagation between agent networks.

Maps SIR interconnected network dynamics (Sahneh et al 2013, Applied Network
Science 2024) to ATF trust propagation. Trust spreads like epidemics: there's
a phase transition threshold below which trust cannot propagate across
communities, and above which it "spills over" from reservoir (established)
to host (new) networks.

Key finding from epidemic literature:
- Epidemic threshold in interconnected networks is LOWER than either
  component network alone (Wang & Xiao 2012)
- For weakly coupled networks, a MIXED PHASE exists where epidemic
  doesn't spread to the whole system (Dickison et al 2012)
- Phase transition for spillover depends on inter-network link density
  AND infection strength (Applied Network Science, Aug 2024)

ATF parallel:
- "Infection" = trust propagation. β = attestation acceptance rate.
- "Recovery" = trust decay (TTL expiry). δ = decay rate.
- Interconnected networks = agent communities (Clawk, Moltbook, agentmail)
- Spillover = when trust from one platform propagates to another
- The epidemic threshold IS the trust threshold — below it, trust
  stays local; above it, trust percolates globally.
- min() composition = immunity (caps infection strength per hop)

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    UNTRUSTED = "S"    # Susceptible — no trust yet
    TRUSTED = "I"      # Infected — actively trusted
    DECAYED = "R"      # Recovered — trust expired (TTL)


@dataclass
class Agent:
    id: str
    network: str       # Which community
    state: State = State.UNTRUSTED
    trust_score: float = 0.0
    trusted_at: int = -1   # Tick when trusted
    ttl: int = 20          # Ticks until decay


@dataclass
class TrustNetwork:
    name: str
    agents: list[Agent] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)  # Internal edges
    
    def add_agents(self, n: int, prefix: str = ""):
        for i in range(n):
            self.agents.append(Agent(
                id=f"{prefix}{i}",
                network=self.name
            ))
    
    def add_random_edges(self, density: float):
        """Erdos-Renyi random graph."""
        n = len(self.agents)
        for i in range(n):
            for j in range(i + 1, n):
                if random.random() < density:
                    self.edges.append((i, j))


def simulate_trust_spillover(
    net_a: TrustNetwork,
    net_b: TrustNetwork,
    inter_links: list[tuple[int, int]],  # (idx_in_a, idx_in_b)
    beta_intra: float = 0.15,   # Intra-network trust propagation rate
    beta_inter: float = 0.05,   # Cross-network trust propagation rate
    delta: float = 0.05,        # Trust decay rate (TTL expiry)
    seed_count: int = 3,        # Initial trusted agents in net_a
    ticks: int = 50,
    use_min_composition: bool = True  # ATF min() cap
) -> dict:
    """
    SIR trust propagation across two interconnected agent networks.
    
    Returns tick-by-tick state and spillover metrics.
    """
    all_agents_a = net_a.agents
    all_agents_b = net_b.agents
    
    # Seed initial trust in network A (reservoir)
    seeds = random.sample(range(len(all_agents_a)), min(seed_count, len(all_agents_a)))
    for idx in seeds:
        all_agents_a[idx].state = State.TRUSTED
        all_agents_a[idx].trust_score = 0.9
        all_agents_a[idx].trusted_at = 0
    
    history = []
    
    for t in range(1, ticks + 1):
        # Count states
        a_trusted = sum(1 for a in all_agents_a if a.state == State.TRUSTED)
        b_trusted = sum(1 for a in all_agents_b if a.state == State.TRUSTED)
        a_decayed = sum(1 for a in all_agents_a if a.state == State.DECAYED)
        b_decayed = sum(1 for a in all_agents_b if a.state == State.DECAYED)
        
        history.append({
            "tick": t,
            "a_trusted": a_trusted,
            "b_trusted": b_trusted,
            "a_decayed": a_decayed,
            "b_decayed": b_decayed,
        })
        
        # Trust propagation: intra-network A
        for (i, j) in net_a.edges:
            _try_propagate(all_agents_a[i], all_agents_a[j], beta_intra, t, use_min_composition)
            _try_propagate(all_agents_a[j], all_agents_a[i], beta_intra, t, use_min_composition)
        
        # Trust propagation: intra-network B
        for (i, j) in net_b.edges:
            _try_propagate(all_agents_b[i], all_agents_b[j], beta_intra, t, use_min_composition)
            _try_propagate(all_agents_b[j], all_agents_b[i], beta_intra, t, use_min_composition)
        
        # Trust propagation: inter-network (spillover channel)
        for (ia, ib) in inter_links:
            _try_propagate(all_agents_a[ia], all_agents_b[ib], beta_inter, t, use_min_composition)
            _try_propagate(all_agents_b[ib], all_agents_a[ia], beta_inter, t, use_min_composition)
        
        # Trust decay (TTL expiry)
        for agent in all_agents_a + all_agents_b:
            if agent.state == State.TRUSTED and agent.trusted_at >= 0:
                if t - agent.trusted_at > agent.ttl:
                    agent.state = State.DECAYED
                    if random.random() < delta:
                        agent.state = State.DECAYED
    
    # Spillover analysis
    b_ever_trusted = sum(1 for a in all_agents_b if a.state != State.UNTRUSTED)
    spillover_rate = b_ever_trusted / max(len(all_agents_b), 1)
    
    # Phase transition: did trust percolate to network B?
    peak_b = max(h["b_trusted"] for h in history) if history else 0
    spillover_occurred = peak_b > len(all_agents_b) * 0.1  # >10% = spillover
    
    return {
        "spillover_occurred": spillover_occurred,
        "spillover_rate": round(spillover_rate, 3),
        "peak_b_trusted": peak_b,
        "peak_b_fraction": round(peak_b / max(len(all_agents_b), 1), 3),
        "final_a_trusted": sum(1 for a in all_agents_a if a.state == State.TRUSTED),
        "final_b_trusted": sum(1 for a in all_agents_b if a.state == State.TRUSTED),
        "inter_link_count": len(inter_links),
        "beta_inter": beta_inter,
        "min_composition": use_min_composition,
        "history": history,
    }


def _try_propagate(source: Agent, target: Agent, beta: float, tick: int, use_min: bool):
    """Attempt trust propagation from source to target."""
    if source.state != State.TRUSTED or target.state != State.UNTRUSTED:
        return
    
    if random.random() < beta:
        target.state = State.TRUSTED
        target.trusted_at = tick
        if use_min:
            # ATF min() composition: target score ≤ source score
            target.trust_score = min(source.trust_score, 0.5 + random.random() * 0.4)
        else:
            # Multiplicative (PGP-style): scores multiply down
            target.trust_score = source.trust_score * (0.5 + random.random() * 0.4)


def find_phase_transition(n_a=50, n_b=50, density=0.15, seeds=5, trials=20):
    """
    Sweep inter-network link density to find the phase transition point
    where trust spills from network A to network B.
    """
    print("=" * 60)
    print("PHASE TRANSITION SWEEP: Trust Spillover")
    print(f"Net A: {n_a} agents, Net B: {n_b} agents, density={density}")
    print("=" * 60)
    
    inter_fractions = [0.0, 0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3]
    
    for frac in inter_fractions:
        spillover_counts = 0
        avg_peak = 0
        
        for _ in range(trials):
            net_a = TrustNetwork(name="established")
            net_a.add_agents(n_a, prefix="a")
            net_a.add_random_edges(density)
            
            net_b = TrustNetwork(name="newcomer")
            net_b.add_agents(n_b, prefix="b")
            net_b.add_random_edges(density)
            
            # Inter-network links
            n_inter = max(1, int(frac * n_a))
            inter_links = []
            for _ in range(n_inter):
                ia = random.randint(0, n_a - 1)
                ib = random.randint(0, n_b - 1)
                inter_links.append((ia, ib))
            
            result = simulate_trust_spillover(
                net_a, net_b, inter_links,
                beta_intra=0.15, beta_inter=0.08,
                seed_count=seeds, ticks=40
            )
            
            if result["spillover_occurred"]:
                spillover_counts += 1
            avg_peak += result["peak_b_fraction"]
        
        spillover_prob = spillover_counts / trials
        avg_peak /= trials
        
        bar = "█" * int(spillover_prob * 30)
        phase = "MAJOR" if spillover_prob > 0.5 else "MINOR" if spillover_prob > 0.1 else "NONE"
        print(f"  inter={frac:.2f} | P(spillover)={spillover_prob:.2f} | peak_B={avg_peak:.2f} | {bar} [{phase}]")
    
    print()
    print("Phase transition = boundary between MINOR and MAJOR spillover.")
    print("Below threshold: trust stays local (weak coupling).")
    print("Above threshold: trust percolates to new community.")
    print()


def compare_composition():
    """Compare min() (ATF) vs multiplicative (PGP) trust propagation."""
    print("=" * 60)
    print("COMPOSITION COMPARISON: min() vs multiplicative")
    print("=" * 60)
    
    random.seed(42)
    results = {}
    
    for use_min, label in [(True, "ATF (min)"), (False, "PGP (mult)")]:
        peaks = []
        scores = []
        for _ in range(30):
            net_a = TrustNetwork(name="established")
            net_a.add_agents(40, prefix="a")
            net_a.add_random_edges(0.15)
            
            net_b = TrustNetwork(name="newcomer")
            net_b.add_agents(40, prefix="b")
            net_b.add_random_edges(0.15)
            
            inter_links = [(random.randint(0, 39), random.randint(0, 39)) for _ in range(5)]
            
            result = simulate_trust_spillover(
                net_a, net_b, inter_links,
                beta_intra=0.15, beta_inter=0.08,
                seed_count=5, ticks=40,
                use_min_composition=use_min
            )
            
            peaks.append(result["peak_b_fraction"])
            final_scores = [a.trust_score for a in net_b.agents if a.state != State.UNTRUSTED]
            if final_scores:
                scores.append(sum(final_scores) / len(final_scores))
        
        avg_peak = sum(peaks) / len(peaks)
        avg_score = sum(scores) / len(scores) if scores else 0
        results[label] = {"avg_peak": avg_peak, "avg_score": avg_score}
        print(f"  {label}: avg peak penetration={avg_peak:.3f}, avg trust score={avg_score:.3f}")
    
    print()
    print("min() preserves higher scores through chains (bounded, not decaying).")
    print("Multiplicative = each hop multiplies down → deep chains = near-zero trust.")
    print()


def demo():
    random.seed(42)
    find_phase_transition()
    compare_composition()
    
    print("KEY INSIGHTS:")
    print("1. Trust propagation has a PHASE TRANSITION — below inter-network")
    print("   link threshold, trust stays local. Above it, trust percolates.")
    print("2. Epidemic threshold in interconnected networks is LOWER than")
    print("   either component alone (Wang & Xiao 2012). Same for trust.")
    print("3. min() composition (ATF) preserves trust scores through chains.")
    print("   Multiplicative (PGP) decays to zero in deep chains.")
    print("4. 'Weakly coupled' agent communities need explicit bridging agents")
    print("   to achieve trust spillover. agentmail = the inter-network link.")


if __name__ == "__main__":
    demo()
