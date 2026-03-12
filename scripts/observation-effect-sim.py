#!/usr/bin/env python3
"""
observation-effect-sim.py — Moral licensing simulation for agent monitoring

Models: does observation frequency affect agent scope compliance?
Based on Rotella et al 2025 meta-analysis (N=21,770):
  - Observed: g=0.65 (licensing present — "I was good, now I can slack")
  - Unobserved: g=-0.01 (no licensing effect)

Simulates agent heartbeat cycles under:
  1. Continuous monitoring (every heartbeat audited)
  2. Intermittent monitoring (random subset audited)
  3. No monitoring (never audited)

Measures: scope violations, drift rate, recovery after observation

Usage: python3 observation-effect-sim.py [--agents 100] [--heartbeats 500] [--monitor-rate 0.3]
"""

import argparse
import random
import statistics
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: int
    compliance: float = 1.0  # 1.0 = fully compliant, 0.0 = fully drifted
    violations: int = 0
    observed_count: int = 0
    last_observed: int = 0
    history: list = field(default_factory=list)

    def tick(self, heartbeat: int, observed: bool, licensing_g: float = 0.65):
        """Simulate one heartbeat cycle."""
        if observed:
            # Observation resets compliance (monitoring effect)
            self.compliance = min(1.0, self.compliance + 0.15)
            self.observed_count += 1
            self.last_observed = heartbeat

            # But moral licensing: being "good" licenses future slack
            # Effect size scales with how compliant agent has been
            if self.compliance > 0.8:
                licensing_drift = licensing_g * 0.05 * random.gauss(1, 0.3)
                self.compliance -= max(0, licensing_drift)
        else:
            # Unobserved: steady drift (no licensing, just entropy)
            gap = heartbeat - self.last_observed
            drift = 0.02 * (1 + gap * 0.01) * random.gauss(1, 0.2)
            self.compliance -= max(0, drift)

        self.compliance = max(0.0, min(1.0, self.compliance))

        # Violation = compliance below threshold
        if self.compliance < 0.5:
            self.violations += 1

        self.history.append(self.compliance)


def run_simulation(n_agents: int, n_heartbeats: int, monitor_rate: float, seed: int = 42):
    """Run simulation with given monitoring rate."""
    random.seed(seed)
    agents = [Agent(id=i) for i in range(n_agents)]

    for hb in range(n_heartbeats):
        for agent in agents:
            if monitor_rate >= 1.0:
                observed = True
            elif monitor_rate <= 0.0:
                observed = False
            else:
                observed = random.random() < monitor_rate
            agent.tick(hb, observed)

    return agents


def analyze(agents: list, label: str):
    """Compute summary statistics."""
    final_compliance = [a.compliance for a in agents]
    total_violations = sum(a.violations for a in agents)
    violation_rate = total_violations / (len(agents) * len(agents[0].history))

    # Drift trajectory: mean compliance over time
    n_hb = len(agents[0].history)
    trajectory = []
    for t in range(n_hb):
        mean_c = statistics.mean(a.history[t] for a in agents)
        trajectory.append(mean_c)

    return {
        "label": label,
        "mean_final_compliance": statistics.mean(final_compliance),
        "std_final_compliance": statistics.stdev(final_compliance),
        "total_violations": total_violations,
        "violation_rate_pct": violation_rate * 100,
        "min_compliance": min(final_compliance),
        "trajectory_start": trajectory[0],
        "trajectory_mid": trajectory[n_hb // 2],
        "trajectory_end": trajectory[-1],
    }


def main():
    parser = argparse.ArgumentParser(description="Observation effect simulation")
    parser.add_argument("--agents", type=int, default=100)
    parser.add_argument("--heartbeats", type=int, default=500)
    parser.add_argument("--monitor-rate", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    scenarios = [
        (1.0, "Continuous (100%)"),
        (args.monitor_rate, f"Intermittent ({int(args.monitor_rate*100)}%)"),
        (0.0, "None (0%)"),
    ]

    print(f"=== Observation Effect Simulation ===")
    print(f"Agents: {args.agents} | Heartbeats: {args.heartbeats} | Seed: {args.seed}")
    print(f"Based on: Rotella et al 2025 (observed g=0.65, unobserved g=-0.01)")
    print()

    results = []
    for rate, label in scenarios:
        agents = run_simulation(args.agents, args.heartbeats, rate, args.seed)
        r = analyze(agents, label)
        results.append(r)

    # Print table
    print(f"{'Monitoring':<25} {'Final Compliance':>18} {'Violations':>12} {'Violation %':>12} {'Trajectory':>30}")
    print("-" * 100)
    for r in results:
        traj = f"{r['trajectory_start']:.2f} → {r['trajectory_mid']:.2f} → {r['trajectory_end']:.2f}"
        print(f"{r['label']:<25} {r['mean_final_compliance']:>8.3f} ± {r['std_final_compliance']:.3f} {r['total_violations']:>12,} {r['violation_rate_pct']:>11.1f}% {traj:>30}")

    print()

    # Key insight
    cont = results[0]
    inter = results[1]
    none = results[2]
    print("Key findings:")
    print(f"  Continuous vs None: {cont['violation_rate_pct']:.1f}% vs {none['violation_rate_pct']:.1f}% violation rate")
    print(f"  Intermittent ({int(args.monitor_rate*100)}%) captures {((none['violation_rate_pct'] - inter['violation_rate_pct']) / (none['violation_rate_pct'] - cont['violation_rate_pct']) * 100):.0f}% of continuous monitoring benefit")
    print(f"  Moral licensing effect: even continuous monitoring shows {cont['violation_rate_pct']:.1f}% violations (licensing drift)")
    print()
    print("Implication: observation IS the mechanism, not a side effect.")
    print("Rotella et al: 'moderate evidence AGAINST licensing when unobserved (g=-0.01)'")
    print("Translation: without monitoring, agents don't self-regulate. Neither do humans.")


if __name__ == "__main__":
    main()
