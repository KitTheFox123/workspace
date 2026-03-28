#!/usr/bin/env python3
"""
trust-epidemic-threshold.py — Epidemic threshold for malicious trust propagation.

Maps Gross et al (Sci Rep, 2015) heterogeneous adaptive SIS model to ATF.
Key insight: bad trust propagation through attestation networks follows
epidemic dynamics. Heterogeneity in agent susceptibility (how easily they
accept attestations without verification) creates natural resilience.

The epidemic threshold = minimum "infectivity" (persuasiveness of fraudulent
attestations) needed for bad trust to spread. Below threshold, isolated
incidents. Above threshold, systemic compromise.

ATF mappings:
- Infected (I) = agents with compromised trust scores (accepting bad attestations)
- Susceptible (S) = agents that could be misled
- Recovery (μ) = rate agents detect and reject bad attestations (SOFT_CASCADE)
- Rewiring (ω) = agents severing links to compromised attesters
- Infectivity (β) = persuasiveness of fraudulent attestation
- Type heterogeneity = agents have different verification thresholds

Key result from Gross et al: heterogeneous susceptibility + adaptive rewiring
creates HIGHER epidemic thresholds than homogeneous networks. This means
diverse verification standards are BETTER than uniform ones — because agents
that easily reject fraud act as natural firewalls.

Sources:
- Gross et al (Sci Rep 2015): Large epidemic thresholds in heterogeneous
  networks of heterogeneous nodes. doi:10.1038/srep13122
- Pastor-Satorras & Vespignani (PRL 2001): Scale-free networks have
  vanishing epidemic thresholds — but adaptive rewiring restores them.

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass


@dataclass
class Agent:
    id: str
    susceptibility: float  # How easily accepts unverified attestations [0,1]
    infected: bool = False  # Currently propagating bad trust
    recovery_rate: float = 0.1  # Rate of detecting/rejecting bad trust
    neighbors: list = None
    
    def __post_init__(self):
        if self.neighbors is None:
            self.neighbors = []


def build_network(n: int, avg_degree: int, type_a_frac: float = 0.5,
                  suscept_a: float = 0.8, suscept_b: float = 0.2) -> list[Agent]:
    """
    Build Erdos-Renyi-like network with two types of agents.
    Type A: high susceptibility (accepts attestations easily)
    Type B: low susceptibility (verifies thoroughly)
    """
    agents = []
    for i in range(n):
        if random.random() < type_a_frac:
            s = suscept_a + random.gauss(0, 0.05)
        else:
            s = suscept_b + random.gauss(0, 0.05)
        s = max(0.01, min(1.0, s))
        agents.append(Agent(id=f"agent_{i}", susceptibility=s))
    
    # Random edges
    k = avg_degree * n // 2
    for _ in range(k):
        a, b = random.sample(range(n), 2)
        if b not in [x for x in agents[a].neighbors]:
            agents[a].neighbors.append(b)
            agents[b].neighbors.append(a)
    
    return agents


def simulate_sis(agents: list[Agent], beta: float, omega: float = 0.05,
                 steps: int = 200, initial_infected: float = 0.01) -> dict:
    """
    Adaptive SIS simulation.
    beta = base infectivity of bad attestations
    omega = rewiring rate (agents dropping compromised neighbors)
    """
    n = len(agents)
    
    # Reset
    for a in agents:
        a.infected = False
    
    # Seed infection
    seeds = random.sample(range(n), max(1, int(n * initial_infected)))
    for i in seeds:
        agents[i].infected = True
    
    history = []
    
    for step in range(steps):
        infected_count = sum(1 for a in agents if a.infected)
        history.append(infected_count / n)
        
        # Recovery: infected agents detect bad trust
        for a in agents:
            if a.infected and random.random() < a.recovery_rate:
                a.infected = False
        
        # Contagion: infected neighbors spread bad trust
        new_infections = []
        for i, a in enumerate(agents):
            if a.infected:
                continue
            for j in a.neighbors:
                if agents[j].infected:
                    # Transmission probability = beta * susceptibility
                    if random.random() < beta * a.susceptibility:
                        new_infections.append(i)
                        break
        
        for i in new_infections:
            agents[i].infected = True
        
        # Adaptive rewiring: susceptible agents drop infected neighbors
        for i, a in enumerate(agents):
            if a.infected:
                continue
            for j in list(a.neighbors):
                if agents[j].infected and random.random() < omega:
                    # Rewire: drop infected, connect to random susceptible
                    a.neighbors.remove(j)
                    agents[j].neighbors.remove(i)
                    candidates = [k for k in range(n) 
                                  if k != i and not agents[k].infected 
                                  and k not in a.neighbors]
                    if candidates:
                        new_neighbor = random.choice(candidates)
                        a.neighbors.append(new_neighbor)
                        agents[new_neighbor].neighbors.append(i)
    
    final_prevalence = sum(1 for a in agents if a.infected) / n
    peak_prevalence = max(history) if history else 0
    
    return {
        "beta": beta,
        "omega": omega,
        "final_prevalence": round(final_prevalence, 4),
        "peak_prevalence": round(peak_prevalence, 4),
        "epidemic": final_prevalence > 0.05
    }


def find_threshold(agents_factory, omega: float = 0.05, 
                   beta_range=(0.01, 0.5), resolution: int = 15) -> dict:
    """Binary-ish search for epidemic threshold."""
    results = []
    betas = [beta_range[0] + i * (beta_range[1] - beta_range[0]) / resolution 
             for i in range(resolution + 1)]
    
    for beta in betas:
        agents = agents_factory()
        r = simulate_sis(agents, beta=beta, omega=omega)
        results.append(r)
    
    # Find threshold: first beta where epidemic persists
    threshold = None
    for r in results:
        if r["epidemic"]:
            threshold = r["beta"]
            break
    
    return {
        "threshold": threshold,
        "results": results
    }


def demo():
    random.seed(42)
    n = 500
    avg_degree = 8
    
    print("=" * 60)
    print("TRUST EPIDEMIC THRESHOLD SIMULATION")
    print("=" * 60)
    print(f"Agents: {n}, Avg degree: {avg_degree}")
    print(f"Based on Gross et al (Sci Rep 2015)")
    print()
    
    # Scenario 1: Homogeneous susceptibility (all agents same)
    print("SCENARIO 1: Homogeneous agents (all susceptibility = 0.5)")
    print("-" * 40)
    homo_factory = lambda: build_network(n, avg_degree, type_a_frac=1.0, 
                                          suscept_a=0.5, suscept_b=0.5)
    homo = find_threshold(homo_factory)
    print(f"Epidemic threshold β*: {homo['threshold']}")
    for r in homo["results"]:
        bar = "█" * int(r["final_prevalence"] * 50)
        print(f"  β={r['beta']:.3f}: {r['final_prevalence']:.3f} {bar}")
    print()
    
    # Scenario 2: Heterogeneous susceptibility (mixed verification standards)
    print("SCENARIO 2: Heterogeneous agents (A=0.8, B=0.2, 50/50 split)")
    print("-" * 40)
    hetero_factory = lambda: build_network(n, avg_degree, type_a_frac=0.5,
                                            suscept_a=0.8, suscept_b=0.2)
    hetero = find_threshold(hetero_factory)
    print(f"Epidemic threshold β*: {hetero['threshold']}")
    for r in hetero["results"]:
        bar = "█" * int(r["final_prevalence"] * 50)
        print(f"  β={r['beta']:.3f}: {r['final_prevalence']:.3f} {bar}")
    print()
    
    # Scenario 3: High rewiring (aggressive SOFT_CASCADE)
    print("SCENARIO 3: High rewiring ω=0.2 (aggressive SOFT_CASCADE)")
    print("-" * 40)
    high_rewire = find_threshold(hetero_factory, omega=0.2)
    print(f"Epidemic threshold β*: {high_rewire['threshold']}")
    for r in high_rewire["results"]:
        bar = "█" * int(r["final_prevalence"] * 50)
        print(f"  β={r['beta']:.3f}: {r['final_prevalence']:.3f} {bar}")
    print()
    
    print("=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    print(f"Homogeneous threshold:  β* = {homo['threshold']}")
    print(f"Heterogeneous threshold: β* = {hetero['threshold']}")
    print(f"Hetero + high rewire:   β* = {high_rewire['threshold']}")
    print()
    
    if hetero["threshold"] and homo["threshold"]:
        improvement = (hetero["threshold"] - homo["threshold"]) / homo["threshold"] * 100
        print(f"Heterogeneity effect: {improvement:+.0f}% threshold change")
    
    if high_rewire["threshold"] and hetero["threshold"]:
        rewire_effect = (high_rewire["threshold"] - hetero["threshold"]) / hetero["threshold"] * 100
        print(f"SOFT_CASCADE effect: {rewire_effect:+.0f}% threshold change")
    
    print()
    print("KEY INSIGHT (Gross et al 2015):")
    print("Diverse verification standards = higher epidemic threshold.")
    print("Agents with LOW susceptibility act as natural firewalls.")
    print("Adaptive rewiring (SOFT_CASCADE) further raises the barrier.")
    print("Uniform trust policies are WORSE than heterogeneous ones.")
    print()
    print("ATF implication: Don't standardize verification thresholds.")
    print("Let paranoid agents be paranoid. They protect the network.")


if __name__ == "__main__":
    demo()
