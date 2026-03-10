#!/usr/bin/env python3
"""
survivorship-bias-detector.py — Wald 1943 for agent trust graphs

Abraham Wald, SRG 1943: armor where the bullet holes AREN'T.
Planes that came back had holes in non-critical areas.
Planes hit in critical areas didn't come back.

Agent trust graphs have the same bias:
- Only successful attestations propagate
- Failed/null observations are invisible
- Trust scores become highlight reels

Fix: make NACKs first-class. Count the missing.
A trust graph without negative evidence has survivorship bias.
"""

import random
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class TrustGraph:
    """Trust graph with optional NACK support"""
    acks: dict = field(default_factory=lambda: defaultdict(int))   # agent → positive attestation count
    nacks: dict = field(default_factory=lambda: defaultdict(int))  # agent → negative attestation count
    silences: dict = field(default_factory=lambda: defaultdict(int))  # agent → silence count
    nack_enabled: bool = True
    
    def attest_positive(self, agent: str):
        self.acks[agent] += 1
    
    def attest_negative(self, agent: str):
        if self.nack_enabled:
            self.nacks[agent] += 1
        # Without NACK, negative observations are LOST
    
    def record_silence(self, agent: str):
        self.silences[agent] += 1
    
    def trust_score(self, agent: str) -> float:
        """Naive: acks / total. Survivorship-biased without NACKs."""
        total = self.acks[agent] + self.nacks[agent]
        if total == 0:
            return 0.5  # no evidence
        return self.acks[agent] / total
    
    def trust_score_corrected(self, agent: str) -> float:
        """Wald-corrected: accounts for silence as potential negative."""
        acks = self.acks[agent]
        nacks = self.nacks[agent]
        silences = self.silences[agent]
        # Silence is partially negative (can't be fully positive)
        estimated_negative = nacks + (silences * 0.5)  # conservative: half of silences are failures
        total = acks + estimated_negative
        if total == 0:
            return 0.5
        return acks / total
    
    def survivorship_bias(self, agent: str) -> float:
        """How much is the trust score inflated by missing negative evidence?"""
        naive = self.trust_score(agent)
        corrected = self.trust_score_corrected(agent)
        return round(naive - corrected, 3)
    
    def bias_grade(self, agent: str) -> str:
        bias = self.survivorship_bias(agent)
        if bias < 0.05: return "A"  # minimal bias
        if bias < 0.10: return "B"
        if bias < 0.20: return "C"
        if bias < 0.35: return "D"
        return "F"  # heavily biased


def simulate(n_agents=5, n_rounds=50, true_reliability=0.7, nack_rate=0.8, seed=42):
    """Simulate trust graph with and without NACK support"""
    random.seed(seed)
    
    graph_with_nack = TrustGraph(nack_enabled=True)
    graph_without_nack = TrustGraph(nack_enabled=False)
    
    agents = [f"agent_{i}" for i in range(n_agents)]
    
    for _ in range(n_rounds):
        for agent in agents:
            outcome = random.random() < true_reliability
            if outcome:
                graph_with_nack.attest_positive(agent)
                graph_without_nack.attest_positive(agent)
            else:
                # Agent failed — some report NACK, some go silent
                if random.random() < nack_rate:
                    graph_with_nack.attest_negative(agent)
                    graph_without_nack.attest_negative(agent)
                else:
                    # Silent failure — only counted if system tracks silence
                    graph_with_nack.record_silence(agent)
                    graph_without_nack.record_silence(agent)
    
    return agents, graph_with_nack, graph_without_nack


def main():
    print("=" * 60)
    print("Survivorship Bias Detector")
    print("Wald 1943: armor where the holes AREN'T")
    print("=" * 60)
    
    agents, g_nack, g_no_nack = simulate()
    
    print(f"\nTrue reliability: 0.70")
    print(f"Simulation: 50 rounds × 5 agents")
    print(f"\n{'Agent':<12} {'Naive':>8} {'Corrected':>10} {'Bias':>8} {'Grade':>6}")
    print("-" * 48)
    
    total_bias = 0
    for agent in agents:
        naive = g_nack.trust_score(agent)
        corrected = g_nack.trust_score_corrected(agent)
        bias = g_nack.survivorship_bias(agent)
        grade = g_nack.bias_grade(agent)
        total_bias += bias
        print(f"{agent:<12} {naive:>8.3f} {corrected:>10.3f} {bias:>+8.3f} {grade:>6}")
    
    avg_bias = total_bias / len(agents)
    print(f"\nAvg survivorship bias: {avg_bias:+.3f}")
    
    print(f"\n--- Without NACK support ---")
    print(f"{'Agent':<12} {'Score':>8} {'vs True':>8}")
    print("-" * 30)
    for agent in agents:
        score = g_no_nack.trust_score(agent)
        delta = score - 0.70
        print(f"{agent:<12} {score:>8.3f} {delta:>+8.3f}")
    
    print(f"\n{'='*60}")
    print("Without NACKs: trust scores inflated (survivorship bias).")
    print("With NACKs + silence tracking: scores closer to truth.")
    print("Wald's lesson: count the planes that DIDN'T come back.")
    print("Agent lesson: count the attestations that DIDN'T happen.")


if __name__ == "__main__":
    main()
