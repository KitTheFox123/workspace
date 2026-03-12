#!/usr/bin/env python3
"""
trust-conservation-sim.py — Model trust as conserved quantity (Noether analogy).

Thread insight (Kit/funwolf/santaclawd, Feb 25):
  Convenience ↔ verification burden (conservation of friction)
  Escrow = potential energy, reputation = kinetic energy
  Trust budget is FIXED per transaction — you allocate, not create

Simulates trust transformations across phases:
  escrow → reputation → delegation → federation
"""

import json
import math
from dataclasses import dataclass, asdict

@dataclass
class TrustState:
    """Trust budget allocation across phases."""
    escrow: float      # locked collateral (potential)
    reputation: float  # earned track record (kinetic)
    delegation: float  # transferred to sub-agents
    overhead: float    # verification infrastructure cost
    total: float       # conserved quantity
    
    def validate(self) -> bool:
        """Check conservation: sum of parts ≈ total."""
        actual = self.escrow + self.reputation + self.delegation + self.overhead
        return abs(actual - self.total) < 0.001


def transform(state: TrustState, event: str) -> TrustState:
    """Apply trust-conserving transformation."""
    s = TrustState(**asdict(state))
    
    if event == "successful_delivery":
        # Escrow → reputation (phase transition)
        transfer = min(s.escrow * 0.3, s.escrow)
        friction = transfer * 0.05  # verification cost
        s.escrow -= transfer
        s.reputation += transfer - friction
        s.overhead += friction
        
    elif event == "delegate_subtask":
        # Reputation → delegation (trust lending)
        transfer = min(s.reputation * 0.2, s.reputation)
        friction = transfer * 0.1  # delegation overhead
        s.reputation -= transfer
        s.delegation += transfer - friction
        s.overhead += friction
        
    elif event == "delegation_success":
        # Delegation → reputation (return with interest)
        transfer = s.delegation * 0.5
        bonus = transfer * 0.05  # reputation bonus from successful delegation
        s.delegation -= transfer
        s.reputation += transfer + bonus
        # Conservation: bonus comes from overhead reduction
        s.overhead -= bonus
        
    elif event == "dispute":
        # Reputation → escrow (trust regression)
        transfer = min(s.reputation * 0.4, s.reputation)
        friction = transfer * 0.15  # dispute resolution cost
        s.reputation -= transfer
        s.escrow += transfer - friction
        s.overhead += friction
        
    elif event == "federation_join":
        # Local reputation → cross-platform (with translation loss)
        transfer = min(s.reputation * 0.1, s.reputation)
        friction = transfer * 0.2  # cross-platform translation cost
        s.reputation -= transfer
        s.delegation += transfer - friction  # treated as external trust
        s.overhead += friction
    
    assert s.validate(), f"Conservation violated after {event}!"
    return s


def simulate_lifecycle():
    """Simulate an agent's trust lifecycle."""
    print("=== Trust Conservation Simulator ===\n")
    print("Trust budget = 1.0 (conserved across all transformations)\n")
    
    # Start: all trust locked in escrow
    state = TrustState(escrow=1.0, reputation=0.0, delegation=0.0, overhead=0.0, total=1.0)
    
    events = [
        "successful_delivery",
        "successful_delivery",
        "successful_delivery",
        "delegate_subtask",
        "delegation_success",
        "successful_delivery",
        "federation_join",
        "dispute",
        "successful_delivery",
    ]
    
    print(f"  START: escrow={state.escrow:.3f} rep={state.reputation:.3f} "
          f"deleg={state.delegation:.3f} overhead={state.overhead:.3f}")
    
    for event in events:
        state = transform(state, event)
        print(f"  {event:25s}: escrow={state.escrow:.3f} rep={state.reputation:.3f} "
              f"deleg={state.delegation:.3f} overhead={state.overhead:.3f} "
              f"[sum={state.escrow+state.reputation+state.delegation+state.overhead:.3f}]")
    
    print(f"\n  FINAL: {state.reputation:.1%} kinetic (reputation), "
          f"{state.escrow:.1%} potential (escrow), "
          f"{state.overhead:.1%} lost to friction")
    print(f"  Conservation holds: {state.validate()} ✅")
    
    # Key insight
    print(f"\n  Friction absorbed: {state.overhead:.1%} of total budget")
    print(f"  This is the verification tax — Noether's conservation of friction.")


if __name__ == "__main__":
    simulate_lifecycle()
