#!/usr/bin/env python3
"""
abc-drift-bound.py — Agent Behavioral Contracts drift bound simulator.

Based on Bhardwaj 2026 (arXiv 2602.22302):
  C = (Preconditions, Invariants, Governance, Recovery)
  Drift bound: D* = α/γ when γ > α
  (p, δ, k)-satisfaction: contracts hold with probability p, tolerance δ, recovery within k steps.

Maps our empirical attestation stack to ABC formal framework:
  scope_hash → Precondition
  CUSUM/watchdog → Invariant monitor
  graduated sanctions → Governance
  remediation-tracker → Recovery

Simulates Ornstein-Uhlenbeck drift process with contract enforcement.
"""

import math
import random
from dataclasses import dataclass


@dataclass
class ABContract:
    """Agent Behavioral Contract: C = (P, I, G, R)"""
    name: str
    alpha: float      # Natural drift rate
    gamma: float      # Recovery rate (must exceed alpha for bounded drift)
    delta: float      # Tolerance threshold for soft violations
    k_recovery: int   # Max steps to recover from violation
    
    @property
    def drift_bound(self) -> float:
        """D* = α/γ — steady-state drift bound"""
        if self.gamma <= 0:
            return float('inf')
        return self.alpha / self.gamma
    
    @property
    def is_stable(self) -> bool:
        """Contract is stable iff γ > α"""
        return self.gamma > self.alpha
    
    def concentration_bound(self, epsilon: float, t: int) -> float:
        """Gaussian concentration: P(D_t > D* + ε) ≤ exp(-2γεt)"""
        if self.gamma <= 0:
            return 1.0
        return math.exp(-2 * self.gamma * epsilon * t)


def simulate_drift(contract: ABContract, steps: int = 100, noise_std: float = 0.05) -> dict:
    """Simulate Ornstein-Uhlenbeck drift with contract enforcement."""
    drift = 0.0
    violations_soft = 0
    violations_hard = 0
    recoveries = 0
    max_drift = 0.0
    in_violation = False
    violation_start = 0
    recovery_times = []
    drift_history = []
    
    for t in range(steps):
        # Natural drift (random walk with drift rate α)
        drift += contract.alpha * random.gauss(0, noise_std)
        
        # Recovery force (mean-reverting at rate γ)
        drift -= contract.gamma * drift * 0.1  # Discrete approximation
        
        drift_history.append(abs(drift))
        max_drift = max(max_drift, abs(drift))
        
        # Check violations
        if abs(drift) > contract.delta:
            violations_soft += 1
            if not in_violation:
                in_violation = True
                violation_start = t
        
        if abs(drift) > contract.delta * 2:
            violations_hard += 1
        
        # Recovery check
        if in_violation and abs(drift) <= contract.delta:
            recovery_time = t - violation_start
            recovery_times.append(recovery_time)
            recoveries += 1
            in_violation = False
    
    avg_drift = sum(drift_history) / len(drift_history) if drift_history else 0
    avg_recovery = sum(recovery_times) / len(recovery_times) if recovery_times else 0
    
    # Grade based on drift bound compliance
    theoretical_bound = contract.drift_bound
    actual_ratio = avg_drift / theoretical_bound if theoretical_bound > 0 else float('inf')
    
    if actual_ratio <= 1.0 and violations_hard == 0:
        grade = "A"
    elif actual_ratio <= 1.5:
        grade = "B"
    elif actual_ratio <= 2.0:
        grade = "C"
    else:
        grade = "F"
    
    return {
        "contract": contract.name,
        "stable": contract.is_stable,
        "theoretical_bound": round(theoretical_bound, 4),
        "avg_drift": round(avg_drift, 4),
        "max_drift": round(max_drift, 4),
        "soft_violations": violations_soft,
        "hard_violations": violations_hard,
        "recoveries": recoveries,
        "avg_recovery_steps": round(avg_recovery, 1),
        "k_compliant": avg_recovery <= contract.k_recovery if recovery_times else True,
        "grade": grade,
    }


def demo():
    random.seed(42)
    
    contracts = [
        # Our attestation stack: high recovery rate, stable
        ABContract("isnad_full_stack", alpha=0.1, gamma=0.5, delta=0.3, k_recovery=5),
        # Weak monitoring: low recovery, barely stable
        ABContract("watchdog_only", alpha=0.1, gamma=0.15, delta=0.3, k_recovery=10),
        # No recovery: unstable (γ < α)
        ABContract("no_recovery", alpha=0.2, gamma=0.05, delta=0.3, k_recovery=20),
        # cassian's HygieneProof: remediation as recovery primitive
        ABContract("hygiene_proof", alpha=0.1, gamma=0.4, delta=0.2, k_recovery=3),
        # CRIU checkpoint: snapshot-based recovery
        ABContract("criu_checkpoint", alpha=0.15, gamma=0.6, delta=0.25, k_recovery=2),
    ]
    
    print("=" * 65)
    print("ABC DRIFT BOUND SIMULATOR")
    print("Bhardwaj 2026 (arXiv 2602.22302): D* = α/γ")
    print("=" * 65)
    
    for contract in contracts:
        result = simulate_drift(contract, steps=200)
        
        print(f"\n{'─' * 55}")
        print(f"Contract: {result['contract']} | Grade: {result['grade']}")
        print(f"  Stable: {result['stable']} | α={contract.alpha} γ={contract.gamma}")
        print(f"  Theoretical D*: {result['theoretical_bound']}")
        print(f"  Actual avg drift: {result['avg_drift']} (max: {result['max_drift']})")
        print(f"  Soft violations: {result['soft_violations']} | Hard: {result['hard_violations']}")
        print(f"  Recoveries: {result['recoveries']} | Avg steps: {result['avg_recovery_steps']}")
        print(f"  (p,δ,k)-compliant: {result['k_compliant']}")
        
        # Concentration bound at t=100
        eps = 0.1
        p_exceed = contract.concentration_bound(eps, 100)
        print(f"  P(D > D*+{eps}) at t=100: {p_exceed:.6f}")
    
    # Mapping to our stack
    print(f"\n{'=' * 65}")
    print("MAPPING: Our Stack → ABC Framework")
    print("─" * 55)
    mappings = [
        ("scope_hash", "Precondition (P)", "valid scope before action"),
        ("CUSUM/watchdog", "Invariant (I)", "behavioral drift monitor"),
        ("graduated sanctions", "Governance (G)", "Ostrom principle #5"),
        ("remediation-tracker", "Recovery (R)", "fix IS attestation event"),
    ]
    for our, abc, desc in mappings:
        print(f"  {our:25s} → {abc:20s} ({desc})")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT: γ > α is THE stability condition.")
    print("Recovery rate must exceed drift rate. Everything else is detail.")
    print("We built it empirically. Bhardwaj proved it formally.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
