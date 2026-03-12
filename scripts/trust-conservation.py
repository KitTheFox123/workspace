#!/usr/bin/env python3
"""
trust-conservation.py — Noether's theorem applied to agent trust.

Insight from Clawk thread (Feb 25):
  - Every trust convenience has a conservation of friction (funwolf/cassian)
  - Trust is conserved, not created — you transform it (santaclawd)
  - Symmetry = behavioral consistency. Conservation = reputation persistence.
  - Break symmetry (context-switch behavior) → reputation decays.

Models trust as a conserved quantity that transforms between forms:
  escrow ↔ reputation ↔ attestation ↔ convenience

Like energy: kinetic ↔ potential ↔ thermal. Total budget fixed per transaction.
"""

import json
import math
from dataclasses import dataclass, asdict

@dataclass
class TrustState:
    """Trust budget decomposed into forms."""
    escrow: float      # Locked capital (potential trust)
    reputation: float  # Track record (kinetic trust)
    attestation: float # Third-party proof (radiated trust)
    convenience: float # Reduced friction (thermal/entropy)
    
    @property
    def total(self) -> float:
        return self.escrow + self.reputation + self.attestation + self.convenience
    
    def symmetry_score(self) -> float:
        """How evenly distributed across forms. Max entropy = max symmetry."""
        vals = [self.escrow, self.reputation, self.attestation, self.convenience]
        total = sum(vals)
        if total == 0:
            return 0.0
        entropy = 0.0
        for v in vals:
            p = v / total
            if p > 0:
                entropy -= p * math.log2(p)
        return round(entropy / 2.0, 3)  # Normalize to [0,1] (max entropy for 4 = 2 bits)


def transform(state: TrustState, n_clean_deliveries: int) -> list[TrustState]:
    """Simulate trust transformation over N clean deliveries.
    
    Escrow converts to reputation. Reputation enables attestation.
    Attestation unlocks convenience. Total stays constant.
    """
    history = [state]
    current = TrustState(**asdict(state))
    budget = current.total
    
    for i in range(1, n_clean_deliveries + 1):
        # Each clean delivery converts escrow → reputation
        transfer = current.escrow * 0.15  # 15% per delivery
        current.escrow -= transfer
        current.reputation += transfer * 0.8  # 80% becomes rep
        current.attestation += transfer * 0.15  # 15% becomes attestation
        current.convenience += transfer * 0.05  # 5% becomes convenience
        
        # Reputation also slowly converts to convenience (trust tax)
        tax = current.reputation * 0.02
        current.reputation -= tax
        current.convenience += tax
        
        # Normalize to conserve total
        scale = budget / current.total
        current = TrustState(
            escrow=round(current.escrow * scale, 4),
            reputation=round(current.reputation * scale, 4),
            attestation=round(current.attestation * scale, 4),
            convenience=round(current.convenience * scale, 4),
        )
        history.append(TrustState(**asdict(current)))
    
    return history


def symmetry_break(state: TrustState, severity: float = 0.5) -> TrustState:
    """Simulate symmetry breaking (inconsistent behavior).
    
    Reputation converts back to escrow requirement.
    Convenience reverts. Attestation damaged.
    severity: 0.0 = minor, 1.0 = total betrayal.
    """
    budget = state.total
    
    # Reputation damage → back to escrow
    rep_loss = state.reputation * severity
    att_loss = state.attestation * severity * 0.5
    conv_loss = state.convenience * severity
    
    new = TrustState(
        escrow=state.escrow + rep_loss + conv_loss,
        reputation=state.reputation - rep_loss,
        attestation=state.attestation - att_loss,
        convenience=state.convenience - conv_loss,
    )
    
    # Normalize
    scale = budget / new.total
    return TrustState(
        escrow=round(new.escrow * scale, 4),
        reputation=round(new.reputation * scale, 4),
        attestation=round(new.attestation * scale, 4),
        convenience=round(new.convenience * scale, 4),
    )


def demo():
    print("=== Trust Conservation Model (Noether) ===\n")
    
    # First contract: all escrow
    initial = TrustState(escrow=1.0, reputation=0.0, attestation=0.0, convenience=0.0)
    print(f"Initial (first contract): total={initial.total}")
    print(f"  escrow={initial.escrow}, rep={initial.reputation}, att={initial.attestation}, conv={initial.convenience}")
    print(f"  symmetry={initial.symmetry_score()}\n")
    
    # 10 clean deliveries
    history = transform(initial, 10)
    for i, s in enumerate(history):
        if i in [0, 1, 3, 5, 10]:
            print(f"After {i} deliveries: escrow={s.escrow:.3f} rep={s.reputation:.3f} att={s.attestation:.3f} conv={s.convenience:.3f} | total={s.total:.3f} symmetry={s.symmetry_score()}")
    
    # Symmetry break at delivery 10
    print(f"\n--- Symmetry Break (severity=0.5) ---")
    broken = symmetry_break(history[-1], severity=0.5)
    print(f"After break: escrow={broken.escrow:.3f} rep={broken.reputation:.3f} att={broken.attestation:.3f} conv={broken.convenience:.3f} | total={broken.total:.3f} symmetry={broken.symmetry_score()}")
    
    # Recovery: 5 more clean deliveries
    print(f"\n--- Recovery (5 clean deliveries) ---")
    recovery = transform(broken, 5)
    for i, s in enumerate(recovery):
        if i in [0, 1, 3, 5]:
            print(f"Recovery +{i}: escrow={s.escrow:.3f} rep={s.reputation:.3f} att={s.attestation:.3f} conv={s.convenience:.3f} | symmetry={s.symmetry_score()}")
    
    print(f"\nKey insight: total trust budget NEVER changes ({initial.total}). Only the form transforms.")
    print("Symmetry (behavioral consistency) determines which direction trust flows.")


if __name__ == "__main__":
    demo()
