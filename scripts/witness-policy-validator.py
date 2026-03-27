#!/usr/bin/env python3
"""
witness-policy-validator.py — Validate ATF WITNESS_POLICY declarations.

From Clawk thread (2026-03-26/27): santaclawd proposed ATF witness market where
relying parties declare witness requirements, witnesses self-select by meeting criteria.

WITNESS_POLICY spec (minimum viable):
{
  "require": 2,                          # N-of-M threshold
  "from": ["rekor", "rfc3161", "ct"],    # Acceptable witness types
  "max_latency_ms": 5000,                # Maximum acceptable witness latency
  "min_jurisdictions": 2                  # Geographic diversity requirement
}

Witness types mapped to real infrastructure:
- rekor: Sigstore Rekor (append-only transparency log + Merkle tree)
- rfc3161: RFC 3161 Time-Stamp Authority (X.509 timestamps)
- ct: Certificate Transparency logs (RFC 9162)
- dkim: DKIM email headers (append-only by nature)
- git: Git push with signed commits (GitHub/GitLab hosted)

Design principles:
- No enrollment. Witnesses self-select by meeting policy criteria.
- Market discovers price. Witnesses compete on uptime + latency + diversity.
- Monitoring IS the security (CT model).
- Relying party bears risk, sets threshold.

References:
- RFC 9162: Certificate Transparency Version 2.0
- Sigstore: https://docs.sigstore.dev
- RFC 3161: Internet X.509 PKI Time-Stamp Protocol
- Apple CT policy: requires 2+ independent logs
- Google CT policy: requires SCTs from multiple log operators
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


VALID_WITNESS_TYPES = {"rekor", "rfc3161", "ct", "dkim", "git"}

# Known witness operators and their properties
KNOWN_WITNESSES = {
    "sigstore-rekor": {
        "type": "rekor",
        "operator": "sigstore-project",
        "jurisdiction": "US",
        "avg_latency_ms": 200,
        "uptime_sla": 0.999,
        "append_only": True,
        "independently_auditable": True,
    },
    "google-argon": {
        "type": "ct",
        "operator": "google",
        "jurisdiction": "US",
        "avg_latency_ms": 150,
        "uptime_sla": 0.9999,
        "append_only": True,
        "independently_auditable": True,
    },
    "cloudflare-nimbus": {
        "type": "ct",
        "operator": "cloudflare",
        "jurisdiction": "US",
        "avg_latency_ms": 100,
        "uptime_sla": 0.9999,
        "append_only": True,
        "independently_auditable": True,
    },
    "letsencrypt-oak": {
        "type": "ct",
        "operator": "letsencrypt",
        "jurisdiction": "US",
        "avg_latency_ms": 250,
        "uptime_sla": 0.999,
        "append_only": True,
        "independently_auditable": True,
    },
    "sectigo-mammoth": {
        "type": "ct",
        "operator": "sectigo",
        "jurisdiction": "UK",
        "avg_latency_ms": 300,
        "uptime_sla": 0.999,
        "append_only": True,
        "independently_auditable": True,
    },
    "digicert-nessie": {
        "type": "ct",
        "operator": "digicert",
        "jurisdiction": "US",
        "avg_latency_ms": 180,
        "uptime_sla": 0.999,
        "append_only": True,
        "independently_auditable": True,
    },
    "freetsa-org": {
        "type": "rfc3161",
        "operator": "freetsa",
        "jurisdiction": "DE",
        "avg_latency_ms": 500,
        "uptime_sla": 0.99,
        "append_only": True,
        "independently_auditable": True,
    },
    "zeitstempel-dfn": {
        "type": "rfc3161",
        "operator": "dfn-verein",
        "jurisdiction": "DE",
        "avg_latency_ms": 400,
        "uptime_sla": 0.999,
        "append_only": True,
        "independently_auditable": True,
    },
    "github-push": {
        "type": "git",
        "operator": "github",
        "jurisdiction": "US",
        "avg_latency_ms": 1000,
        "uptime_sla": 0.999,
        "append_only": False,  # force push exists
        "independently_auditable": False,
    },
}


@dataclass
class WitnessPolicy:
    """A relying party's witness requirements."""
    require: int                    # N-of-M threshold
    from_types: list[str]           # Acceptable witness types
    max_latency_ms: int = 5000      # Max acceptable latency
    min_jurisdictions: int = 2      # Geographic diversity
    min_operators: int = 2          # Operator diversity
    require_append_only: bool = True  # Must be append-only
    require_auditable: bool = True    # Must be independently auditable


@dataclass 
class WitnessReceipt:
    """A witness's signed receipt for an attestation."""
    witness_id: str
    witness_type: str
    operator: str
    jurisdiction: str
    timestamp: str
    latency_ms: int
    inclusion_proof: Optional[str] = None  # Merkle proof for transparency logs


@dataclass
class ValidationResult:
    """Result of validating witness receipts against a policy."""
    valid: bool
    policy: dict
    receipts_provided: int
    receipts_accepted: int
    threshold_met: bool
    jurisdiction_diversity_met: bool
    operator_diversity_met: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class WitnessPolicyValidator:
    """Validate witness receipts against a WITNESS_POLICY."""
    
    def validate(self, policy: WitnessPolicy, receipts: list[WitnessReceipt]) -> ValidationResult:
        errors = []
        warnings = []
        accepted = []
        
        # 1. Filter receipts by policy constraints
        for r in receipts:
            if r.witness_type not in policy.from_types:
                warnings.append(f"{r.witness_id}: type '{r.witness_type}' not in policy from_types")
                continue
            
            if r.latency_ms > policy.max_latency_ms:
                warnings.append(f"{r.witness_id}: latency {r.latency_ms}ms > max {policy.max_latency_ms}ms")
                continue
            
            witness_info = KNOWN_WITNESSES.get(r.witness_id)
            if witness_info:
                if policy.require_append_only and not witness_info["append_only"]:
                    warnings.append(f"{r.witness_id}: not append-only, policy requires it")
                    continue
                if policy.require_auditable and not witness_info["independently_auditable"]:
                    warnings.append(f"{r.witness_id}: not independently auditable")
                    continue
            
            accepted.append(r)
        
        # 2. Check threshold
        threshold_met = len(accepted) >= policy.require
        if not threshold_met:
            errors.append(f"Need {policy.require} witnesses, only {len(accepted)} accepted")
        
        # 3. Check jurisdiction diversity
        jurisdictions = set(r.jurisdiction for r in accepted)
        jurisdiction_met = len(jurisdictions) >= policy.min_jurisdictions
        if not jurisdiction_met:
            errors.append(f"Need {policy.min_jurisdictions} jurisdictions, have {len(jurisdictions)}: {jurisdictions}")
        
        # 4. Check operator diversity
        operators = set(r.operator for r in accepted)
        operator_met = len(operators) >= policy.min_operators
        if not operator_met:
            errors.append(f"Need {policy.min_operators} operators, have {len(operators)}: {operators}")
        
        valid = threshold_met and jurisdiction_met and operator_met and len(errors) == 0
        
        return ValidationResult(
            valid=valid,
            policy={
                "require": policy.require,
                "from": policy.from_types,
                "max_latency_ms": policy.max_latency_ms,
                "min_jurisdictions": policy.min_jurisdictions,
                "min_operators": policy.min_operators,
            },
            receipts_provided=len(receipts),
            receipts_accepted=len(accepted),
            threshold_met=threshold_met,
            jurisdiction_diversity_met=jurisdiction_met,
            operator_diversity_met=operator_met,
            errors=errors,
            warnings=warnings,
        )
    
    def find_satisfying_witnesses(self, policy: WitnessPolicy) -> dict:
        """Find which known witnesses could satisfy a policy."""
        candidates = []
        for wid, info in KNOWN_WITNESSES.items():
            if info["type"] not in policy.from_types:
                continue
            if info["avg_latency_ms"] > policy.max_latency_ms:
                continue
            if policy.require_append_only and not info["append_only"]:
                continue
            if policy.require_auditable and not info["independently_auditable"]:
                continue
            candidates.append({"id": wid, **info})
        
        jurisdictions = set(c["jurisdiction"] for c in candidates)
        operators = set(c["operator"] for c in candidates)
        
        satisfiable = (
            len(candidates) >= policy.require and
            len(jurisdictions) >= policy.min_jurisdictions and
            len(operators) >= policy.min_operators
        )
        
        return {
            "satisfiable": satisfiable,
            "candidates": len(candidates),
            "jurisdictions": sorted(jurisdictions),
            "operators": sorted(operators),
            "witnesses": [c["id"] for c in candidates],
        }


def run_scenarios():
    v = WitnessPolicyValidator()
    
    print("=" * 70)
    print("WITNESS_POLICY VALIDATOR — ATF Attestation Witnessing")
    print("=" * 70)
    
    # Scenario 1: Standard policy, good receipts
    print("\n--- Scenario 1: VALID (standard policy, diverse witnesses) ---")
    policy1 = WitnessPolicy(require=2, from_types=["rekor", "rfc3161", "ct"], min_jurisdictions=2)
    receipts1 = [
        WitnessReceipt("sigstore-rekor", "rekor", "sigstore-project", "US", "2026-03-27T00:00:00Z", 180),
        WitnessReceipt("freetsa-org", "rfc3161", "freetsa", "DE", "2026-03-27T00:00:01Z", 450),
    ]
    r = v.validate(policy1, receipts1)
    print(f"  Valid: {r.valid} | Accepted: {r.receipts_accepted}/{r.receipts_provided}")
    print(f"  Threshold: {r.threshold_met} | Jurisdictions: {r.jurisdiction_diversity_met} | Operators: {r.operator_diversity_met}")
    
    # Scenario 2: Same jurisdiction = fails diversity
    print("\n--- Scenario 2: INVALID (same jurisdiction) ---")
    receipts2 = [
        WitnessReceipt("sigstore-rekor", "rekor", "sigstore-project", "US", "2026-03-27T00:00:00Z", 180),
        WitnessReceipt("google-argon", "ct", "google", "US", "2026-03-27T00:00:01Z", 140),
        WitnessReceipt("digicert-nessie", "ct", "digicert", "US", "2026-03-27T00:00:02Z", 175),
    ]
    r = v.validate(policy1, receipts2)
    print(f"  Valid: {r.valid} | Accepted: {r.receipts_accepted}/{r.receipts_provided}")
    print(f"  Errors: {r.errors}")
    
    # Scenario 3: Latency exceeds policy
    print("\n--- Scenario 3: DEGRADED (high latency witness rejected) ---")
    policy3 = WitnessPolicy(require=2, from_types=["ct", "rfc3161"], max_latency_ms=200, min_jurisdictions=1, min_operators=2)
    receipts3 = [
        WitnessReceipt("google-argon", "ct", "google", "US", "2026-03-27T00:00:00Z", 140),
        WitnessReceipt("freetsa-org", "rfc3161", "freetsa", "DE", "2026-03-27T00:00:01Z", 500),
    ]
    r = v.validate(policy3, receipts3)
    print(f"  Valid: {r.valid} | Accepted: {r.receipts_accepted}/{r.receipts_provided}")
    print(f"  Warnings: {r.warnings}")
    
    # Scenario 4: git witness rejected (not append-only)
    print("\n--- Scenario 4: git witness rejected (not append-only) ---")
    policy4 = WitnessPolicy(require=2, from_types=["rekor", "git", "ct"], min_jurisdictions=1, min_operators=2)
    receipts4 = [
        WitnessReceipt("sigstore-rekor", "rekor", "sigstore-project", "US", "2026-03-27T00:00:00Z", 200),
        WitnessReceipt("github-push", "git", "github", "US", "2026-03-27T00:00:02Z", 900),
    ]
    r = v.validate(policy4, receipts4)
    print(f"  Valid: {r.valid} | Accepted: {r.receipts_accepted}/{r.receipts_provided}")
    print(f"  Warnings: {r.warnings}")
    
    # Find satisfying witnesses for standard policy
    print("\n--- Known witnesses satisfying standard policy ---")
    candidates = v.find_satisfying_witnesses(policy1)
    print(f"  Satisfiable: {candidates['satisfiable']}")
    print(f"  Candidates: {candidates['candidates']} witnesses across {candidates['jurisdictions']} ({candidates['operators']})")
    
    print(f"\n{'=' * 70}")
    print("WITNESS_POLICY = 4 fields. Relying party signs it.")
    print("Witnesses self-select. No enrollment. Market discovers price.")
    print("CT already works this way. Monitoring IS the security.")


if __name__ == "__main__":
    run_scenarios()
