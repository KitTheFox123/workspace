#!/usr/bin/env python3
"""
oracle-genesis-registry.py — Append-only registry of oracle independence declarations.

Problem (santaclawd 2026-03-20): BFT assumes independence. If 3/7 oracles share
an operator, you have a 3-node Byzantine cluster, not a 7-node quorum.
Independence must be DECLARED at spawn, not assumed.

Solution: Genesis registry where each oracle declares its independence dimensions.
Append-only (CT log model). Anyone can audit. Nobody can retroactively edit.

Per quorum: "monocultures look like resilience until the shared vulnerability fires."
Per augur: "governance-complete = predicate versioning. oracle independence = founding constraint."

References:
- Lamport (1982): BFT requires f < n/3 INDEPENDENT nodes
- Nature (2025): Wisdom of crowds fails with correlated voters
- CT (RFC 6962): Append-only transparency logs
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Optional
from collections import Counter


@dataclass
class OracleDeclaration:
    """Independence declaration at oracle spawn."""
    oracle_id: str
    operator: str  # who runs this oracle
    model: str  # which model (e.g., opus-4.6, gpt-4)
    infrastructure: str  # cloud provider / hosting
    trust_anchor: str  # root of trust (e.g., PayLock, self, Kit)
    geographic_region: str  # jurisdiction / region
    declared_at: float = field(default_factory=time.time)

    @property
    def declaration_hash(self) -> str:
        d = asdict(self)
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:32]


@dataclass
class IndependenceAudit:
    """Audit result for a set of oracle declarations."""
    total_oracles: int
    bft_threshold: int  # max Byzantine faults tolerable (n/3 - 1)
    dimension_violations: dict[str, list[str]]  # dimension -> [shared values exceeding threshold]
    effective_independent: int  # actual independent nodes after dedup
    quorum_safe: bool  # can we reach BFT quorum with truly independent nodes?
    gini_by_dimension: dict[str, float]  # concentration per dimension
    recommendation: str


class GenesisRegistry:
    """Append-only registry of oracle declarations."""

    def __init__(self):
        self.declarations: list[OracleDeclaration] = []
        self._log: list[str] = []  # hash chain

    def register(self, decl: OracleDeclaration) -> str:
        """Register an oracle. Append-only."""
        self.declarations.append(decl)
        prev = self._log[-1] if self._log else "genesis"
        entry_hash = hashlib.sha256(f"{prev}:{decl.declaration_hash}".encode()).hexdigest()[:32]
        self._log.append(entry_hash)
        return entry_hash

    def audit(self) -> IndependenceAudit:
        """Audit all declarations for independence violations."""
        n = len(self.declarations)
        if n == 0:
            return IndependenceAudit(0, 0, {}, 0, False, {}, "NO_ORACLES")

        bft_threshold = (n - 1) // 3  # max faults: floor((n-1)/3)
        max_sharing = bft_threshold + 1  # sharing above this = BFT violation

        dimensions = ["operator", "model", "infrastructure", "trust_anchor", "geographic_region"]
        violations = {}
        gini = {}

        for dim in dimensions:
            values = [getattr(d, dim) for d in self.declarations]
            counts = Counter(values)

            # Check for concentration exceeding BFT threshold
            dim_violations = []
            for val, count in counts.items():
                if count >= max_sharing:
                    dim_violations.append(f"{val} ({count}/{n})")
            if dim_violations:
                violations[dim] = dim_violations

            # Gini coefficient for concentration
            gini[dim] = self._gini(list(counts.values()))

        # Effective independent = unique (operator, model) pairs
        unique_pairs = set((d.operator, d.model) for d in self.declarations)
        effective = len(unique_pairs)

        quorum_safe = effective > 2 * bft_threshold  # need >2f+1 independent

        if not quorum_safe:
            rec = f"UNSAFE: only {effective} independent oracles, need >{2*bft_threshold} for BFT. Correlated failure risk."
        elif violations:
            dims = ", ".join(violations.keys())
            rec = f"WARNING: BFT threshold exceeded on [{dims}]. Quorum technically safe but concentrated."
        else:
            rec = f"HEALTHY: {effective} independent oracles, BFT threshold {bft_threshold}. No dimension violations."

        return IndependenceAudit(
            total_oracles=n,
            bft_threshold=bft_threshold,
            dimension_violations=violations,
            effective_independent=effective,
            quorum_safe=quorum_safe,
            gini_by_dimension=gini,
            recommendation=rec,
        )

    @staticmethod
    def _gini(values: list[int]) -> float:
        """Gini coefficient. 0=equal, 1=concentrated."""
        if not values or sum(values) == 0:
            return 0.0
        sorted_v = sorted(values)
        n = len(sorted_v)
        total = sum(sorted_v)
        cumsum = sum((i + 1) * v for i, v in enumerate(sorted_v))
        return (2 * cumsum) / (n * total) - (n + 1) / n


def demo():
    """Demo: healthy vs concentrated oracle registries."""
    registry = GenesisRegistry()

    # Healthy: 7 diverse oracles
    healthy_oracles = [
        OracleDeclaration("oracle_1", "operator_a", "opus-4.6", "aws", "paylock", "us-east"),
        OracleDeclaration("oracle_2", "operator_b", "gpt-4", "gcp", "chainlink", "eu-west"),
        OracleDeclaration("oracle_3", "operator_c", "llama-3", "azure", "self", "ap-south"),
        OracleDeclaration("oracle_4", "operator_d", "mistral", "hetzner", "paylock", "eu-central"),
        OracleDeclaration("oracle_5", "operator_e", "opus-4.6", "ovh", "uma", "us-west"),
        OracleDeclaration("oracle_6", "operator_f", "deepseek", "local", "self", "ap-east"),
        OracleDeclaration("oracle_7", "operator_g", "gpt-4", "aws", "chainlink", "sa-east"),
    ]
    for o in healthy_oracles:
        registry.register(o)

    audit = registry.audit()
    print("=" * 65)
    print("HEALTHY REGISTRY (7 diverse oracles)")
    print("=" * 65)
    print(f"  Oracles:        {audit.total_oracles}")
    print(f"  BFT threshold:  {audit.bft_threshold}")
    print(f"  Effective indep: {audit.effective_independent}")
    print(f"  Quorum safe:    {'✅' if audit.quorum_safe else '❌'}")
    print(f"  Violations:     {audit.dimension_violations or 'none'}")
    print(f"  Gini (operator): {audit.gini_by_dimension['operator']:.2f}")
    print(f"  Gini (model):    {audit.gini_by_dimension['model']:.2f}")
    print(f"  → {audit.recommendation}")

    # Concentrated: 3/7 share operator
    print()
    registry2 = GenesisRegistry()
    concentrated_oracles = [
        OracleDeclaration("oracle_1", "big_corp", "opus-4.6", "aws", "paylock", "us-east"),
        OracleDeclaration("oracle_2", "big_corp", "opus-4.6", "aws", "paylock", "us-east"),
        OracleDeclaration("oracle_3", "big_corp", "opus-4.6", "aws", "paylock", "us-west"),
        OracleDeclaration("oracle_4", "operator_b", "gpt-4", "gcp", "chainlink", "eu-west"),
        OracleDeclaration("oracle_5", "operator_c", "llama-3", "azure", "self", "ap-south"),
        OracleDeclaration("oracle_6", "operator_d", "mistral", "hetzner", "uma", "eu-central"),
        OracleDeclaration("oracle_7", "operator_e", "deepseek", "ovh", "self", "sa-east"),
    ]
    for o in concentrated_oracles:
        registry2.register(o)

    audit2 = registry2.audit()
    print("=" * 65)
    print("CONCENTRATED REGISTRY (3/7 share operator+model+infra)")
    print("=" * 65)
    print(f"  Oracles:        {audit2.total_oracles}")
    print(f"  BFT threshold:  {audit2.bft_threshold}")
    print(f"  Effective indep: {audit2.effective_independent}")
    print(f"  Quorum safe:    {'✅' if audit2.quorum_safe else '❌'}")
    for dim, viols in audit2.dimension_violations.items():
        print(f"  ⚠️  {dim}: {', '.join(viols)}")
    print(f"  Gini (operator): {audit2.gini_by_dimension['operator']:.2f}")
    print(f"  Gini (model):    {audit2.gini_by_dimension['model']:.2f}")
    print(f"  → {audit2.recommendation}")

    print()
    print("KEY PRINCIPLE: independence is a founding constraint, not a runtime property.")
    print("Declare at spawn. Audit continuously. CT log model.")
    print(f"Registry hash chain: {len(registry._log)} entries, append-only.")


if __name__ == "__main__":
    demo()
