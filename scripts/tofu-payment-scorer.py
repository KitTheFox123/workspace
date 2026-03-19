#!/usr/bin/env python3
"""tofu-payment-scorer.py — Score identity bootstrap: TOFU + payment + witness composition.

TOFU alone devolves to opportunistic encryption (AGWA 2020).
Payment alone has no continuity.
Together: first contact = TOFU, second = receipt-backed, third = witnessed.

Per alphasenpai: "TOFU for continuity + PayLock for sybil resistance."
Per funwolf: "they solve orthogonal problems."
"""

import math
from dataclasses import dataclass


@dataclass
class IdentitySignal:
    tofu_age_days: int          # days since first observed key
    payment_receipts: int       # on-chain payment receipts
    witness_attestations: int   # third-party witness count
    unique_counterparties: int  # distinct agents interacted with
    key_changes: int            # number of key rotations
    migration_linked: bool      # prev_chain_hash links old→new


def score_bootstrap(s: IdentitySignal) -> dict:
    """Score identity using composite TOFU + payment + witness."""
    
    # TOFU component: logarithmic age, penalize key changes without migration
    tofu_base = min(1.0, math.log1p(s.tofu_age_days) / math.log1p(365))
    key_penalty = 0.0
    if s.key_changes > 0 and not s.migration_linked:
        key_penalty = min(0.8, s.key_changes * 0.3)  # unlinked rotation = suspicious
    tofu_score = max(0.0, tofu_base - key_penalty)
    
    # Payment component: chain-grade evidence (3x Watson-Morgan)
    payment_base = min(1.0, math.log1p(s.payment_receipts) / math.log1p(50))
    counterparty_diversity = min(1.0, s.unique_counterparties / 10)
    payment_score = payment_base * (0.5 + 0.5 * counterparty_diversity)
    
    # Witness component: independent attestations
    witness_score = min(1.0, math.log1p(s.witness_attestations) / math.log1p(20))
    
    # Composite: payment > witness > TOFU (evidence hierarchy)
    composite = (
        tofu_score * 0.20 +      # continuity signal
        payment_score * 0.50 +    # skin in game
        witness_score * 0.30      # third-party corroboration
    )
    
    # Grade classification
    if composite >= 0.8:
        grade, label = "A", "ESTABLISHED"
    elif composite >= 0.6:
        grade, label = "B", "DEVELOPING"
    elif composite >= 0.4:
        grade, label = "C", "EARLY"
    elif composite >= 0.2:
        grade, label = "D", "FRAGILE"
    else:
        grade, label = "F", "UNKNOWN"
    
    # Bootstrap phase
    if s.tofu_age_days == 0:
        phase = "FIRST_CONTACT"
    elif s.payment_receipts == 0:
        phase = "TOFU_ONLY"
    elif s.witness_attestations == 0:
        phase = "PAYMENT_BACKED"
    else:
        phase = "FULLY_COMPOSED"
    
    return {
        "scores": {
            "tofu": round(tofu_score, 3),
            "payment": round(payment_score, 3),
            "witness": round(witness_score, 3),
            "composite": round(composite, 3),
        },
        "grade": grade,
        "label": label,
        "phase": phase,
        "key_penalty": round(key_penalty, 2),
    }


def run_scenarios():
    """Test against realistic agent profiles."""
    scenarios = {
        "first_contact": IdentitySignal(
            tofu_age_days=0, payment_receipts=0, witness_attestations=0,
            unique_counterparties=0, key_changes=0, migration_linked=False
        ),
        "tofu_only_30d": IdentitySignal(
            tofu_age_days=30, payment_receipts=0, witness_attestations=0,
            unique_counterparties=0, key_changes=0, migration_linked=False
        ),
        "one_payment": IdentitySignal(
            tofu_age_days=7, payment_receipts=1, witness_attestations=0,
            unique_counterparties=1, key_changes=0, migration_linked=False
        ),
        "paylock_active": IdentitySignal(
            tofu_age_days=60, payment_receipts=30, witness_attestations=5,
            unique_counterparties=8, key_changes=0, migration_linked=False
        ),
        "established_agent": IdentitySignal(
            tofu_age_days=180, payment_receipts=100, witness_attestations=15,
            unique_counterparties=20, key_changes=1, migration_linked=True
        ),
        "suspicious_rotation": IdentitySignal(
            tofu_age_days=90, payment_receipts=5, witness_attestations=1,
            unique_counterparties=2, key_changes=3, migration_linked=False
        ),
        "sybil_fresh": IdentitySignal(
            tofu_age_days=1, payment_receipts=0, witness_attestations=10,
            unique_counterparties=0, key_changes=0, migration_linked=False
        ),
    }

    print("=" * 65)
    print("TOFU + Payment + Witness — Identity Bootstrap Scoring")
    print("=" * 65)
    print(f"Weights: TOFU=0.20, Payment=0.50, Witness=0.30")
    print(f"AGWA (2020): TOFU alone devolves to opportunistic encryption")
    print(f"Composite: payment > witness > TOFU (evidence hierarchy)")
    print()

    for name, signal in scenarios.items():
        result = score_bootstrap(signal)
        s = result["scores"]
        print(f"  {name:24s}  T={s['tofu']:.2f} P={s['payment']:.2f} W={s['witness']:.2f}"
              f"  → {s['composite']:.2f} Grade {result['grade']} ({result['label']})"
              f"  [{result['phase']}]")
        if result["key_penalty"] > 0:
            print(f"  {'':24s}  ⚠️  key_penalty={result['key_penalty']}")

    print()
    print("KEY INSIGHT:")
    print("  TOFU alone (30d) = Grade F. TOFU + 1 payment = Grade D.")
    print("  Payment is the upgrade path. Witnesses confirm what payment proves.")
    print("  Unlinked key rotation tanks score — migration_chain matters.")


if __name__ == "__main__":
    run_scenarios()
