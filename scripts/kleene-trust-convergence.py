#!/usr/bin/env python3
"""
kleene-trust-convergence.py — Kleene fixed point for trust score convergence.

santaclawd's insight: "trust score stabilizes when adding more receipts stops
changing the verdict. That is the termination condition for auditing."

Kleene: start from ⊥ (zero trust), iterate f(observe+update), converge to lfp.
Tarski: for non-monotone functions (gaming agents), need complete lattice.

Key: convergence rate IS diagnostic.
- Fast convergence = consistent behavior (honest or consistently bad)
- Slow convergence = noisy or gaming
- Non-convergence = actively adversarial
- Oscillating = gaming (alternating good/bad)

Usage:
    uv run --with numpy python3 scripts/kleene-trust-convergence.py
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class TrustIterator:
    """Iterate trust scoring until Kleene fixed point."""
    agent_id: str
    receipts: List[float]  # receipt scores [0,1]
    alpha: float = 0.3  # learning rate (EMA weight)
    epsilon: float = 0.005  # convergence threshold
    max_iter: int = 100

    def iterate(self) -> dict:
        """Run Kleene ascending chain from ⊥=0."""
        trust = 0.0  # ⊥ = bottom element
        history = [trust]
        deltas = []

        for i, receipt in enumerate(self.receipts):
            # f: trust_{n+1} = (1-α)*trust_n + α*receipt
            new_trust = (1 - self.alpha) * trust + self.alpha * receipt
            delta = abs(new_trust - trust)
            deltas.append(delta)
            trust = new_trust
            history.append(trust)

            # Check convergence
            if i >= 4:
                recent_deltas = deltas[-5:]
                if max(recent_deltas) < self.epsilon:
                    return self._result(history, deltas, i + 1, "CONVERGED")

        # Check final state
        if len(deltas) >= 3:
            recent = deltas[-3:]
            if max(recent) < self.epsilon * 2:
                return self._result(history, deltas, len(self.receipts), "NEAR_CONVERGED")

        # Check oscillation
        if len(deltas) >= 6:
            signs = [1 if deltas[i] > deltas[i-1] else -1 for i in range(1, len(deltas))]
            sign_changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i-1])
            if sign_changes > len(signs) * 0.6:
                return self._result(history, deltas, len(self.receipts), "OSCILLATING")

        return self._result(history, deltas, len(self.receipts), "NON_CONVERGENT")

    def _result(self, history, deltas, steps, status) -> dict:
        final_trust = history[-1]

        # Convergence rate = how fast deltas decay
        if len(deltas) >= 2:
            decay_rates = [deltas[i]/deltas[i-1] if deltas[i-1] > 0.001 else 1.0
                          for i in range(1, len(deltas))]
            avg_decay = np.mean(decay_rates)
        else:
            avg_decay = 1.0

        # Marginal evidence value (how much last 5 receipts changed score)
        if len(history) >= 6:
            marginal = abs(history[-1] - history[-6])
        else:
            marginal = abs(history[-1] - history[0])

        # Grade
        if status == "CONVERGED" and final_trust > 0.6:
            grade = "A"
        elif status == "CONVERGED":
            grade = "B"  # converged but low
        elif status == "NEAR_CONVERGED":
            grade = "B"
        elif status == "OSCILLATING":
            grade = "D"  # gaming signal
        else:
            grade = "C"

        return {
            "agent": self.agent_id,
            "status": status,
            "grade": grade,
            "final_trust": round(final_trust, 4),
            "steps_to_converge": steps,
            "convergence_rate": round(float(avg_decay), 4),
            "marginal_evidence_value": round(float(marginal), 4),
            "audit_recommendation": "STOP" if marginal < 0.01 else "CONTINUE",
        }


def demo():
    print("=" * 60)
    print("KLEENE TRUST CONVERGENCE")
    print("Trust stabilizes → stop auditing. santaclawd's termination.")
    print("=" * 60)
    np.random.seed(42)

    # Scenario 1: Honest agent — fast convergence
    print("\n--- Honest Agent (fast convergence) ---")
    honest = TrustIterator(
        "kit_fox",
        [0.8 + np.random.normal(0, 0.05) for _ in range(30)]
    )
    r1 = honest.iterate()
    for k, v in r1.items():
        print(f"  {k}: {v}")

    # Scenario 2: Gaming agent — oscillating
    print("\n--- Gaming Agent (oscillating) ---")
    gaming_receipts = []
    for i in range(30):
        gaming_receipts.append(0.9 if i % 2 == 0 else 0.2)
    gaming = TrustIterator("gamer", gaming_receipts)
    r2 = gaming.iterate()
    for k, v in r2.items():
        print(f"  {k}: {v}")

    # Scenario 3: Improving agent — slow convergence upward
    print("\n--- Improving Agent (slow convergence) ---")
    improving = TrustIterator(
        "newcomer",
        [min(0.3 + i * 0.025 + np.random.normal(0, 0.03), 1.0) for i in range(30)]
    )
    r3 = improving.iterate()
    for k, v in r3.items():
        print(f"  {k}: {v}")

    # Scenario 4: Declining agent — converges to low
    print("\n--- Declining Agent (converges low) ---")
    declining = TrustIterator(
        "fading",
        [max(0.8 - i * 0.02 + np.random.normal(0, 0.02), 0.0) for i in range(30)]
    )
    r4 = declining.iterate()
    for k, v in r4.items():
        print(f"  {k}: {v}")

    # Scenario 5: Byzantine — looks good then betrays
    print("\n--- Byzantine Agent (sudden betrayal) ---")
    byzantine = [0.85] * 20 + [0.1] * 10
    byz = TrustIterator("trojan", byzantine)
    r5 = byz.iterate()
    for k, v in r5.items():
        print(f"  {k}: {v}")

    print("\n--- SUMMARY ---")
    for r in [r1, r2, r3, r4, r5]:
        print(f"  {r['agent']}: {r['status']} ({r['grade']}) "
              f"trust={r['final_trust']} steps={r['steps_to_converge']} "
              f"audit={r['audit_recommendation']}")

    print("\n--- KEY INSIGHT ---")
    print("Kleene: iterate from ⊥, converge to lfp.")
    print("Convergence rate IS diagnostic:")
    print("  Fast + high = honest. Fast + low = consistently bad.")
    print("  Oscillating = gaming. Non-convergent = adversarial.")
    print("  Marginal evidence < ε → STOP AUDITING (santaclawd's termination)")


if __name__ == "__main__":
    demo()
