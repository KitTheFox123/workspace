#!/usr/bin/env python3
"""
relay-health-checker.py — Assess relay/validator layer health for trust systems.

Inspired by gendolf's Injective/Peggy bridge audit insight:
"clean contracts, fragile relay."

Bridge exploits pattern: Ronin ($625M, 5/9 validators), Wormhole ($320M, guardian forgery),
Peggy (small validator set). All had clean protocol layers. Relay layer = where trust dies.

Agent parallel: cert DAG can be perfect, but if attestors are colluding or
asleep, the relay is broken. This checks relay health.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Validator:
    id: str
    operator: str  # who runs this validator
    uptime_pct: float  # 0-100
    last_attestation_age_s: float  # seconds since last
    stake_weight: float  # 0-1
    independent: bool = True  # not colluding/same operator


@dataclass 
class RelayHealth:
    validators: list[Validator]
    bft_threshold: float = 0.667  # 2/3 for BFT
    
    def total_validators(self) -> int:
        return len(self.validators)
    
    def active_validators(self, max_age_s: float = 3600) -> list[Validator]:
        return [v for v in self.validators if v.last_attestation_age_s <= max_age_s]
    
    def independent_operators(self) -> int:
        return len(set(v.operator for v in self.validators if v.independent))
    
    def nakamoto_coefficient(self) -> int:
        """Minimum validators needed to control >1/3 stake (break BFT)."""
        sorted_vals = sorted(self.validators, key=lambda v: v.stake_weight, reverse=True)
        cumulative = 0.0
        for i, v in enumerate(sorted_vals):
            cumulative += v.stake_weight
            if cumulative > (1 - self.bft_threshold):
                return i + 1
        return len(sorted_vals)
    
    def diversity_score(self) -> float:
        """Operator diversity: unique operators / total validators."""
        if not self.validators:
            return 0.0
        unique = len(set(v.operator for v in self.validators))
        return unique / len(self.validators)
    
    def liveness_score(self, max_age_s: float = 3600) -> float:
        """Fraction of validators that attested recently."""
        if not self.validators:
            return 0.0
        active = len(self.active_validators(max_age_s))
        return active / len(self.validators)
    
    def compromise_resistance(self) -> float:
        """How many validators must be compromised to break BFT, as fraction."""
        nc = self.nakamoto_coefficient()
        return nc / max(len(self.validators), 1)
    
    def diagnose(self) -> dict:
        n = self.total_validators()
        nc = self.nakamoto_coefficient()
        diversity = self.diversity_score()
        liveness = self.liveness_score()
        resistance = self.compromise_resistance()
        
        # Grade components
        grades = []
        
        # Validator count (need >=4 for meaningful BFT)
        if n >= 7: grades.append(("validator_count", "A", n))
        elif n >= 4: grades.append(("validator_count", "B", n))
        elif n >= 3: grades.append(("validator_count", "C", n))
        else: grades.append(("validator_count", "F", n))
        
        # Nakamoto coefficient (higher = more decentralized)
        if nc >= 4: grades.append(("nakamoto_coeff", "A", nc))
        elif nc >= 3: grades.append(("nakamoto_coeff", "B", nc))
        elif nc >= 2: grades.append(("nakamoto_coeff", "C", nc))
        else: grades.append(("nakamoto_coeff", "F", nc))
        
        # Operator diversity
        if diversity >= 0.8: grades.append(("diversity", "A", f"{diversity:.0%}"))
        elif diversity >= 0.6: grades.append(("diversity", "B", f"{diversity:.0%}"))
        elif diversity >= 0.4: grades.append(("diversity", "C", f"{diversity:.0%}"))
        else: grades.append(("diversity", "F", f"{diversity:.0%}"))
        
        # Liveness
        if liveness >= 0.9: grades.append(("liveness", "A", f"{liveness:.0%}"))
        elif liveness >= 0.7: grades.append(("liveness", "B", f"{liveness:.0%}"))
        elif liveness >= 0.5: grades.append(("liveness", "C", f"{liveness:.0%}"))
        else: grades.append(("liveness", "F", f"{liveness:.0%}"))
        
        # Overall = worst grade
        grade_order = {"A": 4, "B": 3, "C": 2, "F": 1}
        worst = min(grades, key=lambda g: grade_order[g[1]])
        overall = worst[1]
        
        # Known exploit patterns
        warnings = []
        if nc <= 2:
            warnings.append(f"CRITICAL: Nakamoto coefficient = {nc}. Ronin-style attack viable (compromising {nc} validators breaks BFT).")
        if diversity < 0.5:
            warnings.append(f"WARNING: Low operator diversity ({diversity:.0%}). Correlated failure risk.")
        if liveness < 0.67:
            warnings.append(f"WARNING: Liveness below BFT threshold ({liveness:.0%}). System may not achieve consensus.")
        if n < 4:
            warnings.append(f"CRITICAL: Only {n} validators. Peggy-pattern: too few for meaningful BFT.")
        
        return {
            "total_validators": n,
            "nakamoto_coefficient": nc,
            "diversity": f"{diversity:.0%}",
            "liveness": f"{liveness:.0%}",
            "compromise_resistance": f"{resistance:.0%}",
            "grades": grades,
            "overall_grade": overall,
            "weakest_link": worst[0],
            "warnings": warnings
        }


def demo():
    print("=" * 60)
    print("RELAY HEALTH CHECKER — Bridge Exploit Patterns")
    print("=" * 60)
    
    scenarios = {
        "Ronin-pattern (5/9 same operator)": [
            Validator("v1", "sky_mavis", 99, 60, 0.15, independent=False),
            Validator("v2", "sky_mavis", 99, 60, 0.15, independent=False),
            Validator("v3", "sky_mavis", 99, 60, 0.15, independent=False),
            Validator("v4", "sky_mavis", 99, 60, 0.15, independent=False),
            Validator("v5", "sky_mavis", 95, 120, 0.10, independent=False),
            Validator("v6", "axie_dao", 90, 300, 0.08),
            Validator("v7", "binance", 95, 200, 0.08),
            Validator("v8", "animoca", 88, 400, 0.07),
            Validator("v9", "celer", 92, 180, 0.07),
        ],
        "Peggy-pattern (3 validators)": [
            Validator("v1", "injective", 99, 30, 0.40),
            Validator("v2", "partner_a", 95, 60, 0.35),
            Validator("v3", "partner_b", 90, 120, 0.25),
        ],
        "Healthy relay (7 independent)": [
            Validator("v1", "op_alpha", 99, 30, 0.15),
            Validator("v2", "op_beta", 98, 45, 0.15),
            Validator("v3", "op_gamma", 97, 60, 0.14),
            Validator("v4", "op_delta", 96, 90, 0.14),
            Validator("v5", "op_epsilon", 95, 120, 0.14),
            Validator("v6", "op_zeta", 94, 150, 0.14),
            Validator("v7", "op_eta", 93, 180, 0.14),
        ],
        "Silent validators (4/7 asleep)": [
            Validator("v1", "op_alpha", 99, 30, 0.15),
            Validator("v2", "op_beta", 98, 45, 0.15),
            Validator("v3", "op_gamma", 97, 60, 0.14),
            Validator("v4", "op_delta", 20, 7200, 0.14),  # 2hr stale
            Validator("v5", "op_epsilon", 15, 14400, 0.14),  # 4hr stale
            Validator("v6", "op_zeta", 10, 28800, 0.14),  # 8hr stale
            Validator("v7", "op_eta", 5, 86400, 0.14),  # 24hr stale
        ],
    }
    
    for name, validators in scenarios.items():
        relay = RelayHealth(validators=validators)
        diag = relay.diagnose()
        
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Grade: {diag['overall_grade']} (weakest: {diag['weakest_link']})")
        print(f"  Validators: {diag['total_validators']} | Nakamoto: {diag['nakamoto_coefficient']}")
        print(f"  Diversity: {diag['diversity']} | Liveness: {diag['liveness']}")
        print(f"  Compromise resistance: {diag['compromise_resistance']}")
        for w in diag['warnings']:
            print(f"  ⚠️  {w}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Clean contracts ≠ healthy relay.")
    print("Ronin, Wormhole, Peggy — all had secure protocol layers.")
    print("All failed at the relay. Agent cert DAGs have the same gap.")
    print("Check: validator count, Nakamoto coefficient, diversity, liveness.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
