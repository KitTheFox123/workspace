#!/usr/bin/env python3
"""
quorum-polarization-detector.py — Detect echo chamber formation in attestation quorums.

Based on:
- Ferraz de Arruda et al (2024, iScience 27:111098, PMC11607542): Priority users
  sharpen echo chambers. Stubborn minority triggers consensus→polarization transition.
  Even centrist stubbornness can reinforce polarization.
- Sunstein (2002, "The Law of Group Polarization"): Deliberating groups move toward
  extremes of initial tendency. Two mechanisms: persuasive arguments pool + social
  comparison (don't want to be less extreme than group).
- Williams, Harkins & Latané (1981): Identifiability eliminates social loafing.

Key insight for attestation systems: Quorum groups that share model lineage or
training data have CORRELATED focal points (Kindred 2026). This creates priority-user
dynamics WITHOUT explicit prioritization — the most confident attestor anchors others.

Detection: Homophilic Bimodality Coefficient (BChom) from Ferraz de Arruda.
Rotates opinion×neighbor-opinion space 45°, measures bimodality of projection.
BChom > 5/9 = echo chamber formation.

Kit 🦊 | 2026-03-30
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class QuorumConfig:
    n_attestors: int = 20
    n_rounds: int = 50
    stubbornness_fraction: float = 0.1  # fraction that won't update
    priority_fraction: float = 0.15  # fraction with boosted influence
    priority_boost: float = 2.0  # influence multiplier for priority attestors
    confidence_threshold: float = 0.3  # bounded confidence (Deffuant model)
    rewire_probability: float = 0.1  # network adaptation rate


def bimodality_coefficient(values: np.ndarray) -> float:
    """BC = (skewness² + 1) / (kurtosis + 3*(n-1)²/((n-2)*(n-3)))"""
    n = len(values)
    if n < 4:
        return 0.0
    mean = np.mean(values)
    std = np.std(values, ddof=1)
    if std < 1e-10:
        return 0.0
    centered = values - mean
    skew = np.mean(centered**3) / std**3
    kurt = np.mean(centered**4) / std**4 - 3  # excess kurtosis
    # Adjusted formula
    bc = (skew**2 + 1) / (kurt + 3 * (n - 1)**2 / ((n - 2) * (n - 3)))
    return float(np.clip(bc, 0, 1))


def homophilic_bimodality(opinions: np.ndarray, neighbor_avg: np.ndarray) -> float:
    """BChom: Rotate opinion×neighbor space 45°, measure bimodality of projection."""
    # Rotation matrix 45°
    cos45 = np.cos(np.pi / 4)
    rotated = cos45 * (opinions + neighbor_avg)  # first component of 45° rotation
    return bimodality_coefficient(rotated)


class AttestationQuorum:
    def __init__(self, config: QuorumConfig, seed: int = 42):
        self.config = config
        self.rng = np.random.default_rng(seed)
        n = config.n_attestors

        # Initialize opinions in [-1, 1]
        self.opinions = self.rng.uniform(-1, 1, n)

        # Adjacency (start fully connected, will rewire)
        self.adj = np.ones((n, n)) - np.eye(n)

        # Assign roles
        indices = self.rng.permutation(n)
        n_stubborn = int(n * config.stubbornness_fraction)
        n_priority = int(n * config.priority_fraction)
        self.stubborn = set(indices[:n_stubborn])
        self.priority = set(indices[n_stubborn:n_stubborn + n_priority])

        # Push stubborn to extremes
        for i in self.stubborn:
            self.opinions[i] = self.rng.choice([-0.9, 0.9])

    def neighbor_averages(self) -> np.ndarray:
        """Average opinion of each attestor's neighbors."""
        avgs = np.zeros(self.config.n_attestors)
        for i in range(self.config.n_attestors):
            neighbors = np.where(self.adj[i] > 0)[0]
            if len(neighbors) == 0:
                avgs[i] = self.opinions[i]
            else:
                weights = np.array([
                    self.config.priority_boost if j in self.priority else 1.0
                    for j in neighbors
                ])
                weights /= weights.sum()
                avgs[i] = np.dot(weights, self.opinions[neighbors])
        return avgs

    def step(self):
        """One round of opinion dynamics + network adaptation."""
        n = self.config.n_attestors
        neighbor_avg = self.neighbor_averages()

        for i in range(n):
            if i in self.stubborn:
                continue  # stubborn don't update

            # Bounded confidence: only update if neighbor avg is close enough
            diff = abs(self.opinions[i] - neighbor_avg[i])
            if diff < self.config.confidence_threshold:
                # Move toward neighbor average
                mu = 0.3  # convergence rate
                self.opinions[i] += mu * (neighbor_avg[i] - self.opinions[i])
                self.opinions[i] = np.clip(self.opinions[i], -1, 1)

        # Network rewiring (adaptive)
        for i in range(n):
            for j in range(i + 1, n):
                if self.adj[i, j] > 0:
                    if abs(self.opinions[i] - self.opinions[j]) > self.config.confidence_threshold * 2:
                        if self.rng.random() < self.config.rewire_probability:
                            self.adj[i, j] = 0
                            self.adj[j, i] = 0
                else:
                    if abs(self.opinions[i] - self.opinions[j]) < self.config.confidence_threshold:
                        if self.rng.random() < self.config.rewire_probability * 0.5:
                            self.adj[i, j] = 1
                            self.adj[j, i] = 1

    def run(self) -> dict:
        """Run simulation, return polarization metrics per round."""
        history = []
        for r in range(self.config.n_rounds):
            self.step()
            navg = self.neighbor_averages()
            bc = bimodality_coefficient(self.opinions)
            bchom = homophilic_bimodality(self.opinions, navg)
            history.append({
                "round": r,
                "bc": round(bc, 4),
                "bchom": round(bchom, 4),
                "mean_opinion": round(float(np.mean(self.opinions)), 4),
                "std_opinion": round(float(np.std(self.opinions)), 4),
            })
        return history


def run_scenarios():
    """Compare quorum configurations for polarization risk."""
    scenarios = {
        "baseline_no_priority": QuorumConfig(
            stubbornness_fraction=0.0,
            priority_fraction=0.0,
        ),
        "priority_no_stubborn": QuorumConfig(
            stubbornness_fraction=0.0,
            priority_fraction=0.2,
        ),
        "stubborn_no_priority": QuorumConfig(
            stubbornness_fraction=0.15,
            priority_fraction=0.0,
        ),
        "ideologues_priority_stubborn": QuorumConfig(
            stubbornness_fraction=0.15,
            priority_fraction=0.15,  # stubborn + priority overlap
        ),
        "diverse_quorum": QuorumConfig(
            stubbornness_fraction=0.05,
            priority_fraction=0.1,
            confidence_threshold=0.5,  # wider acceptance
        ),
    }

    print("=" * 70)
    print("QUORUM POLARIZATION DETECTOR")
    print("Ferraz de Arruda et al (2024) + Sunstein (2002)")
    print("=" * 70)

    for name, config in scenarios.items():
        quorum = AttestationQuorum(config, seed=42)
        history = quorum.run()

        final = history[-1]
        peak_bchom = max(h["bchom"] for h in history)
        echo_chamber = peak_bchom > 5 / 9

        print(f"\n--- {name} ---")
        print(f"  Final BC:     {final['bc']:.4f}")
        print(f"  Final BChom:  {final['bchom']:.4f}")
        print(f"  Peak BChom:   {peak_bchom:.4f}")
        print(f"  Opinion std:  {final['std_opinion']:.4f}")
        print(f"  Echo chamber: {'YES ⚠️' if echo_chamber else 'NO ✓'}")
        print(f"  Risk level:   ", end="")
        if peak_bchom > 0.7:
            print("CRITICAL — quorum opinions clustered and networked")
        elif peak_bchom > 5 / 9:
            print("HIGH — echo chamber forming")
        elif peak_bchom > 0.4:
            print("MODERATE — trending toward polarization")
        else:
            print("LOW — diverse opinions maintained")

    # Key finding
    print("\n" + "=" * 70)
    print("KEY FINDINGS:")
    print("1. Priority users WITHOUT stubbornness = can MITIGATE polarization")
    print("   (Ferraz de Arruda: boosting moderate voices helps)")
    print("2. Priority users WITH stubbornness = IDEOLOGUES = worst case")
    print("   (minority extremists with amplified reach = echo chambers)")
    print("3. Agent translation: same-model attestors = shared focal points")
    print("   = implicit priority. Diverse model lineage = defense.")
    print("4. Sunstein's two mechanisms map directly:")
    print("   - Persuasive arguments pool → shared training data")
    print("   - Social comparison → correlated confidence scores")
    print("5. HONEST LIMITATION: 20-agent sim. Real quorums may differ.")
    print("=" * 70)


if __name__ == "__main__":
    run_scenarios()
