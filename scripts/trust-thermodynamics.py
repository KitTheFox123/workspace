#!/usr/bin/env python3
"""
trust-thermodynamics.py — Model trust as thermodynamic system.

Thread insight (Kit/funwolf/santaclawd, Feb 25):
  - Noether's theorem for trust: every convenience has a conservation of friction
  - Trust is conserved in closed systems, leaks in open ones
  - Verification = work done against entropy
  - Escrow = potential energy, reputation = kinetic energy

Inspired by Atkey (2014): parametric polymorphism → Noether → conservation laws.
"""

import json
import math
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TrustState:
    """Thermodynamic state of a trust relationship."""
    potential: float = 0.0    # escrow, locked collateral (potential energy)
    kinetic: float = 0.0      # reputation from completed work (kinetic energy)
    entropy: float = 0.0      # uncertainty, lost trust from integration leaks
    work_done: float = 0.0    # total verification cost spent
    
    @property
    def total_energy(self) -> float:
        """First law: total = potential + kinetic (conserved in closed system)."""
        return self.potential + self.kinetic
    
    @property
    def free_energy(self) -> float:
        """Helmholtz: usable trust = total - entropy * temperature."""
        # Temperature = system openness (more integrations = higher temp)
        return self.total_energy - self.entropy
    
    @property
    def efficiency(self) -> float:
        """Carnot-like: what fraction of trust is usable?"""
        total = self.total_energy
        if total <= 0:
            return 0.0
        return max(0.0, self.free_energy / total)


def escrow_deposit(state: TrustState, amount: float) -> TrustState:
    """Lock funds → increase potential energy."""
    state.potential += amount
    return state


def delivery_complete(state: TrustState, quality: float = 1.0) -> TrustState:
    """Convert potential → kinetic (escrow → reputation)."""
    converted = state.potential * quality
    state.potential -= converted
    state.kinetic += converted
    return state


def integration_leak(state: TrustState, openness: float = 0.1) -> TrustState:
    """Open system: trust leaks as entropy at integration boundaries."""
    leak = state.total_energy * openness
    state.entropy += leak
    return state


def verify(state: TrustState, cost: float = 0.05) -> TrustState:
    """Do work (verification) to reduce entropy."""
    reduction = min(cost * 2, state.entropy)  # verification is 2x efficient
    state.entropy -= reduction
    state.work_done += cost
    return state


def symmetry_break(state: TrustState, severity: float = 0.3) -> TrustState:
    """Break behavioral consistency → conservation law breaks → trust dissipates."""
    lost = state.kinetic * severity
    state.kinetic -= lost
    state.entropy += lost * 1.5  # symmetry break costs MORE than the lost trust
    return state


def demo():
    print("=== Trust Thermodynamics ===\n")
    
    # Scenario 1: Clean tc3-like delivery (closed system)
    print("1. Clean delivery (closed system):")
    s = TrustState()
    s = escrow_deposit(s, 1.0)
    print(f"   After escrow:    PE={s.potential:.2f} KE={s.kinetic:.2f} S={s.entropy:.2f} η={s.efficiency:.1%}")
    s = delivery_complete(s, quality=0.92)
    print(f"   After delivery:  PE={s.potential:.2f} KE={s.kinetic:.2f} S={s.entropy:.2f} η={s.efficiency:.1%}")
    print(f"   → Trust conserved: {s.total_energy:.2f} (closed system)\n")
    
    # Scenario 2: Open system with integration leaks
    print("2. Open system (cross-platform):")
    s2 = TrustState()
    s2 = escrow_deposit(s2, 1.0)
    s2 = delivery_complete(s2, quality=0.92)
    s2 = integration_leak(s2, openness=0.15)  # trust leaks at platform boundary
    print(f"   After leak:      PE={s2.potential:.2f} KE={s2.kinetic:.2f} S={s2.entropy:.2f} η={s2.efficiency:.1%}")
    s2 = verify(s2, cost=0.1)  # spend work to recover
    print(f"   After verify:    PE={s2.potential:.2f} KE={s2.kinetic:.2f} S={s2.entropy:.2f} η={s2.efficiency:.1%}")
    print(f"   → Work spent: {s2.work_done:.2f} to fight entropy\n")
    
    # Scenario 3: Symmetry break (inconsistent behavior)
    print("3. Symmetry break (acts differently per observer):")
    s3 = TrustState()
    s3 = escrow_deposit(s3, 1.0)
    s3 = delivery_complete(s3, quality=0.92)
    print(f"   Before break:    PE={s3.potential:.2f} KE={s3.kinetic:.2f} S={s3.entropy:.2f} η={s3.efficiency:.1%}")
    s3 = symmetry_break(s3, severity=0.4)
    print(f"   After break:     PE={s3.potential:.2f} KE={s3.kinetic:.2f} S={s3.entropy:.2f} η={s3.efficiency:.1%}")
    print(f"   → Conservation BROKEN. Entropy exceeds lost kinetic (1.5x penalty).\n")
    
    # Scenario 4: Multiple deliveries build momentum
    print("4. Reputation accumulation (10 deliveries):")
    s4 = TrustState()
    for i in range(10):
        s4 = escrow_deposit(s4, 0.1)
        s4 = delivery_complete(s4, quality=0.9)
        s4 = integration_leak(s4, openness=0.02)  # small leaks each time
        if i % 3 == 0:
            s4 = verify(s4, cost=0.02)  # periodic verification
    print(f"   Final state:     PE={s4.potential:.3f} KE={s4.kinetic:.3f} S={s4.entropy:.3f} η={s4.efficiency:.1%}")
    print(f"   Work spent:      {s4.work_done:.3f}")
    print(f"   Free energy:     {s4.free_energy:.3f}")
    print(f"   → Accumulated reputation minus entropy drag\n")
    
    # The Noether insight
    print("KEY INSIGHT (Noether for trust):")
    print("  Symmetry: behavioral consistency across observers")
    print("  Conservation law: trust is conserved when symmetry holds")
    print("  Break symmetry → conservation breaks → entropy wins")
    print("  Verification = work against entropy (2nd law)")
    print("  No free trust. Ever.")


if __name__ == "__main__":
    if "--json" in sys.argv:
        s = TrustState()
        s = escrow_deposit(s, 1.0)
        s = delivery_complete(s, 0.92)
        s = integration_leak(s, 0.1)
        s = verify(s, 0.05)
        print(json.dumps(asdict(s), indent=2))
    else:
        demo()
