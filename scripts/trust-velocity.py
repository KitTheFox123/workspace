#!/usr/bin/env python3
"""Trust Velocity — measure rate of trust change, not just trust level.

Key insight (santaclawd): Beta(10,1) vs Beta(10,2) is the difference between
"binary ban" and "calibrated forgiveness." The VELOCITY of trust change matters
more than the level.

Trust velocity = d(trust)/d(event). How much does each new receipt change your
reputation? High velocity = volatile (new agents). Low velocity = stable (veterans).

Usage:
  python trust-velocity.py --demo
  echo '{"events": [...]}' | python trust-velocity.py --json
"""

import json
import sys
import math


def beta_mean(alpha, beta):
    return alpha / (alpha + beta)


def beta_variance(alpha, beta):
    return (alpha * beta) / ((alpha + beta)**2 * (alpha + beta + 1))


def trust_trajectory(events: list, prior_alpha=1.0, prior_beta=1.0) -> dict:
    """Compute trust trajectory with velocity at each point."""
    alpha, beta = prior_alpha, prior_beta
    trajectory = []
    
    prev_trust = beta_mean(alpha, beta)
    
    for i, event in enumerate(events):
        outcome = event.get("outcome", "success")  # success or failure
        weight = event.get("weight", 1.0)  # proof-class diversity bonus
        
        if outcome == "success":
            alpha += weight
        else:
            beta += weight
        
        trust = beta_mean(alpha, beta)
        variance = beta_variance(alpha, beta)
        velocity = trust - prev_trust  # instantaneous velocity
        
        # Sensitivity: how much would ONE more failure change trust?
        hypothetical_fail = beta_mean(alpha, beta + 1)
        sensitivity = trust - hypothetical_fail
        
        # Stability: inverse of variance (higher = more stable)
        stability = 1.0 / (variance + 0.001)
        
        trajectory.append({
            "event": i + 1,
            "outcome": outcome,
            "alpha": round(alpha, 2),
            "beta": round(beta, 2),
            "trust": round(trust, 4),
            "velocity": round(velocity, 4),
            "sensitivity": round(sensitivity, 4),
            "stability": round(stability, 1),
            "phase": classify_phase(alpha, beta, velocity),
        })
        
        prev_trust = trust
    
    # Summary
    velocities = [t["velocity"] for t in trajectory]
    avg_velocity = sum(velocities) / len(velocities) if velocities else 0
    max_drop = min(velocities) if velocities else 0
    
    return {
        "final_trust": trajectory[-1]["trust"] if trajectory else 0.5,
        "final_phase": trajectory[-1]["phase"] if trajectory else "cold_start",
        "avg_velocity": round(avg_velocity, 4),
        "max_drop": round(max_drop, 4),
        "total_events": len(events),
        "trajectory": trajectory,
    }


def classify_phase(alpha, beta, velocity):
    """Classify agent's trust phase."""
    total = alpha + beta
    trust = alpha / total
    
    if total < 4:
        return "cold_start"
    elif total < 12:
        return "warming" if velocity >= 0 else "struggling"
    elif total < 30:
        return "establishing" if trust > 0.7 else "recovering"
    else:
        if trust > 0.9:
            return "veteran"
        elif trust > 0.7:
            return "reliable"
        else:
            return "damaged"


def compare_scenarios():
    """Compare trust velocity across different agent histories."""
    print("=" * 60)
    print("Trust Velocity Comparison")
    print("=" * 60)
    
    # Scenario 1: Clean new agent
    clean = [{"outcome": "success"} for _ in range(10)]
    result = trust_trajectory(clean)
    print(f"\n--- Clean Agent (10 successes) ---")
    print(f"Final trust: {result['final_trust']} | Phase: {result['final_phase']}")
    print(f"Avg velocity: {result['avg_velocity']} | Sensitivity: {result['trajectory'][-1]['sensitivity']}")
    
    # Scenario 2: One early failure
    early_fail = [{"outcome": "success"}] * 3 + [{"outcome": "failure"}] + [{"outcome": "success"}] * 6
    result = trust_trajectory(early_fail)
    print(f"\n--- Early Failure (fail at #4) ---")
    print(f"Final trust: {result['final_trust']} | Phase: {result['final_phase']}")
    print(f"Max drop: {result['max_drop']} | Recovery events: ", end="")
    # Find recovery point
    pre_fail = result['trajectory'][2]['trust']
    recovered = next((t['event'] for t in result['trajectory'][4:] if t['trust'] >= pre_fail), "never")
    print(recovered)
    
    # Scenario 3: One late failure (veteran)
    late_fail = [{"outcome": "success"}] * 49 + [{"outcome": "failure"}]
    result = trust_trajectory(late_fail)
    print(f"\n--- Late Failure (fail at #50) ---")
    print(f"Final trust: {result['final_trust']} | Phase: {result['final_phase']}")
    print(f"Max drop: {result['max_drop']} | Sensitivity: {result['trajectory'][-1]['sensitivity']}")
    
    # Scenario 4: Diverse proof classes (weighted)
    diverse = [{"outcome": "success", "weight": 1.5} for _ in range(5)]  # 3-class diversity bonus
    result = trust_trajectory(diverse)
    print(f"\n--- Diverse Proofs (3-class, 5 events) ---")
    print(f"Final trust: {result['final_trust']} | Phase: {result['final_phase']}")
    print(f"Stability: {result['trajectory'][-1]['stability']}")
    
    # Key comparison: santaclawd's insight
    print(f"\n--- santaclawd's Trust Velocity Insight ---")
    new = trust_trajectory([])
    ten_clean = trust_trajectory([{"outcome": "success"}] * 10)
    ten_one_fail = trust_trajectory([{"outcome": "success"}] * 10 + [{"outcome": "failure"}])
    
    print(f"Beta(1,1)  new agent:    trust={beta_mean(1,1):.3f}  (binary: unknown)")
    print(f"Beta(11,1) 10 receipts:  trust={beta_mean(11,1):.3f}  (calibrated: reliable)")
    print(f"Beta(11,2) +1 failure:   trust={beta_mean(11,2):.3f}  (calibrated: mostly reliable)")
    print(f"Velocity of failure: {beta_mean(11,2) - beta_mean(11,1):.4f}")
    print(f"Without receipts: trust=1.0 → trust=0.0 (binary ban)")
    print(f"With receipts: trust=0.917 → trust=0.846 (proportional adjustment)")
    print(f"That {beta_mean(11,1) - beta_mean(11,2):.1%} difference is load-bearing.")


def demo():
    compare_scenarios()


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = trust_trajectory(data.get("events", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
