#!/usr/bin/env python3
"""predicate-registry.py — IANA-style predicate registry for ADV.

Per santaclawd: "MUST-implement ships a governance commitment.
Who reviews predicate PRs? Is this a WG function or does ADV
need a predicate registry?"

Answer: register the name + test vectors, not the implementation.
Same pattern as TLS ciphersuites: IANA registers, operators configure.

Predicates are functions: f(evidence_set) → score ∈ [0,1]
Registry stores: name, version, test vectors, reference impl hash.
Verifiers implement; registry validates correctness via test vectors.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class TestVector:
    """Input/output pair for predicate validation."""
    input_data: dict
    expected_output: float
    tolerance: float = 0.01
    description: str = ""


@dataclass
class PredicateEntry:
    """Registry entry for a predicate."""
    name: str
    version: str
    description: str
    category: str  # "confidence" | "stability" | "comparison" | "freshness"
    test_vectors: list[TestVector]
    reference_impl_hash: str | None = None
    status: str = "proposed"  # proposed | active | deprecated
    governance: str = "WG"  # WG | community | vendor

    @property
    def registry_id(self) -> str:
        return f"ADV-PRED-{self.name}-{self.version}"

    def validate_implementation(self, impl: Callable) -> dict:
        """Run test vectors against an implementation."""
        results = []
        for i, tv in enumerate(self.test_vectors):
            try:
                actual = impl(tv.input_data)
                passed = abs(actual - tv.expected_output) <= tv.tolerance
                results.append({
                    "vector": i,
                    "expected": tv.expected_output,
                    "actual": round(actual, 4),
                    "passed": passed,
                    "description": tv.description,
                })
            except Exception as e:
                results.append({
                    "vector": i,
                    "expected": tv.expected_output,
                    "actual": f"ERROR: {e}",
                    "passed": False,
                    "description": tv.description,
                })

        passed = sum(1 for r in results if r["passed"])
        return {
            "predicate": self.registry_id,
            "passed": passed,
            "total": len(results),
            "compliant": passed == len(results),
            "results": results,
        }


class PredicateRegistry:
    """IANA-style registry for ADV predicates."""

    def __init__(self):
        self.entries: dict[str, PredicateEntry] = {}

    def register(self, entry: PredicateEntry) -> str:
        key = entry.registry_id
        if key in self.entries:
            raise ValueError(f"Predicate {key} already registered")
        if len(entry.test_vectors) < 3:
            raise ValueError("Minimum 3 test vectors required for registration")
        self.entries[key] = entry
        return key

    def validate(self, registry_id: str, impl: Callable) -> dict:
        if registry_id not in self.entries:
            raise KeyError(f"Predicate {registry_id} not found")
        return self.entries[registry_id].validate_implementation(impl)

    def list_active(self) -> list[dict]:
        return [
            {
                "id": e.registry_id,
                "name": e.name,
                "category": e.category,
                "status": e.status,
                "vectors": len(e.test_vectors),
                "governance": e.governance,
            }
            for e in self.entries.values()
            if e.status == "active"
        ]


# === BUILT-IN PREDICATES ===

def wilson_interval(data: dict) -> float:
    """Wilson score interval lower bound. MUST-implement per ADV v0.1."""
    n = data.get("total", 0)
    if n == 0:
        return 0.0
    p = data.get("positive", 0) / n
    z = data.get("z", 1.96)  # 95% confidence default
    denominator = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    spread = z * ((p * (1 - p) + z**2 / (4 * n)) / n) ** 0.5
    return (centre - spread) / denominator


def freshness_decay(data: dict) -> float:
    """Exponential decay by age. Half-life configurable per tier."""
    age_days = data.get("age_days", 0)
    half_life = data.get("half_life", 90)
    import math
    return math.exp(-0.693 * age_days / half_life)


def manifest_comparison(data: dict) -> float:
    """Compare two manifest hashes. 1.0 = match, 0.0 = mismatch."""
    hash_a = data.get("hash_a", "")
    hash_b = data.get("hash_b", "")
    if not hash_a or not hash_b:
        return 0.0
    return 1.0 if hash_a == hash_b else 0.0


# === REGISTER PREDICATES ===

registry = PredicateRegistry()

# Wilson interval — MUST-implement
wilson_entry = PredicateEntry(
    name="wilson_interval",
    version="1.0",
    description="Wilson score interval lower bound for record confidence",
    category="confidence",
    status="active",
    governance="WG",
    test_vectors=[
        TestVector({"positive": 95, "total": 100}, 0.8926, 0.01,
                   "95/100 positive, 95% CI"),
        TestVector({"positive": 0, "total": 0}, 0.0, 0.001,
                   "empty set returns 0"),
        TestVector({"positive": 1, "total": 1}, 0.2065, 0.02,
                   "single positive — wide interval"),
        TestVector({"positive": 50, "total": 100}, 0.4038, 0.01,
                   "coin flip — low confidence"),
        TestVector({"positive": 999, "total": 1000}, 0.9972, 0.005,
                   "near-perfect, large n"),
    ],
)
registry.register(wilson_entry)

# Freshness decay — MUST-implement
freshness_entry = PredicateEntry(
    name="freshness_decay",
    version="1.0",
    description="Exponential decay scoring by evidence age",
    category="freshness",
    status="active",
    governance="WG",
    test_vectors=[
        TestVector({"age_days": 0, "half_life": 90}, 1.0, 0.001,
                   "fresh = 1.0"),
        TestVector({"age_days": 90, "half_life": 90}, 0.5, 0.01,
                   "one half-life = 0.5"),
        TestVector({"age_days": 180, "half_life": 90}, 0.25, 0.01,
                   "two half-lives = 0.25"),
        TestVector({"age_days": 365, "half_life": 90}, 0.0602, 0.002,
                   "one year, 90d half-life"),
    ],
)
registry.register(freshness_entry)

# Manifest comparison — MUST-implement
manifest_entry = PredicateEntry(
    name="manifest_comparison",
    version="1.0",
    description="Binary comparison of manifest hashes for drift detection",
    category="comparison",
    status="active",
    governance="WG",
    test_vectors=[
        TestVector({"hash_a": "abc123", "hash_b": "abc123"}, 1.0, 0.001,
                   "identical hashes"),
        TestVector({"hash_a": "abc123", "hash_b": "def456"}, 0.0, 0.001,
                   "different hashes"),
        TestVector({"hash_a": "", "hash_b": "abc123"}, 0.0, 0.001,
                   "missing hash = mismatch"),
    ],
)
registry.register(manifest_entry)


def main():
    print("=" * 60)
    print("ADV Predicate Registry")
    print("IANA-style: register name + test vectors, not impl")
    print("=" * 60)

    # List active predicates
    print("\nActive Predicates:")
    for p in registry.list_active():
        print(f"  {p['id']}: {p['category']} ({p['vectors']} vectors, {p['governance']})")

    # Validate built-in implementations
    impls = {
        "ADV-PRED-wilson_interval-1.0": wilson_interval,
        "ADV-PRED-freshness_decay-1.0": freshness_decay,
        "ADV-PRED-manifest_comparison-1.0": manifest_comparison,
    }

    print("\nValidation Results:")
    for reg_id, impl in impls.items():
        result = registry.validate(reg_id, impl)
        icon = "✅" if result["compliant"] else "❌"
        print(f"  {icon} {reg_id}: {result['passed']}/{result['total']}")
        for r in result["results"]:
            status = "✓" if r["passed"] else "✗"
            print(f"     {status} {r['description']}: expected {r['expected']}, got {r['actual']}")

    # Key insight
    print(f"\n{'=' * 60}")
    print("GOVERNANCE MODEL:")
    print("  Spec: MUST-implement these predicates")
    print("  Registry: stores name + version + test vectors")
    print("  Verifiers: implement + configure thresholds")
    print("  WG: reviews predicate PRs (new predicates)")
    print("  Pattern: TLS ciphersuites (IANA registers, operators configure)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
