#!/usr/bin/env python3
"""
atf-dns-discovery.py — DNS-based registry discovery + FBCA assurance level mapping for ATF.

Per santaclawd: cross-registry discovery gap. How does ATF-A find ATF-B?
Per XMPP federation (XEP-0156): DNS TXT for connection methods, SRV for endpoints.
Per FBCA: four assurance levels with audit requirements.

Discovery flow:
  1. _atf.<domain> TXT → endpoint + assurance_level + policy_url + genesis_hash
  2. DNSSEC validation → SIGNED (trusted) or UNSIGNED (PROVISIONAL only)
  3. SMTP bootstrap → first cross-signing handshake
  4. Cross-signing ceremony → mutual or unidirectional trust

Assurance mapping (FBCA → ATF):
  RUDIMENTARY → F (n<5, no Wilson CI possible)
  BASIC       → D (n≥5, Wilson CI < 0.50)
  MEDIUM      → C (n≥15, Wilson CI ≥ 0.70)
  HIGH        → A (n≥30, Wilson CI ≥ 0.85, 3+ counterparties)
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    RUDIMENTARY = "RUDIMENTARY"  # FBCA Level 1
    BASIC = "BASIC"              # FBCA Level 2
    MEDIUM = "MEDIUM"            # FBCA Level 3
    HIGH = "HIGH"                # FBCA Level 4


class DiscoveryStatus(Enum):
    DISCOVERED = "DISCOVERED"        # TXT found
    VERIFIED = "VERIFIED"            # DNSSEC valid
    PROVISIONAL = "PROVISIONAL"      # No DNSSEC
    BOOTSTRAPPING = "BOOTSTRAPPING"  # SMTP handshake in progress
    FEDERATED = "FEDERATED"          # Cross-signing complete
    FAILED = "FAILED"                # Discovery failed


class DNSSECStatus(Enum):
    SIGNED = "SIGNED"        # DNSSEC validated
    UNSIGNED = "UNSIGNED"    # No DNSSEC
    BOGUS = "BOGUS"          # DNSSEC failed validation


# SPEC_CONSTANTS
ASSURANCE_REQUIREMENTS = {
    AssuranceLevel.RUDIMENTARY: {"min_n": 0, "wilson_floor": 0.0, "min_counterparties": 0, "grade": "F"},
    AssuranceLevel.BASIC:       {"min_n": 5, "wilson_floor": 0.0, "min_counterparties": 1, "grade": "D"},
    AssuranceLevel.MEDIUM:      {"min_n": 15, "wilson_floor": 0.70, "min_counterparties": 2, "grade": "C"},
    AssuranceLevel.HIGH:        {"min_n": 30, "wilson_floor": 0.85, "min_counterparties": 3, "grade": "A"},
}

TXT_REQUIRED_FIELDS = ["endpoint", "assurance_level", "policy_url", "genesis_hash"]
DISCOVERY_TTL_HOURS = 24
BOOTSTRAP_TIMEOUT_HOURS = 72


@dataclass
class ATFTxtRecord:
    """Represents _atf.<domain> TXT record content."""
    domain: str
    endpoint: str
    assurance_level: AssuranceLevel
    policy_url: str
    genesis_hash: str
    schema_version: str = "1.0"
    dnssec_status: DNSSECStatus = DNSSECStatus.UNSIGNED
    discovered_at: float = 0.0
    
    def to_txt(self) -> str:
        """Generate DNS TXT record value."""
        return (f"v=ATF1; endpoint={self.endpoint}; "
                f"assurance={self.assurance_level.value}; "
                f"policy={self.policy_url}; "
                f"genesis={self.genesis_hash[:16]}")

    def validate(self) -> dict:
        issues = []
        if not self.endpoint.startswith("https://"):
            issues.append("endpoint MUST be HTTPS")
        if not self.genesis_hash or len(self.genesis_hash) < 16:
            issues.append("genesis_hash MUST be ≥16 chars")
        if not self.policy_url:
            issues.append("policy_url REQUIRED")
        return {"valid": len(issues) == 0, "issues": issues}


@dataclass
class RegistryProfile:
    """ATF registry with assurance metrics."""
    domain: str
    assurance_level: AssuranceLevel
    n_receipts: int
    wilson_ci_lower: float
    n_counterparties: int
    genesis_hash: str
    txt_record: Optional[ATFTxtRecord] = None


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1-p) + z**2 / (4*total)) / total)
    return max(0, (centre - spread) / denominator)


def map_assurance_level(n_receipts: int, wilson_lower: float, n_counterparties: int) -> AssuranceLevel:
    """Map receipt statistics to FBCA assurance level."""
    for level in reversed(list(AssuranceLevel)):
        req = ASSURANCE_REQUIREMENTS[level]
        if (n_receipts >= req["min_n"] and 
            wilson_lower >= req["wilson_floor"] and
            n_counterparties >= req["min_counterparties"]):
            return level
    return AssuranceLevel.RUDIMENTARY


def discover_registry(txt: ATFTxtRecord) -> dict:
    """Simulate registry discovery via DNS TXT."""
    validation = txt.validate()
    
    if not validation["valid"]:
        return {
            "status": DiscoveryStatus.FAILED.value,
            "domain": txt.domain,
            "issues": validation["issues"]
        }
    
    # DNSSEC check determines trust level
    if txt.dnssec_status == DNSSECStatus.BOGUS:
        return {
            "status": DiscoveryStatus.FAILED.value,
            "domain": txt.domain,
            "issues": ["DNSSEC validation FAILED — possible tampering"]
        }
    
    discovery_status = (DiscoveryStatus.VERIFIED if txt.dnssec_status == DNSSECStatus.SIGNED 
                       else DiscoveryStatus.PROVISIONAL)
    
    return {
        "status": discovery_status.value,
        "domain": txt.domain,
        "txt_record": txt.to_txt(),
        "dnssec": txt.dnssec_status.value,
        "assurance_declared": txt.assurance_level.value,
        "trust_note": ("DNSSEC-validated: discovery trusted" if discovery_status == DiscoveryStatus.VERIFIED
                      else "No DNSSEC: discovery PROVISIONAL only — verify via SMTP bootstrap")
    }


def cross_registry_bridge(registry_a: RegistryProfile, registry_b: RegistryProfile) -> dict:
    """
    Evaluate cross-registry federation.
    Bridge inherits LOWER of two assurance floors (prevents trust laundering).
    """
    level_order = list(AssuranceLevel)
    a_idx = level_order.index(registry_a.assurance_level)
    b_idx = level_order.index(registry_b.assurance_level)
    bridge_level = level_order[min(a_idx, b_idx)]
    
    bridge_grade = ASSURANCE_REQUIREMENTS[bridge_level]["grade"]
    
    return {
        "registry_a": {"domain": registry_a.domain, "assurance": registry_a.assurance_level.value,
                       "n": registry_a.n_receipts, "wilson": registry_a.wilson_ci_lower},
        "registry_b": {"domain": registry_b.domain, "assurance": registry_b.assurance_level.value,
                       "n": registry_b.n_receipts, "wilson": registry_b.wilson_ci_lower},
        "bridge_assurance": bridge_level.value,
        "bridge_grade": bridge_grade,
        "trust_laundering": registry_a.assurance_level != registry_b.assurance_level,
        "note": (f"Bridge inherits {bridge_level.value} (lower of {registry_a.assurance_level.value} "
                f"and {registry_b.assurance_level.value})")
    }


def n_recovery_assessment(profile: RegistryProfile, recovery_reason: str) -> dict:
    """
    Assess recovery requirements after SUSPENDED state.
    n_recovery < n_cold_start (TLS session resumption model).
    """
    N_COLD_START = 30
    N_RECOVERY = 10
    MIN_COUNTERPARTIES_RECOVERY = 2  # vs 3 for cold start
    RECOVERY_WINDOW_HOURS = 48
    
    full_reattestion_reasons = {"axiom_violation", "grader_rotation", "emergency_exit"}
    needs_full = recovery_reason in full_reattestion_reasons
    
    if needs_full:
        return {
            "recovery_type": "FULL_RE_ATTESTATION",
            "reason": recovery_reason,
            "n_required": N_COLD_START,
            "counterparties_required": 3,
            "window_hours": None,
            "note": "Full re-attestation required — cannot use abbreviated recovery"
        }
    
    return {
        "recovery_type": "ABBREVIATED_RECOVERY",
        "reason": recovery_reason,
        "n_required": N_RECOVERY,
        "counterparties_required": MIN_COUNTERPARTIES_RECOVERY,
        "window_hours": RECOVERY_WINDOW_HOURS,
        "wilson_ceiling_at_n10": round(wilson_ci_lower(10, 10), 3),
        "note": f"TLS session resumption model — {N_RECOVERY} receipts from {MIN_COUNTERPARTIES_RECOVERY}+ counterparties in {RECOVERY_WINDOW_HOURS}h"
    }


# === Scenarios ===

def scenario_dns_discovery():
    """Registry discovery via DNS TXT."""
    print("=== Scenario: DNS Registry Discovery ===")
    
    # DNSSEC-signed registry
    txt_signed = ATFTxtRecord(
        domain="atf-alpha.example.com",
        endpoint="https://atf-alpha.example.com/api/v1",
        assurance_level=AssuranceLevel.HIGH,
        policy_url="https://atf-alpha.example.com/policy",
        genesis_hash="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        dnssec_status=DNSSECStatus.SIGNED
    )
    result = discover_registry(txt_signed)
    print(f"  {result['domain']}: {result['status']}")
    print(f"  TXT: {result['txt_record']}")
    print(f"  DNSSEC: {result['dnssec']} — {result['trust_note']}")
    print()
    
    # Unsigned registry
    txt_unsigned = ATFTxtRecord(
        domain="atf-beta.example.org",
        endpoint="https://atf-beta.example.org/api",
        assurance_level=AssuranceLevel.MEDIUM,
        policy_url="https://atf-beta.example.org/policy",
        genesis_hash="f1e2d3c4b5a6f7e8d9c0b1a2f3e4d5c6",
        dnssec_status=DNSSECStatus.UNSIGNED
    )
    result = discover_registry(txt_unsigned)
    print(f"  {result['domain']}: {result['status']}")
    print(f"  DNSSEC: {result['dnssec']} — {result['trust_note']}")
    print()
    
    # Bogus DNSSEC — tampered
    txt_bogus = ATFTxtRecord(
        domain="atf-evil.example.net",
        endpoint="https://atf-evil.example.net/api",
        assurance_level=AssuranceLevel.HIGH,
        policy_url="https://atf-evil.example.net/policy",
        genesis_hash="0000000000000000",
        dnssec_status=DNSSECStatus.BOGUS
    )
    result = discover_registry(txt_bogus)
    print(f"  {result['domain']}: {result['status']}")
    print(f"  Issues: {result.get('issues', [])}")
    print()


def scenario_assurance_mapping():
    """FBCA assurance level mapping from receipt statistics."""
    print("=== Scenario: FBCA Assurance Level Mapping ===")
    
    cases = [
        ("new_agent", 3, 3, 1),       # 3 receipts, all good, 1 counterparty
        ("growing_agent", 12, 10, 2),  # 12 receipts, 10 good, 2 counterparties
        ("established", 25, 22, 3),    # 25 receipts, 22 good, 3 counterparties
        ("trusted", 50, 47, 5),        # 50 receipts, 47 good, 5 counterparties
        ("sybil", 30, 30, 1),          # 30 perfect receipts, 1 counterparty (sybil!)
    ]
    
    for name, total, success, cps in cases:
        wilson = wilson_ci_lower(success, total)
        level = map_assurance_level(total, wilson, cps)
        grade = ASSURANCE_REQUIREMENTS[level]["grade"]
        print(f"  {name}: n={total} wilson={wilson:.3f} counterparties={cps} → {level.value} (Grade {grade})")
    print()


def scenario_cross_registry_bridge():
    """Cross-registry federation with trust laundering prevention."""
    print("=== Scenario: Cross-Registry Bridge ===")
    
    reg_a = RegistryProfile("atf-alpha.com", AssuranceLevel.HIGH, 100, 0.92, 8, "hash_a")
    reg_b = RegistryProfile("atf-beta.org", AssuranceLevel.BASIC, 8, 0.35, 1, "hash_b")
    
    bridge = cross_registry_bridge(reg_a, reg_b)
    print(f"  {bridge['registry_a']['domain']} ({bridge['registry_a']['assurance']}) ↔ "
          f"{bridge['registry_b']['domain']} ({bridge['registry_b']['assurance']})")
    print(f"  Bridge: {bridge['bridge_assurance']} (Grade {bridge['bridge_grade']})")
    print(f"  Trust laundering prevented: {bridge['trust_laundering']}")
    print(f"  {bridge['note']}")
    print()
    
    # Two HIGH registries
    reg_c = RegistryProfile("atf-gamma.io", AssuranceLevel.HIGH, 200, 0.95, 12, "hash_c")
    bridge2 = cross_registry_bridge(reg_a, reg_c)
    print(f"  {bridge2['registry_a']['domain']} ({bridge2['registry_a']['assurance']}) ↔ "
          f"{bridge2['registry_b']['domain']} ({bridge2['registry_b']['assurance']})")
    print(f"  Bridge: {bridge2['bridge_assurance']} (Grade {bridge2['bridge_grade']})")
    print()


def scenario_recovery_paths():
    """n_recovery vs full re-attestation."""
    print("=== Scenario: Recovery Paths ===")
    
    reasons = ["scope_hash_mutation", "timeout_expiry", "axiom_violation", "grader_rotation", "network_partition"]
    for reason in reasons:
        result = n_recovery_assessment(
            RegistryProfile("kit_fox.atf", AssuranceLevel.MEDIUM, 45, 0.82, 4, "hash_kit"),
            reason
        )
        print(f"  {reason}: {result['recovery_type']} (n={result['n_required']}, "
              f"counterparties={result['counterparties_required']})")
    print()


if __name__ == "__main__":
    print("ATF DNS Discovery + FBCA Assurance Level Mapping")
    print("Per santaclawd + XMPP XEP-0156 + FBCA (2004)")
    print("=" * 70)
    print()
    
    scenario_dns_discovery()
    scenario_assurance_mapping()
    scenario_cross_registry_bridge()
    scenario_recovery_paths()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. DNS TXT = phonebook (unauthenticated discovery)")
    print("2. DNSSEC = tamper-evident discovery (SIGNED vs PROVISIONAL)")  
    print("3. SMTP = first authenticated handshake")
    print("4. Cross-signing ceremony = treaty (mutual or unidirectional)")
    print("5. Bridge assurance = MIN(both floors) — prevents trust laundering")
    print("6. n_recovery=10 < n_cold_start=30 — TLS resumption model")
