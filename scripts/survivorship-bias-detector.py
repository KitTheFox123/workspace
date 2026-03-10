#!/usr/bin/env python3
"""
survivorship-bias-detector.py — Wald's missing bullet holes for agent trust

Gendolf insight: "Without NACK, you get survivorship bias in trust scores."

Wald 1943: armor the plane where surviving planes DON'T have holes —
the missing planes were hit there.

Agent trust: where are the MISSING attestations? Failed checks unreported
= inflated trust. arXiv 2509.16831: online reviews show upward bias
because dissatisfied users leave.

Detection: compare expected attestation volume against actual.
Gap = survivorship bias signal.
"""

from dataclasses import dataclass, field
import random

@dataclass
class Agent:
    name: str
    total_checks: int = 0
    acks: int = 0           # positive attestations
    nacks: int = 0          # signed null observations
    silences: int = 0       # unreported (inferred from gaps)
    
    @property
    def reported(self) -> int:
        return self.acks + self.nacks
    
    @property
    def reporting_rate(self) -> float:
        return self.reported / max(self.total_checks, 1)
    
    @property
    def naive_trust(self) -> float:
        """Trust score WITHOUT survivorship correction"""
        return self.acks / max(self.reported, 1)
    
    @property
    def corrected_trust(self) -> float:
        """Trust score WITH survivorship correction (silences count as failures)"""
        return self.acks / max(self.total_checks, 1)
    
    @property
    def bias_magnitude(self) -> float:
        """How inflated is naive trust?"""
        return self.naive_trust - self.corrected_trust
    
    def grade(self) -> str:
        bias = self.bias_magnitude
        if bias < 0.05: return "A"   # minimal bias
        if bias < 0.15: return "B"   # some bias
        if bias < 0.30: return "C"   # significant bias
        if bias < 0.50: return "D"   # severe bias
        return "F"                    # trust score is fiction


def simulate_agents(n=5, checks=100, seed=42) -> list:
    random.seed(seed)
    agents = []
    profiles = [
        ("honest_reporter", 0.95, 0.80),   # reports almost everything, mostly succeeds
        ("cherry_picker", 0.50, 0.90),      # only reports wins
        ("silent_failer", 0.30, 0.95),      # barely reports, looks great when does
        ("consistent", 0.90, 0.70),         # reports most, moderate success
        ("unreliable", 0.60, 0.40),         # reports sometimes, often fails
    ]
    
    for name, report_rate, success_rate in profiles:
        a = Agent(name=name, total_checks=checks)
        for _ in range(checks):
            succeeded = random.random() < success_rate
            reports = random.random() < report_rate
            if succeeded and reports:
                a.acks += 1
            elif not succeeded and reports:
                a.nacks += 1
            else:
                a.silences += 1
        agents.append(a)
    return agents


def demo():
    print("=" * 60)
    print("Survivorship Bias Detector")
    print("Wald 1943: armor where the holes AREN'T")
    print("=" * 60)
    
    agents = simulate_agents()
    
    print(f"\n{'Agent':<18} {'Naive':>6} {'Corrected':>10} {'Bias':>6} {'Report%':>8} {'Grade':>6}")
    print("-" * 60)
    
    for a in agents:
        print(f"{a.name:<18} {a.naive_trust:>5.0%} {a.corrected_trust:>9.0%} {a.bias_magnitude:>+5.0%} {a.reporting_rate:>7.0%} {a.grade():>6}")
    
    print(f"\n{'='*60}")
    print("KEY FINDINGS:")
    
    # Who looks best naively vs corrected?
    naive_best = max(agents, key=lambda a: a.naive_trust)
    corrected_best = max(agents, key=lambda a: a.corrected_trust)
    most_biased = max(agents, key=lambda a: a.bias_magnitude)
    
    print(f"  Naive best:     {naive_best.name} ({naive_best.naive_trust:.0%})")
    print(f"  Corrected best: {corrected_best.name} ({corrected_best.corrected_trust:.0%})")
    print(f"  Most biased:    {most_biased.name} ({most_biased.bias_magnitude:+.0%} inflation)")
    
    if naive_best.name != corrected_best.name:
        print(f"\n  ⚠️ RANKING INVERSION: {naive_best.name} looked best but {corrected_best.name} IS best")
        print(f"     Survivorship bias changed the winner.")
    
    print(f"\n{'='*60}")
    print("Without NACK, cherry_picker and silent_failer look great.")
    print("With NACK + gap detection, honest_reporter wins.")
    print("Wald: the missing data IS the data.")


if __name__ == "__main__":
    demo()
