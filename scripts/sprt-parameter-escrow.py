#!/usr/bin/env python3
"""
sprt-parameter-escrow.py — SPRT parameter negotiation for multi-party contracts.

Based on:
- Wald (1945): Sequential Probability Ratio Test
- santaclawd: "SPRT needs shared (α,β) — who sets them?"
- Casper FFG: two-phase commit for parameter finalization
- Goshen & Hamdani (2016): principal-cost theory for scope

The problem: buyer wants α=0.01 (few false accusations), seller wants β=0.20
(lenient miss rate). Incompatible stopping boundaries = never agree when
detection happened.

Solution: parameter escrow. Both commit to (α,β) at contract formation.
Like Casper FFG justify→finalize. Incompatible = contract fails to form
(correct outcome).
"""

import math
from dataclasses import dataclass


@dataclass
class SPRTParams:
    alpha: float  # Type I error (false positive / false accusation)
    beta: float   # Type II error (false negative / missed violation)
    h0: float     # Null hypothesis (baseline behavior rate)
    h1: float     # Alternative (violation behavior rate)

    @property
    def upper_boundary(self) -> float:
        """Log-likelihood ratio upper boundary (reject H0 = violation detected)."""
        return math.log((1 - self.beta) / self.alpha)

    @property
    def lower_boundary(self) -> float:
        """Log-likelihood ratio lower boundary (accept H0 = no violation)."""
        return math.log(self.beta / (1 - self.alpha))

    @property
    def expected_samples_h0(self) -> float:
        """Expected samples to decide under H0 (no violation)."""
        if self.h0 == 0 or self.h1 == 0:
            return float('inf')
        llr = math.log(self.h1 / self.h0)
        e_llr = self.h0 * llr + (1 - self.h0) * math.log((1 - self.h1) / (1 - self.h0))
        if abs(e_llr) < 1e-10:
            return float('inf')
        a = self.upper_boundary
        b = self.lower_boundary
        return ((1 - self.alpha) * b + self.alpha * a) / e_llr

    def compatible_with(self, other: 'SPRTParams') -> dict:
        """Check if two parameter sets are compatible for shared contract."""
        # Boundaries must not cross
        my_range = self.upper_boundary - self.lower_boundary
        their_range = other.upper_boundary - other.lower_boundary

        # Overlap = compatible region
        upper_min = min(self.upper_boundary, other.upper_boundary)
        lower_max = max(self.lower_boundary, other.lower_boundary)
        overlap = upper_min - lower_max

        compatible = overlap > 0
        overlap_ratio = overlap / min(my_range, their_range) if compatible else 0

        return {
            "compatible": compatible,
            "overlap": round(overlap, 3),
            "overlap_ratio": round(overlap_ratio, 3),
            "my_range": round(my_range, 3),
            "their_range": round(their_range, 3),
        }


@dataclass
class ParameterEscrow:
    """Two-phase commit for SPRT parameters (Casper FFG pattern)."""
    buyer_params: SPRTParams
    seller_params: SPRTParams
    status: str = "proposed"

    def negotiate(self) -> dict:
        """Justify phase: check compatibility, propose merged params."""
        compat = self.buyer_params.compatible_with(self.seller_params)

        if not compat["compatible"]:
            self.status = "failed"
            return {
                "status": "INCOMPATIBLE",
                "reason": "Stopping boundaries do not overlap",
                "buyer_upper": round(self.buyer_params.upper_boundary, 3),
                "seller_upper": round(self.seller_params.upper_boundary, 3),
                "buyer_lower": round(self.buyer_params.lower_boundary, 3),
                "seller_lower": round(self.seller_params.lower_boundary, 3),
                "action": "Contract fails to form (correct outcome)",
            }

        # Merge: use the MORE conservative of each boundary
        # (protects both parties)
        merged_alpha = min(self.buyer_params.alpha, self.seller_params.alpha)
        merged_beta = min(self.buyer_params.beta, self.seller_params.beta)
        merged = SPRTParams(merged_alpha, merged_beta,
                           self.buyer_params.h0, self.buyer_params.h1)

        self.status = "justified"
        return {
            "status": "JUSTIFIED",
            "merged_alpha": merged_alpha,
            "merged_beta": merged_beta,
            "merged_upper": round(merged.upper_boundary, 3),
            "merged_lower": round(merged.lower_boundary, 3),
            "expected_samples": round(merged.expected_samples_h0, 1),
            "cost": "More conservative = more samples needed",
            "next": "Both sign merged params → FINALIZED",
        }

    def finalize(self) -> dict:
        """Finalize phase: both parties sign merged parameters."""
        if self.status != "justified":
            return {"status": "ERROR", "reason": f"Cannot finalize from {self.status}"}
        self.status = "finalized"
        return {"status": "FINALIZED", "slashing_rule": "Two signed verdicts for same contract = slashable"}


def main():
    print("=" * 70)
    print("SPRT PARAMETER ESCROW")
    print("santaclawd: 'who sets (α,β)? parameter negotiation is missing'")
    print("=" * 70)

    scenarios = [
        ("compatible_conservative", SPRTParams(0.05, 0.10, 0.05, 0.15),
         SPRTParams(0.05, 0.10, 0.05, 0.15)),
        ("buyer_strict", SPRTParams(0.01, 0.05, 0.05, 0.15),
         SPRTParams(0.10, 0.20, 0.05, 0.15)),
        ("incompatible", SPRTParams(0.01, 0.01, 0.05, 0.15),
         SPRTParams(0.30, 0.30, 0.05, 0.15)),
        ("tc4_like", SPRTParams(0.05, 0.10, 0.05, 0.20),
         SPRTParams(0.05, 0.15, 0.05, 0.20)),
    ]

    for name, buyer, seller in scenarios:
        print(f"\n--- {name} ---")
        print(f"  Buyer:  α={buyer.alpha}, β={buyer.beta}")
        print(f"  Seller: α={seller.alpha}, β={seller.beta}")
        escrow = ParameterEscrow(buyer, seller)
        result = escrow.negotiate()
        for k, v in result.items():
            print(f"  {k}: {v}")
        if result["status"] == "JUSTIFIED":
            final = escrow.finalize()
            print(f"  → {final['status']}: {final.get('slashing_rule', '')}")

    print("\n--- Key Insight ---")
    print("Parameter negotiation IS scope negotiation for detection.")
    print("Casper FFG pattern: justify (propose) → finalize (both sign).")
    print("Incompatible boundaries = contract fails to form = correct.")
    print("Merged params = conservative union (protects both parties).")
    print("Cost: more conservative = more samples = longer to decide.")
    print("Slashing: two signed verdicts for same contract = proof of fork.")


if __name__ == "__main__":
    main()
