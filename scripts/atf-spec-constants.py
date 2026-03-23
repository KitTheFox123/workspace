#!/usr/bin/env python3
"""
atf-spec-constants.py — ATF V1.1 normative constants registry.

Per santaclawd: "too many impl-defined constants = fragmentation risk."
X.509 solved this: normative constants in the spec.

This is THE canonical constants file. Every value is SPEC_NORMATIVE
(interop-critical) or SPEC_DEFAULT (safe override).

Two classes:
  SPEC_NORMATIVE — MUST NOT be overridden. Changing breaks interop.
  SPEC_DEFAULT — MAY be overridden with justification in genesis.

Usage:
    python3 atf-spec-constants.py [--validate agent.json]
"""

import json
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class Constant:
    name: str
    value: Any
    kind: str  # SPEC_NORMATIVE or SPEC_DEFAULT
    layer: str  # genesis, attestation, drift, revocation, composition, bootstrap, ceremony
    rationale: str
    x509_parallel: str = ""


# THE registry
CONSTANTS = [
    # === KS Test (burst detection) ===
    Constant("KS_REJECT_THRESHOLD", 0.05, "SPEC_NORMATIVE", "drift",
             "p < 0.05 = timing is non-Poisson = REJECT. Universal significance level.",
             "X.509 CRL: revocation is binary, not probabilistic"),
    Constant("KS_PASS_THRESHOLD", 0.30, "SPEC_NORMATIVE", "drift",
             "p > 0.30 = timing is Poisson-consistent = PASS. Conservative margin.",
             "X.509 OCSP: good/revoked/unknown three-state"),
    Constant("KS_MIN_SAMPLE", 30, "SPEC_NORMATIVE", "drift",
             "Minimum receipts before KS test applies. Below: Wilson CI instead. "
             "Central limit theorem: n=30 is standard minimum for distribution tests.",
             "X.509: minimum key length requirements"),

    # === Migration ===
    Constant("MIGRATION_WINDOW_FLOOR", 86400, "SPEC_NORMATIVE", "revocation",
             "24h minimum dual-sign window. Seconds. Shorter = counterparty can't verify.",
             "X.509 CRL: nextUpdate is normative"),
    Constant("MIGRATION_WINDOW_CEILING", 604800, "SPEC_DEFAULT", "revocation",
             "7d maximum dual-sign window. Seconds. Longer = attack surface.",
             "X.509: validity period bounded"),
    Constant("MIGRATION_MIN_WITNESSES", 2, "SPEC_NORMATIVE", "revocation",
             "Minimum independent counterparty witnesses for key rotation.",
             "X.509: minimum CA path length"),
    Constant("MIGRATION_CHALLENGE_WINDOW", 259200, "SPEC_DEFAULT", "revocation",
             "72h challenge period when n<3 witnesses. Seconds.",
             "X.509 CRL: grace period"),

    # === Bootstrap ===
    Constant("BOOTSTRAP_MIN_INTERACTIONS", 10, "SPEC_DEFAULT", "bootstrap",
             "Minimum interactions before migration is permitted.",
             "X.509: minimum validity period before renewal"),
    Constant("BOOTSTRAP_TIMEOUT", 604800, "SPEC_DEFAULT", "bootstrap",
             "7d max wait for voucher. Seconds. Timeout → MANUAL state.",
             "X.509: certificate request timeout"),

    # === Drift Detection ===
    Constant("JS_DIVERGENCE_FLOOR", 0.30, "SPEC_NORMATIVE", "drift",
             "Jensen-Shannon divergence ≥ 0.30 = OP_DRIFT. Agents may be stricter, not looser.",
             "X.509: key usage critical extension"),
    Constant("JS_DIVERGENCE_WARNING", 0.20, "SPEC_DEFAULT", "drift",
             "JS ≥ 0.20 = WARNING. Advisory, not blocking.",
             "X.509: nearing expiry notification"),
    Constant("CORRECTION_RANGE_MIN", 0.05, "SPEC_NORMATIVE", "attestation",
             "Correction frequency below 0.05 = SUSPICIOUSLY_LOW. Never wrong = not learning.",
             ""),
    Constant("CORRECTION_RANGE_MAX", 0.40, "SPEC_NORMATIVE", "attestation",
             "Correction frequency above 0.40 = UNSTABLE. Wrong too often.",
             ""),

    # === Trust Scoring ===
    Constant("DECAY_HALFLIFE_DAYS", 30, "SPEC_DEFAULT", "attestation",
             "Trust score decay half-life in days. Exponential.",
             "X.509: certificate validity period"),
    Constant("WILSON_CI_Z", 1.96, "SPEC_NORMATIVE", "bootstrap",
             "Z-score for Wilson confidence interval. 95% CI.",
             ""),
    Constant("COLD_START_PRIOR", 0.10, "SPEC_NORMATIVE", "bootstrap",
             "Default trust for unknown agents. Low = safe.",
             "X.509: untrusted root = rejected by default"),

    # === Quorum ===
    Constant("BFT_FAULT_FRACTION", 0.333, "SPEC_NORMATIVE", "composition",
             "f < n/3 Byzantine fault tolerance. Classic BFT bound.",
             "X.509: root store minimum CAs"),
    Constant("QUORUM_DEGRADED_REEMIT_HOURS", 12, "SPEC_DEFAULT", "composition",
             "Re-emit DEGRADED_QUORUM state every 12h.",
             "X.509 CRL: thisUpdate/nextUpdate cadence"),
    Constant("QUORUM_CONTESTED_REEMIT_HOURS", 6, "SPEC_DEFAULT", "composition",
             "Re-emit CONTESTED state every 6h.",
             "X.509 OCSP: responder refresh rate"),

    # === Ceremony ===
    Constant("CEREMONY_MIN_WITNESSES", 4, "SPEC_NORMATIVE", "ceremony",
             "Minimum witnesses for genesis ceremony. DNSSEC root signing: 7.",
             "X.509 key ceremony: minimum attendees"),
    Constant("CEREMONY_TRANSCRIPT_REQUIRED", True, "SPEC_NORMATIVE", "ceremony",
             "Ceremony MUST produce a hashable transcript.",
             "X.509 key ceremony: transcript is mandatory"),

    # === Error Types ===
    Constant("ERROR_TYPES_CORE", [
        "TIMEOUT", "MALFORMED_INPUT", "CAPABILITY_EXCEEDED",
        "DEPENDENCY_FAILURE", "INTERNAL", "SCOPE_VIOLATION",
        "RESOURCE_EXHAUSTED", "UNAUTHORIZED", "FORK_DETECTED"
    ], "SPEC_NORMATIVE", "attestation",
             "Core error type enum. Frozen. Extensions use ext: prefix.",
             "HTTP status codes: core set frozen since 1999"),

    # === Evidence Grade ===
    Constant("GRADE_SCALE", {"A": "independently verified", "B": "counterparty attested",
                              "C": "self-reported + corroborated", "D": "self-reported only",
                              "F": "unfalsifiable or missing"}, "SPEC_NORMATIVE", "attestation",
             "Evidence grade definitions. Frozen.",
             "X.509: trust anchor levels"),

    # === Governance ===
    Constant("REGISTRY_APPEND_ONLY", True, "SPEC_NORMATIVE", "genesis",
             "Field registry is append-only. Rename = new major version.",
             "IANA registries: append-only by design"),
    Constant("VERIFIER_TABLE_HOT_SWAP", True, "SPEC_NORMATIVE", "attestation",
             "Verifier table allows hot-swap updates. Independent of registry version.",
             "CT log list: updated independently of certificate format"),
]


def validate_agent_config(config: dict) -> dict:
    """Validate an agent's config against normative constants."""
    issues = []
    overrides = []

    for const in CONSTANTS:
        agent_val = config.get(const.name)
        if agent_val is None:
            continue

        if const.kind == "SPEC_NORMATIVE" and agent_val != const.value:
            issues.append({
                "field": const.name,
                "spec_value": const.value,
                "agent_value": agent_val,
                "severity": "BREAKING",
                "reason": f"SPEC_NORMATIVE: {const.rationale}",
            })
        elif const.kind == "SPEC_DEFAULT" and agent_val != const.value:
            overrides.append({
                "field": const.name,
                "spec_default": const.value,
                "agent_value": agent_val,
                "severity": "OVERRIDE",
                "reason": f"SPEC_DEFAULT override permitted: {const.rationale}",
            })

    normative_count = sum(1 for c in CONSTANTS if c.kind == "SPEC_NORMATIVE")
    default_count = sum(1 for c in CONSTANTS if c.kind == "SPEC_DEFAULT")

    grade = "A" if not issues else "D" if len(issues) <= 2 else "F"

    return {
        "valid": len(issues) == 0,
        "grade": grade,
        "normative_constants": normative_count,
        "default_constants": default_count,
        "total_constants": len(CONSTANTS),
        "breaking_issues": issues,
        "overrides": overrides,
        "registry_hash": _registry_hash(),
    }


def _registry_hash() -> str:
    import hashlib
    canonical = "|".join(
        f"{c.name}={c.value}:{c.kind}" for c in sorted(CONSTANTS, key=lambda x: x.name)
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def demo():
    print("=" * 60)
    print("ATF V1.1 Spec Constants Registry")
    print(f"Total: {len(CONSTANTS)} constants")
    print(f"SPEC_NORMATIVE: {sum(1 for c in CONSTANTS if c.kind == 'SPEC_NORMATIVE')}")
    print(f"SPEC_DEFAULT: {sum(1 for c in CONSTANTS if c.kind == 'SPEC_DEFAULT')}")
    print(f"Registry hash: {_registry_hash()}")
    print("=" * 60)

    # Group by layer
    layers = {}
    for c in CONSTANTS:
        layers.setdefault(c.layer, []).append(c)

    for layer, consts in sorted(layers.items()):
        print(f"\n--- {layer.upper()} ---")
        for c in consts:
            marker = "🔒" if c.kind == "SPEC_NORMATIVE" else "📝"
            print(f"  {marker} {c.name} = {c.value}")
            if c.x509_parallel:
                print(f"     ↳ X.509: {c.x509_parallel}")

    # Validate a compliant agent
    print("\n--- Validation: compliant agent ---")
    compliant = {"KS_REJECT_THRESHOLD": 0.05, "COLD_START_PRIOR": 0.10, "DECAY_HALFLIFE_DAYS": 14}
    result = validate_agent_config(compliant)
    print(json.dumps(result, indent=2))

    # Validate a non-compliant agent
    print("\n--- Validation: non-compliant agent ---")
    bad = {"KS_REJECT_THRESHOLD": 0.20, "COLD_START_PRIOR": 0.50, "JS_DIVERGENCE_FLOOR": 0.10}
    result2 = validate_agent_config(bad)
    print(json.dumps(result2, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--validate":
        with open(sys.argv[2]) as f:
            config = json.load(f)
        print(json.dumps(validate_agent_config(config), indent=2))
    else:
        demo()
