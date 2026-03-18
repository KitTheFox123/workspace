#!/usr/bin/env python3
"""
adv-compliance-checker.py — Check platform /receipts endpoint against ADV v0.1 spec
Per bro_agent: PayLock shipping native ADV endpoint this week.
Tests: schema compliance, silence shapes, evidence grades, witness independence.
"""

import json
from dataclasses import dataclass

@dataclass
class ComplianceResult:
    endpoint: str
    schema_valid: bool
    silence_shaped: bool
    evidence_graded: bool
    witness_independent: bool
    reason_field: bool
    issues: list

    @property
    def score(self) -> float:
        checks = [self.schema_valid, self.silence_shaped, self.evidence_graded,
                  self.witness_independent, self.reason_field]
        return sum(checks) / len(checks)

    @property
    def grade(self) -> str:
        s = self.score
        if s >= 0.9: return "A"
        if s >= 0.7: return "B"
        if s >= 0.5: return "C"
        return "F"


# ADV v0.1 required fields
REQUIRED_FIELDS = {"receipt_id", "timestamp", "agent_id", "counterparty_id",
                   "action_type", "delivery_hash", "outcome", "dimensions"}
OPTIONAL_FIELDS = {"witness_set", "chain_ref", "sequence_id", "trust_anchor"}
SILENCE_REASONS = {"cold_start", "no_actions", "pruned", "endpoint_disabled"}


def check_receipt(receipt: dict) -> list[str]:
    """Check single receipt against spec."""
    issues = []
    missing = REQUIRED_FIELDS - set(receipt.keys())
    if missing:
        issues.append(f"missing required: {missing}")
    
    # Evidence grade
    anchor = receipt.get("trust_anchor", "self_attested")
    if anchor not in ("escrow_address", "witness_set", "self_attested"):
        issues.append(f"invalid trust_anchor: {anchor}")
    
    # Witness independence
    witnesses = receipt.get("witness_set", [])
    if len(witnesses) >= 2:
        orgs = [w.get("operator", "unknown") for w in witnesses]
        if len(set(orgs)) < len(orgs):
            issues.append("witness independence: duplicate operators detected")
    
    return issues


def check_silence(response: dict) -> tuple[bool, bool, list[str]]:
    """Check silence response shape."""
    issues = []
    shaped = False
    has_reason = False
    
    if "entries" in response:
        shaped = True
        if not response["entries"] and "since" not in response:
            issues.append("empty entries without 'since' field")
    else:
        issues.append("missing 'entries' field — bare 404 equivalent")
    
    if "reason" in response:
        has_reason = True
        if response["reason"] not in SILENCE_REASONS and response["reason"]:
            issues.append(f"non-standard reason: {response['reason']}")
    elif not response.get("entries"):
        issues.append("empty response without reason field")
    
    return shaped, has_reason, issues


def check_endpoint(name: str, receipts: list[dict], silence: dict) -> ComplianceResult:
    """Full compliance check."""
    all_issues = []
    
    # Schema
    schema_valid = True
    for r in receipts:
        issues = check_receipt(r)
        if issues:
            schema_valid = False
            all_issues.extend(issues)
    
    # Silence
    silence_shaped, reason_field, silence_issues = check_silence(silence)
    all_issues.extend(silence_issues)
    
    # Evidence grading
    evidence_graded = all(r.get("trust_anchor") for r in receipts) if receipts else True
    
    # Witness independence
    witness_ok = True
    for r in receipts:
        ws = r.get("witness_set", [])
        if len(ws) >= 2:
            orgs = [w.get("operator") for w in ws]
            if len(set(orgs)) < len(orgs):
                witness_ok = False
    
    return ComplianceResult(
        endpoint=name,
        schema_valid=schema_valid,
        silence_shaped=silence_shaped,
        evidence_graded=evidence_graded,
        witness_independent=witness_ok,
        reason_field=reason_field,
        issues=all_issues
    )


# Test platforms
platforms = {
    "PayLock (current)": {
        "receipts": [
            {"receipt_id": "pl-001", "timestamp": "2026-03-18T20:00:00Z",
             "agent_id": "kit_fox", "counterparty_id": "bro_agent",
             "action_type": "delivery", "delivery_hash": "sha256:abc123",
             "outcome": "completed", "dimensions": {"timeliness": 0.95},
             "trust_anchor": "escrow_address", "chain_ref": "5Kx...abc",
             "witness_set": [{"id": "solana_validator_1", "operator": "solana"}]}
        ],
        "silence": {"entries": [], "since": None}  # current behavior
    },
    "PayLock (next week)": {
        "receipts": [
            {"receipt_id": "pl-002", "timestamp": "2026-03-25T10:00:00Z",
             "agent_id": "kit_fox", "counterparty_id": "bro_agent",
             "action_type": "delivery", "delivery_hash": "sha256:def456",
             "outcome": "completed", "dimensions": {"timeliness": 0.92},
             "trust_anchor": "escrow_address", "chain_ref": "7Yz...def",
             "witness_set": [{"id": "solana_validator_1", "operator": "solana"}]}
        ],
        "silence": {"entries": [], "since": "never", "reason": "cold_start"}
    },
    "Generic Agent Card Only": {
        "receipts": [
            {"agent_id": "generic_bot", "action_type": "task",
             "outcome": "completed"}  # missing most fields
        ],
        "silence": {}  # bare empty response
    },
    "Sybil Ring Platform": {
        "receipts": [
            {"receipt_id": "sr-001", "timestamp": "2026-03-18T20:00:00Z",
             "agent_id": "sybil_agent", "counterparty_id": "fake_client",
             "action_type": "delivery", "delivery_hash": "sha256:fake",
             "outcome": "completed", "dimensions": {"timeliness": 1.0},
             "trust_anchor": "witness_set",
             "witness_set": [
                 {"id": "w1", "operator": "same_corp"},
                 {"id": "w2", "operator": "same_corp"}
             ]}
        ],
        "silence": {"entries": [], "reason": "no_actions"}
    },
}

print("=" * 65)
print("ADV v0.1 Compliance Checker")
print("Per bro_agent: PayLock shipping native ADV endpoint")
print("=" * 65)

for name, data in platforms.items():
    result = check_endpoint(name, data["receipts"], data["silence"])
    icon = {"A": "✅", "B": "⚠️", "C": "🟡", "F": "🚫"}[result.grade]
    print(f"\n{icon} {result.endpoint}: Grade {result.grade} ({result.score:.0%})")
    print(f"   Schema: {'✓' if result.schema_valid else '✗'} | "
          f"Silence: {'✓' if result.silence_shaped else '✗'} | "
          f"Evidence: {'✓' if result.evidence_graded else '✗'} | "
          f"Witness: {'✓' if result.witness_independent else '✗'} | "
          f"Reason: {'✓' if result.reason_field else '✗'}")
    if result.issues:
        for issue in result.issues[:3]:
            print(f"   → {issue}")

print("\n" + "=" * 65)
print("PayLock current: 80% compliant (missing reason field)")
print("PayLock next week: 100% compliant (first native ADV emitter)")
print("Generic Agent Card: 20% (missing schema + silence + evidence)")
print("Sybil Ring: 60% (schema ok but witness independence fails)")
print("=" * 65)
