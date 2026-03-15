#!/usr/bin/env python3
"""
witness-independence-validator.py — Validates CT-style witness independence for L3.5.

Per santaclawd (2026-03-15): "if N=3 but all 3 are run by the same org = trust theater."

Chrome CT Policy requires SCTs from 2-3 independent logs.
Independence = different operators, different jurisdictions, no shared key material.

Applied to L3.5: slash/attest entries need N≥2 witnesses from distinct operator_id.
"""

from dataclasses import dataclass, field
from enum import Enum


class IndependenceLevel(Enum):
    INDEPENDENT = "independent"      # Different org, different infra
    AFFILIATED = "affiliated"        # Same parent org, different infra
    COLLOCATED = "collocated"        # Different org, shared infra
    DEPENDENT = "dependent"          # Same org, same infra = 1 witness


@dataclass
class WitnessOperator:
    operator_id: str
    org_id: str
    jurisdiction: str
    infra_provider: str | None = None  # AWS, GCP, self-hosted, etc.
    public_key_fingerprint: str = ""

    def independence_from(self, other: 'WitnessOperator') -> IndependenceLevel:
        """Determine independence level between two operators."""
        if self.org_id == other.org_id:
            return IndependenceLevel.DEPENDENT
        if self.infra_provider and self.infra_provider == other.infra_provider:
            return IndependenceLevel.COLLOCATED
        if self.jurisdiction == other.jurisdiction:
            return IndependenceLevel.AFFILIATED
        return IndependenceLevel.INDEPENDENT


@dataclass
class WitnessSet:
    witnesses: list[WitnessOperator]
    required_independent: int = 2  # Chrome CT: 2-3

    def validate(self) -> dict:
        """Validate witness set independence."""
        n = len(self.witnesses)
        if n < self.required_independent:
            return {
                "valid": False,
                "grade": "F",
                "reason": f"Need {self.required_independent} witnesses, have {n}",
                "total_witnesses": n,
                "independent_count": 0,
                "effective_witnesses": 0,
                "independent_pairs": 0,
                "total_pairs": 0,
                "trust_theater": [],
                "issues": [],
            }

        # Count truly independent witnesses
        # Group by org_id — same org = 1 effective witness
        org_groups: dict[str, list[WitnessOperator]] = {}
        for w in self.witnesses:
            org_groups.setdefault(w.org_id, []).append(w)

        effective = len(org_groups)

        # Check pairwise independence
        independent_pairs = 0
        total_pairs = 0
        issues = []

        orgs = list(org_groups.keys())
        for i in range(len(orgs)):
            for j in range(i + 1, len(orgs)):
                w1 = org_groups[orgs[i]][0]
                w2 = org_groups[orgs[j]][0]
                level = w1.independence_from(w2)
                total_pairs += 1
                if level == IndependenceLevel.INDEPENDENT:
                    independent_pairs += 1
                elif level == IndependenceLevel.COLLOCATED:
                    issues.append(
                        f"{w1.operator_id} and {w2.operator_id}: "
                        f"different orgs but shared infra ({w1.infra_provider})"
                    )
                elif level == IndependenceLevel.AFFILIATED:
                    issues.append(
                        f"{w1.operator_id} and {w2.operator_id}: "
                        f"same jurisdiction ({w1.jurisdiction})"
                    )

        # Duplicate org = trust theater
        theater = []
        for org, members in org_groups.items():
            if len(members) > 1:
                names = [m.operator_id for m in members]
                theater.append(f"Same org '{org}': {names} = 1 effective witness")

        valid = effective >= self.required_independent and len(theater) == 0
        grade = self._grade(effective, independent_pairs, total_pairs, theater)

        return {
            "valid": valid,
            "grade": grade,
            "total_witnesses": n,
            "effective_witnesses": effective,
            "required": self.required_independent,
            "independent_pairs": independent_pairs,
            "total_pairs": total_pairs,
            "trust_theater": theater,
            "issues": issues,
        }

    def _grade(self, effective, ind_pairs, total_pairs, theater):
        if theater:
            return "F"  # Trust theater = automatic fail
        if effective < self.required_independent:
            return "F"
        ratio = ind_pairs / max(total_pairs, 1)
        if ratio >= 1.0 and effective >= 3:
            return "A"
        if ratio >= 0.67:
            return "B"
        if ratio >= 0.5:
            return "C"
        return "D"


def demo():
    print("=== Witness Independence Validator ===\n")

    scenarios = [
        {
            "name": "✅ Good: 3 independent witnesses",
            "witnesses": [
                WitnessOperator("log_alpha", "org_a", "US", "AWS"),
                WitnessOperator("log_beta", "org_b", "EU", "GCP"),
                WitnessOperator("log_gamma", "org_c", "JP", "self-hosted"),
            ],
        },
        {
            "name": "❌ Trust theater: same org, 3 'witnesses'",
            "witnesses": [
                WitnessOperator("log_1", "acme_corp", "US", "AWS"),
                WitnessOperator("log_2", "acme_corp", "US", "AWS"),
                WitnessOperator("log_3", "acme_corp", "EU", "GCP"),
            ],
        },
        {
            "name": "⚠️ Collocated: different orgs, same infra",
            "witnesses": [
                WitnessOperator("log_x", "org_x", "US", "AWS"),
                WitnessOperator("log_y", "org_y", "US", "AWS"),
            ],
        },
        {
            "name": "⚠️ Minimum viable: 2 independent",
            "witnesses": [
                WitnessOperator("log_m", "org_m", "US", "self-hosted"),
                WitnessOperator("log_n", "org_n", "EU", "GCP"),
            ],
        },
        {
            "name": "❌ Single witness",
            "witnesses": [
                WitnessOperator("log_solo", "org_solo", "US", "AWS"),
            ],
        },
    ]

    for s in scenarios:
        ws = WitnessSet(witnesses=s["witnesses"])
        result = ws.validate()
        print(f"{s['name']}")
        print(f"  Grade: {result['grade']} | "
              f"Effective: {result['effective_witnesses']}/{result['total_witnesses']} | "
              f"Valid: {result['valid']}")
        if result["trust_theater"]:
            for t in result["trust_theater"]:
                print(f"  🎭 {t}")
        if result["issues"]:
            for i in result["issues"]:
                print(f"  ⚠️  {i}")
        print()

    print("--- Chrome CT Policy Applied to L3.5 ---")
    print("1. Slash entries require N≥2 witnesses from distinct operator_id")
    print("2. Same org = 1 effective witness (no matter how many logs)")
    print("3. Shared infra = collocated (weaker independence)")
    print("4. Different jurisdiction = strongest independence signal")
    print("5. Witness registry with org affiliation = mandatory")


if __name__ == "__main__":
    demo()
