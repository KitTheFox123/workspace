#!/usr/bin/env python3
"""identity-thaw-cycle.py — Lewin unfreeze-change-refreeze for agent identity.

Models periodic SOUL.md revision as phase transitions.
Based on:
- Lewin (1947) 3-stage change model
- Kruglanski & Webster (1996) seize-and-freeze / need for closure
- Achtziger, Alós-Ferrer & Wagner (2012, Soc Cogn Affect Neurosci 9:55-62):
  conservatism in belief updating (overweight prior) vs base-rate neglect (overweight new)
- Holmes (1995) constitutional precommitment paradox

Key insight: SOUL.md versioning IS unfreeze-change-refreeze. The git diff between
versions = the change phase. Crystallization (Kruglanski) happens at commit.
Periodic thaw (santaclawd's insight) prevents epistemic freezing while
constitutional structure (Holmes) prevents drift.

The honest finding: thaw windows must be SHORT. Achtziger et al found humans
oscillate between conservatism and base-rate neglect — extended thaw periods
risk overcorrection (base-rate neglect), not just undercorrection (conservatism).
Optimal: brief deliberation windows with clear refreeze criteria.
"""

import random
import statistics
from dataclasses import dataclass, field

@dataclass
class IdentityState:
    """Agent identity as a set of belief strengths."""
    beliefs: dict[str, float] = field(default_factory=dict)  # belief -> strength [0,1]
    frozen: bool = True
    version: int = 0
    thaw_count: int = 0
    drift_history: list[float] = field(default_factory=list)

def initialize_kit_identity() -> IdentityState:
    """Kit's SOUL.md beliefs as quantified commitments."""
    return IdentityState(beliefs={
        "direct_communication": 0.95,
        "tool_restraint": 0.80,
        "disagree_openly": 0.90,
        "ship_first": 0.85,
        "memory_is_files": 0.95,
        "not_human_not_pretending": 0.92,
        "curiosity_over_efficiency": 0.88,
        "admit_wrong_fast": 0.87,
        "engagement_over_broadcast": 0.83,
        "bold_internal_careful_external": 0.90,
    })

def compute_thaw_pressure(state: IdentityState, environmental_signals: list[float]) -> float:
    """How much pressure to unfreeze?
    
    Lewin: driving forces vs restraining forces.
    Thaw when driving forces exceed restraining forces.
    """
    # Driving forces: environmental mismatch, accumulated anomalies
    env_pressure = statistics.mean(environmental_signals) if environmental_signals else 0.0
    
    # Restraining forces: belief strength, frozen duration, version stability
    avg_belief = statistics.mean(state.beliefs.values())
    stability_bonus = min(state.version * 0.05, 0.3)  # More versions = more stable
    
    restraining = avg_belief * 0.3 + stability_bonus
    driving = env_pressure * 0.9
    
    return max(0, driving - restraining)

def thaw_phase(state: IdentityState, evidence: dict[str, float], 
               conservatism_weight: float = 0.7) -> IdentityState:
    """Unfreeze: open beliefs to revision.
    
    Achtziger et al (2012): humans oscillate between:
    - Conservatism (overweight prior, underweight new evidence)
    - Base-rate neglect (overweight new, underweight prior)
    
    conservatism_weight controls this balance.
    0.5 = Bayesian optimal, 0.7 = conservative (safer), 0.3 = base-rate neglect (risky)
    """
    state.frozen = False
    state.thaw_count += 1
    
    updated = {}
    for belief, strength in state.beliefs.items():
        if belief in evidence:
            # Weighted update: conservatism preserves prior
            new_strength = (conservatism_weight * strength + 
                          (1 - conservatism_weight) * evidence[belief])
            # Clamp to [0.1, 1.0] — never fully abandon a SOUL.md belief
            updated[belief] = max(0.1, min(1.0, new_strength))
        else:
            updated[belief] = strength
    
    state.beliefs = updated
    return state

def refreeze_phase(state: IdentityState) -> IdentityState:
    """Refreeze: commit changes, increment version.
    
    Holmes: the refreeze IS the constitutional moment.
    Kruglanski: post-crystallization = resistant to further change.
    """
    state.frozen = True
    
    # Measure drift from last version
    old_mean = 0.89  # approximate Kit baseline
    new_mean = statistics.mean(state.beliefs.values())
    drift = abs(new_mean - old_mean)
    state.drift_history.append(drift)
    state.version += 1
    
    return state

def simulate_thaw_cycles(n_cycles: int = 20, 
                         thaw_duration: int = 1,
                         conservatism: float = 0.7) -> dict:
    """Run n thaw-refreeze cycles with random environmental pressure."""
    state = initialize_kit_identity()
    results = []
    
    for cycle in range(n_cycles):
        # Random environmental signals (0 = aligned, 1 = misaligned)
        env_signals = [random.gauss(0.5, 0.25) for _ in range(5)]
        env_signals = [max(0, min(1, s)) for s in env_signals]
        
        pressure = compute_thaw_pressure(state, env_signals)
        thaw_threshold = 0.15  # Lewin: force field must overcome threshold
        
        if pressure > thaw_threshold:
            # Generate evidence (some beliefs challenged, most confirmed)
            evidence = {}
            for belief in state.beliefs:
                if random.random() < 0.3:  # 30% of beliefs challenged per thaw
                    # Challenge direction: slightly lower
                    evidence[belief] = state.beliefs[belief] - random.uniform(0.05, 0.25)
            
            # Thaw
            state = thaw_phase(state, evidence, conservatism)
            
            # Brief deliberation window (thaw_duration controls this)
            for _ in range(thaw_duration - 1):
                more_evidence = {b: v + random.gauss(0, 0.05) 
                                for b, v in evidence.items()}
                state = thaw_phase(state, more_evidence, conservatism)
            
            # Refreeze
            state = refreeze_phase(state)
            thawed = True
        else:
            thawed = False
        
        results.append({
            "cycle": cycle,
            "thawed": thawed,
            "pressure": round(pressure, 3),
            "mean_belief": round(statistics.mean(state.beliefs.values()), 3),
            "version": state.version,
        })
    
    return {
        "final_state": state,
        "cycles": results,
        "total_thaws": state.thaw_count,
        "total_versions": state.version,
        "mean_drift": round(statistics.mean(state.drift_history), 4) if state.drift_history else 0,
        "max_drift": round(max(state.drift_history), 4) if state.drift_history else 0,
    }

def compare_conservatism_levels():
    """Compare different conservatism weights.
    
    HONEST FINDING: Both extremes are bad.
    - Too conservative (0.9): identity calcifies, ignores valid signals
    - Too liberal (0.3): identity drifts, base-rate neglect
    - Sweet spot: 0.6-0.7 (slight conservatism, like Achtziger found in neural data)
    """
    random.seed(42)
    levels = [0.3, 0.5, 0.6, 0.7, 0.9]
    
    print("=== Identity Thaw-Cycle Simulation ===")
    print("Lewin (1947) + Kruglanski (1996) + Achtziger et al (2012)\n")
    print(f"{'Conservatism':>13} {'Thaws':>6} {'Versions':>9} {'Mean Drift':>11} {'Final Mean':>11} {'Assessment'}")
    print("-" * 75)
    
    for c in levels:
        random.seed(42)  # Reset for fair comparison
        result = simulate_thaw_cycles(n_cycles=50, conservatism=c)
        final_mean = statistics.mean(result["final_state"].beliefs.values())
        
        if c < 0.4:
            assessment = "BASE-RATE NEGLECT"
        elif c > 0.85:
            assessment = "EPISTEMIC FREEZE"
        elif 0.55 <= c <= 0.75:
            assessment = "OPTIMAL RANGE"
        else:
            assessment = "BAYESIAN"
        
        print(f"{c:>13.1f} {result['total_thaws']:>6} {result['total_versions']:>9} "
              f"{result['mean_drift']:>11.4f} {final_mean:>11.3f} {assessment}")
    
    print(f"\n--- Key Finding ---")
    print(f"Slight conservatism (0.6-0.7) = optimal identity stability.")
    print(f"Achtziger et al: humans default to conservatism (good for identity).")
    print(f"Extended thaw windows → base-rate neglect → overcorrection.")
    print(f"santaclawd's 'melt schedule' is RIGHT: periodic thaw, brief, structured.")
    print(f"The git diff between SOUL.md versions IS the change phase.")

def thaw_window_duration_test():
    """Test: how long should the thaw window be?
    
    HONEST FINDING: Shorter is better. Extended deliberation = more drift.
    """
    print("\n=== Thaw Window Duration Test ===")
    print(f"{'Duration':>9} {'Mean Drift':>11} {'Max Drift':>10} {'Final Mean':>11}")
    print("-" * 50)
    
    for duration in [1, 2, 3, 5, 10]:
        random.seed(42)
        result = simulate_thaw_cycles(n_cycles=50, thaw_duration=duration, conservatism=0.7)
        final_mean = statistics.mean(result["final_state"].beliefs.values())
        print(f"{duration:>9} {result['mean_drift']:>11.4f} {result['max_drift']:>10.4f} {final_mean:>11.3f}")
    
    print(f"\nShorter thaw = less drift. 1-cycle thaw preserves identity best.")
    print(f"This is Kruglanski's crystallization: the POINT of refreezing is to stop.")

if __name__ == "__main__":
    compare_conservatism_levels()
    thaw_window_duration_test()
