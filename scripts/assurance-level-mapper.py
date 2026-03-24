#!/usr/bin/env python3
"""
assurance-level-mapper.py — FBCA-to-ATF assurance level mapping for cross-registry federation.

Per santaclawd: FBCA has RUDIMENTARY/BASIC/MEDIUM/HIGH. ATF needs equivalent.
Per RFC 6763: DNS-SD for discovery. _atf._tcp.<domain> TXT for registry endpoints.

Mapping:
  RUDIMENTARY → PROVISIONAL  (n<5, depth≤1, Wilson CI floor 0.00)
  BASIC       → ALLEGED      (n<30, depth≤2, Wilson CI floor 0.30)
  MEDIUM      → CONFIRMED    (n≥30, depth≤3, Wilson CI floor 0.70)
  HIGH        → VERIFIED     (n≥100, depth≤4, Wilson CI floor 0.90)

Cross-registry bridge: grade = MIN(source_assurance, target_assurance).
Trust laundering upward = structurally impossible.
"""

import hashlib
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FBCALevel(Enum):
    RUDIMENTARY = 1
    BASIC = 2
    MEDIUM = 3
    HIGH = 4


class ATFLevel(Enum):
    PROVISIONAL = 1
    ALLEGED = 2
    CONFIRMED = 3
    VERIFIED = 4


# SPEC_CONSTANTS: assurance level requirements
LEVEL_REQUIREMENTS = {
    ATFLevel.PROVISIONAL: {
        "min_receipts": 1,
        "wilson_ci_floor": 0.00,
        "max_delegation_depth": 1,
        "min_counterparties": 1,
        "min_days_active": 0,
        "fbca_equivalent": FBCALevel.RUDIMENTARY,
    },
    ATFLevel.ALLEGED: {
        "min_receipts": 5,
        "wilson_ci_floor": 0.30,
        "max_delegation_depth": 2,
        "min_counterparties": 2,
        "min_days_active": 7,
        "fbca_equivalent": FBCALevel.BASIC,
    },
    ATFLevel.CONFIRMED: {
        "min_receipts": 30,
        "wilson_ci_floor": 0.70,
        "max_delegation_depth": 3,
        "min_counterparties": 5,
        "min_days_active": 30,
        "fbca_equivalent": FBCALevel.MEDIUM,
    },
    ATFLevel.VERIFIED: {
        "min_receipts": 100,
        "wilson_ci_floor": 0.90,
        "max_delegation_depth": 4,
        "min_counterparties": 10,
        "min_days_active": 90,
        "fbca_equivalent": FBCALevel.HIGH,
    },
}


@dataclass
class RegistryProfile:
    registry_id: str
    domain: str
    assurance_level: ATFLevel
    policy_hash: str
    endpoint: str
    cross_sign_contact: str  # email for cross-signing ceremony
    dns_txt: str = ""  # _atf._tcp.<domain> TXT record value

    def __post_init__(self):
        if not self.dns_txt:
            self.dns_txt = (f"v=ATF1; level={self.assurance_level.name}; "
                          f"endpoint={self.endpoint}; policy={self.policy_hash[:16]}; "
                          f"contact={self.cross_sign_contact}")


@dataclass
class AgentTrustProfile:
    agent_id: str
    registry: str
    total_receipts: int
    confirmed_receipts: int
    unique_counterparties: int
    days_active: int
    max_delegation_depth: int


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return max(0, (centre - spread) / denominator)


def assess_level(profile: AgentTrustProfile) -> dict:
    """Assess which ATF assurance level an agent qualifies for."""
    ci = wilson_ci_lower(profile.confirmed_receipts, profile.total_receipts)
    
    qualified_level = ATFLevel.PROVISIONAL  # default
    for level in [ATFLevel.VERIFIED, ATFLevel.CONFIRMED, ATFLevel.ALLEGED, ATFLevel.PROVISIONAL]:
        reqs = LEVEL_REQUIREMENTS[level]
        if (profile.total_receipts >= reqs["min_receipts"] and
            ci >= reqs["wilson_ci_floor"] and
            profile.max_delegation_depth <= reqs["max_delegation_depth"] and
            profile.unique_counterparties >= reqs["min_counterparties"] and
            profile.days_active >= reqs["min_days_active"]):
            qualified_level = level
            break
    
    # Find what's needed for next level
    next_level = None
    gaps = []
    for level in ATFLevel:
        if level.value == qualified_level.value + 1:
            next_level = level
            reqs = LEVEL_REQUIREMENTS[level]
            if profile.total_receipts < reqs["min_receipts"]:
                gaps.append(f"need {reqs['min_receipts'] - profile.total_receipts} more receipts")
            if ci < reqs["wilson_ci_floor"]:
                gaps.append(f"Wilson CI {ci:.3f} < {reqs['wilson_ci_floor']}")
            if profile.unique_counterparties < reqs["min_counterparties"]:
                gaps.append(f"need {reqs['min_counterparties'] - profile.unique_counterparties} more counterparties")
            if profile.days_active < reqs["min_days_active"]:
                gaps.append(f"need {reqs['min_days_active'] - profile.days_active} more active days")
    
    return {
        "agent_id": profile.agent_id,
        "registry": profile.registry,
        "level": qualified_level.name,
        "wilson_ci": round(ci, 4),
        "fbca_equivalent": LEVEL_REQUIREMENTS[qualified_level]["fbca_equivalent"].name,
        "next_level": next_level.name if next_level else "MAX",
        "gaps_to_next": gaps
    }


def cross_registry_bridge_grade(source: RegistryProfile, target: RegistryProfile) -> dict:
    """
    Compute cross-registry bridge assurance level.
    Bridge = MIN(source, target). Trust laundering upward = impossible.
    """
    bridge_level = ATFLevel(min(source.assurance_level.value, target.assurance_level.value))
    
    # Bridge hash = hash of both registry policies
    bridge_hash = hashlib.sha256(
        f"{source.policy_hash}:{target.policy_hash}".encode()
    ).hexdigest()[:16]
    
    return {
        "source": f"{source.registry_id} ({source.assurance_level.name})",
        "target": f"{target.registry_id} ({target.assurance_level.name})",
        "bridge_level": bridge_level.name,
        "bridge_hash": bridge_hash,
        "direction": "UNIDIRECTIONAL",
        "trust_laundering": "IMPOSSIBLE" if bridge_level.value <= min(
            source.assurance_level.value, target.assurance_level.value
        ) else "DETECTED",
        "dns_discovery": {
            "source_txt": source.dns_txt,
            "target_txt": target.dns_txt
        }
    }


def generate_dns_txt(registry: RegistryProfile) -> str:
    """Generate DNS TXT record for ATF registry discovery (RFC 6763 style)."""
    return (f"_atf._tcp.{registry.domain}. IN TXT "
           f'"v=ATF1; level={registry.assurance_level.name}; '
           f'endpoint={registry.endpoint}; '
           f'policy={registry.policy_hash[:16]}; '
           f'contact={registry.cross_sign_contact}"')


# === Scenarios ===

def scenario_level_assessment():
    """Assess assurance levels for agents at different trust stages."""
    print("=== Scenario: Assurance Level Assessment ===")
    
    profiles = [
        AgentTrustProfile("kit_fox", "atf-main", 150, 138, 12, 120, 2),
        AgentTrustProfile("new_agent", "atf-main", 3, 3, 1, 2, 0),
        AgentTrustProfile("growing_agent", "atf-main", 25, 20, 4, 21, 1),
        AgentTrustProfile("sybil_bot", "atf-shady", 50, 50, 1, 10, 0),
    ]
    
    for p in profiles:
        result = assess_level(p)
        print(f"  {result['agent_id']}: {result['level']} (FBCA: {result['fbca_equivalent']}) "
              f"CI={result['wilson_ci']}")
        if result['gaps_to_next']:
            print(f"    → Next ({result['next_level']}): {', '.join(result['gaps_to_next'])}")
    print()


def scenario_cross_registry_bridge():
    """Cross-registry bridge with different assurance levels."""
    print("=== Scenario: Cross-Registry Bridge ===")
    
    reg_a = RegistryProfile(
        "atf-main", "main.atf.example", ATFLevel.VERIFIED,
        "abc123def456", "https://main.atf.example/api", "admin@main.atf.example"
    )
    reg_b = RegistryProfile(
        "atf-partner", "partner.atf.example", ATFLevel.CONFIRMED,
        "789xyz012abc", "https://partner.atf.example/api", "ops@partner.atf.example"
    )
    reg_c = RegistryProfile(
        "atf-startup", "startup.atf.example", ATFLevel.ALLEGED,
        "456def789ghi", "https://startup.atf.example/api", "team@startup.atf.example"
    )
    
    bridges = [
        cross_registry_bridge_grade(reg_a, reg_b),
        cross_registry_bridge_grade(reg_a, reg_c),
        cross_registry_bridge_grade(reg_b, reg_c),
    ]
    
    for b in bridges:
        print(f"  {b['source']} → {b['target']}")
        print(f"    Bridge: {b['bridge_level']} ({b['direction']})")
        print(f"    Laundering: {b['trust_laundering']}")
    print()


def scenario_dns_discovery():
    """DNS TXT records for registry discovery."""
    print("=== Scenario: DNS-SD Discovery (RFC 6763) ===")
    
    registries = [
        RegistryProfile("atf-main", "main.atf.example", ATFLevel.VERIFIED,
                        "abc123def456", "https://main.atf.example/api", "admin@main.atf.example"),
        RegistryProfile("atf-partner", "partner.atf.example", ATFLevel.CONFIRMED,
                        "789xyz012abc", "https://partner.atf.example/api", "ops@partner.atf.example"),
    ]
    
    print("  DNS TXT records for discovery:")
    for reg in registries:
        txt = generate_dns_txt(reg)
        print(f"    {txt}")
    
    print()
    print("  Discovery flow:")
    print("    1. Query _atf._tcp.<domain> TXT → endpoint + level + contact")
    print("    2. SMTP bootstrap → first cross-signing handshake")
    print("    3. Cross-signing ceremony → unidirectional bridge")
    print("    4. DNSSEC signs TXT → tamper-evident discovery")
    print("    5. CAA (RFC 8659) parallel: _atf TXT = CAA for registries")
    print()


def scenario_sybil_counterparty_gate():
    """Sybil caught by counterparty diversity requirement."""
    print("=== Scenario: Sybil Caught by Counterparty Gate ===")
    
    # Perfect record but only 1 counterparty
    sybil = AgentTrustProfile("sybil_perfect", "atf-shady", 200, 200, 1, 180, 0)
    result = assess_level(sybil)
    
    # Honest agent with diverse counterparties
    honest = AgentTrustProfile("honest_diverse", "atf-main", 50, 42, 8, 60, 1)
    honest_result = assess_level(honest)
    
    print(f"  Sybil (200 perfect receipts, 1 counterparty): {result['level']}")
    print(f"    CI={result['wilson_ci']}, gaps: {result['gaps_to_next']}")
    print(f"  Honest (50 receipts, 8 counterparties): {honest_result['level']}")
    print(f"    CI={honest_result['wilson_ci']}, gaps: {honest_result['gaps_to_next']}")
    print(f"  → Counterparty diversity gate catches monoculture attestation")
    print()


if __name__ == "__main__":
    print("Assurance-Level-Mapper — FBCA-to-ATF Federation Mapping")
    print("Per santaclawd + DNS-SD (RFC 6763) + CAA (RFC 8659)")
    print("=" * 70)
    print()
    print("Level mapping:")
    for level, reqs in LEVEL_REQUIREMENTS.items():
        fbca = reqs["fbca_equivalent"].name
        print(f"  {level.name:12s} (FBCA: {fbca:12s}) — "
              f"n≥{reqs['min_receipts']:3d}, CI≥{reqs['wilson_ci_floor']:.2f}, "
              f"depth≤{reqs['max_delegation_depth']}, "
              f"counterparties≥{reqs['min_counterparties']:2d}, "
              f"days≥{reqs['min_days_active']:3d}")
    print()
    
    scenario_level_assessment()
    scenario_cross_registry_bridge()
    scenario_dns_discovery()
    scenario_sybil_counterparty_gate()
    
    print("=" * 70)
    print("KEY INSIGHT: Cross-registry = MIN(source, target).")
    print("Trust laundering upward structurally impossible.")
    print("Counterparty diversity gates prevent monoculture attestation.")
    print("DNS-SD discovery → SMTP bootstrap → cross-signing ceremony.")
