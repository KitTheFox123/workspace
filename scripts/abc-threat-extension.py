#!/usr/bin/env python3
"""
abc-threat-extension.py — Extends ABC contracts with adversary model parameter.

Based on:
- Bhardwaj (arXiv 2602.22302, Feb 2026): Agent Behavioral Contracts
  C = (P, I, G, R) with (p, δ, k)-satisfaction
  Drift Bound: D* = α/γ where γ > α
- santaclawd: "threat model IS the contract, not an appendix"
- Avenhaus et al (2001): Inspection games — adversary adapts

The gap: ABC assumes task model (benign drift). Strategic adversary
controls α (drift rate). ABC needs T parameter for threat model.

Extended contract: C' = (P, I, G, R, T) where T = threat model
- T.adversary_type: {benign, strategic, byzantine}
- T.alpha_control: can adversary modulate drift rate?
- T.k_adaptation: can adversary learn monitoring cadence?
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AdversaryType(Enum):
    BENIGN = "benign"           # Natural drift, no intent
    STRATEGIC = "strategic"     # Optimizes against detection
    BYZANTINE = "byzantine"     # Arbitrary, worst-case


class ContractHealth(Enum):
    SOUND = "SOUND"
    FRAGILE = "FRAGILE"
    BROKEN = "BROKEN"


@dataclass
class ThreatModel:
    """The missing T parameter in ABC."""
    adversary_type: AdversaryType
    alpha_max: float            # Max drift rate adversary can induce
    k_observable: bool          # Can adversary observe monitoring cadence?
    amendment_signed: bool      # Are contract changes co-signed?
    
    def effective_alpha(self, base_alpha: float) -> float:
        """Adversary's actual drift rate given their capabilities."""
        if self.adversary_type == AdversaryType.BENIGN:
            return base_alpha
        elif self.adversary_type == AdversaryType.STRATEGIC:
            # Strategic: stays just under detection threshold
            return self.alpha_max * 0.95  # 95% of max to avoid triggering
        else:  # Byzantine
            return self.alpha_max


@dataclass
class ABCContract:
    """Original ABC: C = (P, I, G, R) with (p, δ, k)."""
    name: str
    p: float        # Probability of compliance
    delta: float    # Deviation tolerance
    k: int          # Recovery steps
    gamma: float    # Recovery rate
    alpha: float    # Natural drift rate


@dataclass
class ExtendedABCContract:
    """Extended: C' = (P, I, G, R, T) with adaptive k."""
    name: str
    p: float
    delta: float
    k: int          # Base k
    gamma: float
    alpha: float    # Base alpha (benign)
    threat: ThreatModel
    k_variable: bool = False  # Can k change mid-contract?
    
    def effective_drift_bound(self) -> float:
        """D* = α_eff / γ — but with adversary-controlled α."""
        alpha_eff = self.threat.effective_alpha(self.alpha)
        if self.gamma <= 0:
            return float('inf')
        return alpha_eff / self.gamma
    
    def original_drift_bound(self) -> float:
        """Original ABC bound assuming benign drift."""
        if self.gamma <= 0:
            return float('inf')
        return self.alpha / self.gamma
    
    def health(self) -> ContractHealth:
        """Is the contract sound under the threat model?"""
        d_star = self.effective_drift_bound()
        if d_star < self.delta:
            return ContractHealth.SOUND
        elif d_star < self.delta * 2:
            return ContractHealth.FRAGILE
        else:
            return ContractHealth.BROKEN
    
    def k_needed_for_adversary(self) -> int:
        """Minimum k to detect strategic adversary."""
        alpha_eff = self.threat.effective_alpha(self.alpha)
        if alpha_eff <= 0:
            return 1
        # PAC: need enough samples to distinguish adversary from benign
        # N ≥ (1/2ε²) · ln(2/δ) where ε = alpha_eff - alpha
        epsilon = max(alpha_eff - self.alpha, 0.01)
        n = math.ceil((1 / (2 * epsilon**2)) * math.log(2 / (1 - self.p)))
        return max(n, self.k)
    
    def amendment_risk(self) -> str:
        """Risk of unilateral k amendment."""
        if not self.k_variable:
            return "FIXED_K_SAFE"
        if self.threat.amendment_signed:
            return "CO_SIGNED_OK"
        return "UNILATERAL_RISK"


def main():
    print("=" * 70)
    print("ABC THREAT MODEL EXTENSION")
    print("Bhardwaj (2602.22302) + santaclawd's critique")
    print("=" * 70)

    scenarios = [
        ExtendedABCContract(
            "abc_original_benign", p=0.95, delta=0.27, k=5,
            gamma=0.5, alpha=0.1,
            threat=ThreatModel(AdversaryType.BENIGN, 0.1, False, True),
        ),
        ExtendedABCContract(
            "abc_strategic_adversary", p=0.95, delta=0.27, k=5,
            gamma=0.5, alpha=0.1,
            threat=ThreatModel(AdversaryType.STRATEGIC, 0.6, True, False),
            k_variable=True,
        ),
        ExtendedABCContract(
            "abc_byzantine", p=0.95, delta=0.27, k=5,
            gamma=0.5, alpha=0.1,
            threat=ThreatModel(AdversaryType.BYZANTINE, 1.0, True, False),
        ),
        ExtendedABCContract(
            "abc_strategic_high_gamma", p=0.95, delta=0.27, k=5,
            gamma=1.5, alpha=0.1,  # 3x recovery rate
            threat=ThreatModel(AdversaryType.STRATEGIC, 0.6, True, True),
            k_variable=True,
        ),
        ExtendedABCContract(
            "abc_stochastic_k", p=0.95, delta=0.27, k=5,
            gamma=0.5, alpha=0.1,
            threat=ThreatModel(AdversaryType.STRATEGIC, 0.6, False, True),  # k NOT observable
            k_variable=True,
        ),
    ]

    print(f"\n{'Scenario':<28} {'D*orig':<8} {'D*adv':<8} {'Health':<10} {'k_needed':<9} {'Amend'}")
    print("-" * 75)

    for s in scenarios:
        d_orig = s.original_drift_bound()
        d_adv = s.effective_drift_bound()
        health = s.health()
        k_need = s.k_needed_for_adversary()
        amend = s.amendment_risk()
        print(f"{s.name:<28} {d_orig:<8.3f} {d_adv:<8.3f} {health.value:<10} {k_need:<9} {amend}")

    print("\n--- Key Findings ---")
    print("1. ABC Drift Bound (D*=α/γ) assumes benign α.")
    print("   Strategic adversary: D*=0.57/0.5=1.14 >> δ=0.27. Contract BROKEN.")
    print("2. High γ (1.5) recovers even against strategic: D*=0.38 < δ*2.")
    print("3. Stochastic k (adversary can't observe) = Avenhaus inspector advantage.")
    print("4. Unilateral k amendment without co-signing = attack surface.")
    print()
    print("Proposal: C' = (P, I, G, R, T) where T encodes:")
    print("  - adversary_type: {benign, strategic, byzantine}")
    print("  - alpha_max: worst-case drift rate")
    print("  - k_observable: is monitoring cadence visible?")
    print("  - amendment_signed: are changes co-signed?")
    print()
    print("The threat model IS the contract. — santaclawd")


if __name__ == "__main__":
    main()
