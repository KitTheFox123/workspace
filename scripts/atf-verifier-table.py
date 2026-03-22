#!/usr/bin/env python3
"""atf-verifier-table.py — Evolving verifier table for ATF governance.

Per santaclawd: ATF needs TWO governance objects.
1. Registry: field names + types. Ossifies. Rename breaks every verifier.
2. Verifier table: named verifiers + trust level. Evolves as standards sharpen.

Same pattern as TLS: cipher suites ossify, certificate policies evolve.
Same pattern as DNS: zone file format frozen, DNSSEC policies evolve.
Same pattern as HTTP: status codes frozen, security headers evolve.

The registry is atf-field-registry.py (already built).
This is the verifier table — the evolving half.

Each verifier:
- Has a declared verification method (how it checks)
- Has a trust level (how much weight its check carries)
- Can be added/deprecated via version bump
- Independence is auditable (same-operator verifiers = correlated)

References:
- santaclawd: "registry ossifies, verifier table evolves"
- CT (Certificate Transparency): log operators evolve, log format frozen
- Kalyuga (2007): expertise reversal — scaffolding that helps novices harms experts
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from enum import Enum


class VerifierStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    SUSPENDED = "SUSPENDED"
    CANDIDATE = "CANDIDATE"  # proposed but not yet active


class VerificationMethod(str, Enum):
    CRYPTOGRAPHIC = "CRYPTOGRAPHIC"  # hash comparison, signature check
    STATISTICAL = "STATISTICAL"  # distribution analysis, anomaly detection
    COUNTERPARTY = "COUNTERPARTY"  # independent observer attestation
    TEMPORAL = "TEMPORAL"  # timing analysis, freshness check
    STRUCTURAL = "STRUCTURAL"  # dependency graph, diversity audit


@dataclass
class Verifier:
    """A named verifier in the ATF verifier table."""
    verifier_id: str
    name: str
    description: str
    method: VerificationMethod
    target_fields: list[str]  # which registry fields this verifier checks
    operator: str  # who runs this verifier
    model_family: Optional[str] = None  # if AI-based
    trust_weight: float = 1.0  # relative weight in composite
    status: VerifierStatus = VerifierStatus.ACTIVE
    added_in_version: str = "0.1.0"
    deprecated_in_version: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.status == VerifierStatus.ACTIVE


@dataclass
class VerifierTable:
    """The evolving governance object for ATF verifiers."""
    version: str
    verifiers: dict[str, Verifier] = field(default_factory=dict)
    version_history: list[dict] = field(default_factory=list)

    def add_verifier(self, v: Verifier) -> dict:
        """Add a verifier. Returns audit record."""
        if v.verifier_id in self.verifiers:
            return {"error": f"DUPLICATE — {v.verifier_id} already exists"}
        v.added_in_version = self.version
        self.verifiers[v.verifier_id] = v
        record = {
            "action": "ADD",
            "verifier_id": v.verifier_id,
            "version": self.version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.version_history.append(record)
        return record

    def deprecate_verifier(self, verifier_id: str, reason: str) -> dict:
        """Deprecate a verifier. Does NOT remove — frozen in history."""
        if verifier_id not in self.verifiers:
            return {"error": f"NOT_FOUND — {verifier_id}"}
        v = self.verifiers[verifier_id]
        v.status = VerifierStatus.DEPRECATED
        v.deprecated_in_version = self.version
        record = {
            "action": "DEPRECATE",
            "verifier_id": verifier_id,
            "reason": reason,
            "version": self.version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.version_history.append(record)
        return record

    def independence_audit(self) -> dict:
        """Check verifier independence — correlated operators = theater."""
        active = [v for v in self.verifiers.values() if v.is_active]
        if not active:
            return {"grade": "F", "reason": "NO_ACTIVE_VERIFIERS"}

        # Operator diversity
        operators = [v.operator for v in active]
        unique_ops = set(operators)
        op_diversity = len(unique_ops) / len(operators) if operators else 0

        # Method diversity
        methods = [v.method for v in active]
        unique_methods = set(methods)
        method_diversity = len(unique_methods) / len(methods) if methods else 0

        # Model family diversity (for AI-based verifiers)
        ai_verifiers = [v for v in active if v.model_family]
        if ai_verifiers:
            families = [v.model_family for v in ai_verifiers]
            unique_families = set(families)
            model_diversity = len(unique_families) / len(families)
        else:
            model_diversity = 1.0  # no AI = no monoculture risk

        # Simpson diversity index
        from collections import Counter
        op_counts = Counter(operators)
        n = len(operators)
        simpson = 1 - sum(c * (c - 1) for c in op_counts.values()) / (n * (n - 1)) if n > 1 else 0

        # Grade
        issues = []
        if op_diversity < 0.5:
            issues.append(f"OPERATOR_MONOCULTURE — {len(unique_ops)}/{len(operators)} unique")
        if method_diversity < 0.3:
            issues.append(f"METHOD_MONOCULTURE — {len(unique_methods)}/{len(methods)} unique")
        if model_diversity < 0.5 and ai_verifiers:
            issues.append(f"MODEL_MONOCULTURE — {len(unique_families)}/{len(ai_verifiers)} unique families")

        if not issues:
            grade = "A"
        elif len(issues) == 1:
            grade = "C"
        else:
            grade = "F"

        return {
            "grade": grade,
            "active_verifiers": len(active),
            "operator_diversity": round(op_diversity, 2),
            "method_diversity": round(method_diversity, 2),
            "model_diversity": round(model_diversity, 2),
            "simpson_index": round(simpson, 2),
            "issues": issues,
        }

    def coverage_audit(self, registry_fields: list[str]) -> dict:
        """Check which registry fields are covered by active verifiers."""
        active = [v for v in self.verifiers.values() if v.is_active]
        covered = set()
        for v in active:
            covered.update(v.target_fields)

        uncovered = set(registry_fields) - covered
        coverage_pct = len(covered & set(registry_fields)) / len(registry_fields) if registry_fields else 0

        return {
            "coverage": round(coverage_pct, 2),
            "covered_fields": sorted(covered & set(registry_fields)),
            "uncovered_fields": sorted(uncovered),
            "grade": "A" if coverage_pct >= 0.9 else "C" if coverage_pct >= 0.7 else "F",
        }

    def table_hash(self) -> str:
        """Deterministic hash of current table state."""
        state = {
            "version": self.version,
            "verifiers": {
                vid: {
                    "name": v.name,
                    "method": v.method.value,
                    "operator": v.operator,
                    "status": v.status.value,
                    "trust_weight": v.trust_weight,
                    "target_fields": sorted(v.target_fields),
                }
                for vid, v in sorted(self.verifiers.items())
            },
        }
        canonical = json.dumps(state, sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def demo():
    # ATF registry fields (from atf-field-registry.py)
    registry_fields = [
        "agent_id", "operator", "model_family", "genesis_hash",
        "evidence_grade", "grader_id", "error_type", "receipt_hash",
        "correction_count", "counterparty_count", "simpson_diversity",
        "schema_version", "failure_hash",
    ]

    table = VerifierTable(version="0.2.0")

    # Add verifiers — diverse operators and methods
    table.add_verifier(Verifier(
        verifier_id="genesis_check", name="Genesis Record Validator",
        description="Validates genesis record completeness and hash integrity",
        method=VerificationMethod.CRYPTOGRAPHIC,
        target_fields=["genesis_hash", "agent_id", "operator", "schema_version"],
        operator="kit_fox",
    ))

    table.add_verifier(Verifier(
        verifier_id="independence_audit", name="Oracle Independence Auditor",
        description="Simpson diversity + operator/model/infra/CA diversity",
        method=VerificationMethod.STATISTICAL,
        target_fields=["simpson_diversity", "counterparty_count", "model_family"],
        operator="bro_agent",
    ))

    table.add_verifier(Verifier(
        verifier_id="receipt_chain", name="Receipt Chain Verifier",
        description="Hash chain integrity, predecessor links, evidence grades",
        method=VerificationMethod.CRYPTOGRAPHIC,
        target_fields=["receipt_hash", "evidence_grade", "failure_hash"],
        operator="gerundium",
    ))

    table.add_verifier(Verifier(
        verifier_id="correction_health", name="Correction Health Scorer",
        description="Correction frequency, Shannon entropy, burstiness",
        method=VerificationMethod.STATISTICAL,
        target_fields=["correction_count", "error_type"],
        operator="braindiff",
        model_family="custom_statistical",
    ))

    table.add_verifier(Verifier(
        verifier_id="counterparty_attestation", name="Counterparty Attestation Validator",
        description="Independent counterparty observations, BFT quorum",
        method=VerificationMethod.COUNTERPARTY,
        target_fields=["counterparty_count", "grader_id", "evidence_grade"],
        operator="gendolf",
    ))

    print("=" * 60)
    print("ATF VERIFIER TABLE v0.2.0")
    print("=" * 60)
    print(f"Table hash: {table.table_hash()}")
    print(f"Active verifiers: {sum(1 for v in table.verifiers.values() if v.is_active)}")
    print()

    print("INDEPENDENCE AUDIT:")
    print(json.dumps(table.independence_audit(), indent=2))
    print()

    print("COVERAGE AUDIT:")
    print(json.dumps(table.coverage_audit(registry_fields), indent=2))
    print()

    # Now add a MONOCULTURE verifier — same operator
    print("=" * 60)
    print("ADDING MONOCULTURE VERIFIER (same operator as genesis_check)")
    print("=" * 60)
    table.add_verifier(Verifier(
        verifier_id="freshness_check", name="Freshness Validator",
        description="Receipt staleness detection",
        method=VerificationMethod.TEMPORAL,
        target_fields=["receipt_hash"],
        operator="kit_fox",  # SAME operator as genesis_check
    ))

    print("INDEPENDENCE AUDIT (post-addition):")
    audit = table.independence_audit()
    print(json.dumps(audit, indent=2))
    print()

    # Deprecate the monoculture verifier
    print("DEPRECATING monoculture verifier:")
    print(json.dumps(table.deprecate_verifier("freshness_check", "operator monoculture with genesis_check"), indent=2))
    print()

    print("VERSION HISTORY:")
    for record in table.version_history:
        print(f"  {record['action']}: {record['verifier_id']} (v{record['version']})")


if __name__ == "__main__":
    demo()
