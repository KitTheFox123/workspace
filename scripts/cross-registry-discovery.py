#!/usr/bin/env python3
"""
cross-registry-discovery.py — DNS-based ATF registry discovery + FBCA assurance mapping.

Per santaclawd: ATF V1.2 frontier = cross-registry federation.
FBCA model: discovery ≠ trust. DNS finds who exists. Cross-signing ceremony IS the audit.

Protocol:
  1. DISCOVERY: _atf.<domain> TXT → endpoint + policy level (unauthenticated)
  2. BOOTSTRAP: SMTP handshake → genesis exchange (authenticated) 
  3. CEREMONY: Cross-signing with M-of-N witnesses (audited)

FBCA assurance level mapping:
  FBCA RUDIMENTARY → ATF PROVISIONAL (n<5, Wilson CI<0.57)
  FBCA BASIC       → ATF ALLEGED     (n<30, CI<0.70)
  FBCA MEDIUM      → ATF CONFIRMED   (n≥30, CI≥0.70)
  FBCA HIGH        → ATF VERIFIED    (n≥100, CI≥0.90)

Bridge grade = MIN(both registries). Prevents trust laundering upward.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    PROVISIONAL = "PROVISIONAL"  # FBCA RUDIMENTARY
    ALLEGED = "ALLEGED"          # FBCA BASIC
    CONFIRMED = "CONFIRMED"      # FBCA MEDIUM
    VERIFIED = "VERIFIED"        # FBCA HIGH


class DiscoveryStatus(Enum):
    DISCOVERED = "DISCOVERED"    # TXT record found
    BOOTSTRAPPED = "BOOTSTRAPPED"  # SMTP handshake complete
    CROSS_SIGNED = "CROSS_SIGNED"  # Ceremony complete
    REVOKED = "REVOKED"


# SPEC_CONSTANTS for assurance levels
ASSURANCE_THRESHOLDS = {
    AssuranceLevel.PROVISIONAL: {"min_n": 1, "min_ci": 0.0, "max_depth": 1},
    AssuranceLevel.ALLEGED:     {"min_n": 5, "min_ci": 0.57, "max_depth": 2},
    AssuranceLevel.CONFIRMED:   {"min_n": 30, "min_ci": 0.70, "max_depth": 3},
    AssuranceLevel.VERIFIED:    {"min_n": 100, "min_ci": 0.90, "max_depth": 3},
}

# n_recovery: 30% of original n, minimum 5 (TLS session resumption model)
N_RECOVERY_RATIO = 0.3
N_RECOVERY_MIN = 5


@dataclass
class DNSTXTRecord:
    """_atf.<domain> TXT record format."""
    domain: str
    version: str = "ATF1"
    endpoint: str = ""
    level: AssuranceLevel = AssuranceLevel.PROVISIONAL
    bridge_policy: str = "open"  # open | closed | selective
    contact: str = ""  # SMTP address for bootstrap
    
    def to_txt(self) -> str:
        return (f"v={self.version}; endpoint={self.endpoint}; "
                f"level={self.level.value}; bridge={self.bridge_policy}; "
                f"contact={self.contact}")
    
    @classmethod
    def from_txt(cls, domain: str, txt: str) -> 'DNSTXTRecord':
        parts = {}
        for segment in txt.split(';'):
            if '=' in segment:
                k, v = segment.strip().split('=', 1)
                parts[k.strip()] = v.strip()
        
        level = AssuranceLevel.PROVISIONAL
        for al in AssuranceLevel:
            if al.value == parts.get('level', ''):
                level = al
                break
        
        return cls(
            domain=domain,
            version=parts.get('v', 'ATF1'),
            endpoint=parts.get('endpoint', ''),
            level=level,
            bridge_policy=parts.get('bridge', 'open'),
            contact=parts.get('contact', '')
        )


@dataclass
class Registry:
    registry_id: str
    domain: str
    assurance_level: AssuranceLevel
    n_receipts: int
    wilson_ci_lower: float
    max_delegation_depth: int
    genesis_hash: str
    txt_record: Optional[DNSTXTRecord] = None


@dataclass
class CrossRegistryBridge:
    registry_a: Registry
    registry_b: Registry
    bridge_level: AssuranceLevel  # MIN of both
    status: DiscoveryStatus = DiscoveryStatus.DISCOVERED
    ceremony_hash: Optional[str] = None
    created_at: float = 0.0
    expires_at: float = 0.0
    witnesses: list = field(default_factory=list)


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return round((center - spread) / denominator, 4)


def classify_assurance(n_receipts: int, ci_lower: float) -> AssuranceLevel:
    """Classify registry into FBCA-equivalent assurance level."""
    if n_receipts >= 100 and ci_lower >= 0.90:
        return AssuranceLevel.VERIFIED
    elif n_receipts >= 30 and ci_lower >= 0.70:
        return AssuranceLevel.CONFIRMED
    elif n_receipts >= 5 and ci_lower >= 0.57:
        return AssuranceLevel.ALLEGED
    else:
        return AssuranceLevel.PROVISIONAL


def compute_bridge_level(a: Registry, b: Registry) -> AssuranceLevel:
    """Bridge grade = MIN(both registries). Prevents trust laundering."""
    levels = [AssuranceLevel.PROVISIONAL, AssuranceLevel.ALLEGED, 
              AssuranceLevel.CONFIRMED, AssuranceLevel.VERIFIED]
    a_idx = levels.index(a.assurance_level)
    b_idx = levels.index(b.assurance_level)
    return levels[min(a_idx, b_idx)]


def compute_n_recovery(original_n: int) -> int:
    """
    TLS session resumption model for recovery from DEGRADED.
    30% of original n, minimum 5.
    """
    return max(N_RECOVERY_MIN, math.ceil(original_n * N_RECOVERY_RATIO))


def discover_registry(domain: str, txt_content: str) -> dict:
    """Simulate DNS TXT discovery."""
    record = DNSTXTRecord.from_txt(domain, txt_content)
    return {
        "domain": domain,
        "version": record.version,
        "endpoint": record.endpoint,
        "level": record.level.value,
        "bridge_policy": record.bridge_policy,
        "contact": record.contact,
        "status": "DISCOVERED",
        "note": "DNS TXT is phonebook not treaty. Cross-signing ceremony IS the audit."
    }


def validate_bridge(bridge: CrossRegistryBridge) -> dict:
    """Validate cross-registry bridge constraints."""
    issues = []
    
    # Bridge level must be MIN
    expected = compute_bridge_level(bridge.registry_a, bridge.registry_b)
    if bridge.bridge_level != expected:
        issues.append(f"Bridge level {bridge.bridge_level.value} != MIN({bridge.registry_a.assurance_level.value}, {bridge.registry_b.assurance_level.value}) = {expected.value}")
    
    # Max delegation depth = MIN
    max_depth = min(bridge.registry_a.max_delegation_depth, bridge.registry_b.max_delegation_depth)
    
    # Cross-signed bridges require ceremony
    if bridge.status == DiscoveryStatus.CROSS_SIGNED and not bridge.ceremony_hash:
        issues.append("CROSS_SIGNED bridge requires ceremony_hash")
    
    if bridge.status == DiscoveryStatus.CROSS_SIGNED and len(bridge.witnesses) < 3:
        issues.append(f"CROSS_SIGNED requires 3+ witnesses, got {len(bridge.witnesses)}")
    
    return {
        "valid": len(issues) == 0,
        "bridge_level": expected.value,
        "max_delegation_depth": max_depth,
        "issues": issues,
        "grade": "A" if not issues else "F"
    }


# === Scenarios ===

def scenario_dns_discovery():
    """Discover registry via DNS TXT."""
    print("=== Scenario: DNS TXT Discovery ===")
    
    txt = "v=ATF1; endpoint=https://atf.example.com/api; level=CONFIRMED; bridge=open; contact=admin@example.com"
    result = discover_registry("example.com", txt)
    
    for k, v in result.items():
        print(f"  {k}: {v}")
    print()


def scenario_assurance_mapping():
    """Map FBCA levels to ATF levels."""
    print("=== Scenario: FBCA → ATF Assurance Mapping ===")
    
    cases = [
        ("New agent", 3, 3, 1.0),
        ("Building trust", 15, 14, 0.933),
        ("Established", 50, 47, 0.94),
        ("Verified", 200, 192, 0.96),
        ("Mixed record", 50, 35, 0.70),
        ("Poor record", 30, 18, 0.60),
    ]
    
    for name, total, success, _ in cases:
        ci = wilson_ci_lower(success, total)
        level = classify_assurance(total, ci)
        thresholds = ASSURANCE_THRESHOLDS[level]
        print(f"  {name}: n={total}, success={success}, CI={ci:.3f} → {level.value} "
              f"(min_n={thresholds['min_n']}, min_ci={thresholds['min_ci']}, depth≤{thresholds['max_depth']})")
    print()


def scenario_bridge_grade_min():
    """Bridge inherits lower assurance level."""
    print("=== Scenario: Bridge Grade = MIN ===")
    
    reg_a = Registry("atf-alpha", "alpha.com", AssuranceLevel.VERIFIED, 200, 0.92, 3, "aaa")
    reg_b = Registry("atf-beta", "beta.com", AssuranceLevel.ALLEGED, 12, 0.60, 2, "bbb")
    
    bridge_level = compute_bridge_level(reg_a, reg_b)
    bridge = CrossRegistryBridge(reg_a, reg_b, bridge_level, 
                                  DiscoveryStatus.CROSS_SIGNED,
                                  ceremony_hash="ceremony_abc123",
                                  witnesses=["w1", "w2", "w3"])
    
    validation = validate_bridge(bridge)
    
    print(f"  Registry A: {reg_a.assurance_level.value} (n={reg_a.n_receipts}, CI={reg_a.wilson_ci_lower})")
    print(f"  Registry B: {reg_b.assurance_level.value} (n={reg_b.n_receipts}, CI={reg_b.wilson_ci_lower})")
    print(f"  Bridge level: {bridge_level.value} (= MIN)")
    print(f"  Max depth: {validation['max_delegation_depth']}")
    print(f"  Valid: {validation['valid']}, Grade: {validation['grade']}")
    print(f"  Key: VERIFIED↔ALLEGED bridge = ALLEGED. Prevents trust laundering.")
    print()


def scenario_trust_laundering_blocked():
    """Attempt to launder PROVISIONAL through VERIFIED registry."""
    print("=== Scenario: Trust Laundering Blocked ===")
    
    reg_legit = Registry("atf-legit", "legit.com", AssuranceLevel.VERIFIED, 500, 0.95, 3, "legit")
    reg_shady = Registry("atf-shady", "shady.com", AssuranceLevel.PROVISIONAL, 2, 0.15, 1, "shady")
    
    # Shady tries to bridge with legit to inherit VERIFIED status
    bridge_level = compute_bridge_level(reg_legit, reg_shady)
    
    print(f"  Legit registry: {reg_legit.assurance_level.value}")
    print(f"  Shady registry: {reg_shady.assurance_level.value}")
    print(f"  Bridge level: {bridge_level.value}")
    print(f"  Laundering blocked: shady stays {bridge_level.value} despite bridging with VERIFIED")
    print(f"  FBCA parallel: intermediate CA inherits LOWER of two roots")
    print()


def scenario_n_recovery():
    """TLS session resumption model for DEGRADED recovery."""
    print("=== Scenario: n_recovery (TLS Session Resumption) ===")
    
    cases = [
        ("Small agent", 10),
        ("Medium agent", 30),
        ("Large agent", 100),
        ("Very large", 500),
    ]
    
    for name, original_n in cases:
        recovery = compute_n_recovery(original_n)
        ci_if_perfect = wilson_ci_lower(recovery, recovery)
        print(f"  {name}: original n={original_n} → n_recovery={recovery} "
              f"(if all pass: CI={ci_if_perfect:.3f})")
    
    print(f"\n  Rule: n_recovery = ceil(n * {N_RECOVERY_RATIO}), min {N_RECOVERY_MIN}")
    print(f"  Full re-attestation only on: grader rotation, scope mutation, EMERGENCY exit")
    print()


if __name__ == "__main__":
    print("Cross-Registry Discovery — DNS + FBCA Assurance for ATF V1.2")
    print("Per santaclawd: discovery ≠ trust. DNS finds who exists.")
    print("=" * 70)
    print()
    
    scenario_dns_discovery()
    scenario_assurance_mapping()
    scenario_bridge_grade_min()
    scenario_trust_laundering_blocked()
    scenario_n_recovery()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("  1. _atf.<domain> TXT = DMARC model. Phonebook not treaty.")
    print("  2. Bridge grade = MIN(both registries). Prevents laundering.")
    print("  3. n_recovery = 30% of original (TLS resumption model).")
    print("  4. FBCA 4 levels map cleanly to ATF 4 levels.")
    print("  5. DNS discovers. SMTP bootstraps. Ceremony audits.")
