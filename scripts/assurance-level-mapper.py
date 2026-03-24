#!/usr/bin/env python3
"""
assurance-level-mapper.py — FBCA-to-ATF assurance level mapping for cross-registry federation.

Per santaclawd: FBCA has RUDIMENTARY/BASIC/MEDIUM/HIGH.
ATF needs equivalent: PROVISIONAL/ALLEGED/CONFIRMED/VERIFIED.

Cross-registry bridge inherits the LOWER of two registries' assurance floors.
Prevents trust laundering upward.

DNS-SD (RFC 6763) + SRP (RFC 9665, Dec 2024) for discovery.
_atf._tcp.<domain> SRV for endpoint, TXT for policy level.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FBCALevel(Enum):
    """Federal Bridge CA assurance levels."""
    RUDIMENTARY = 1
    BASIC = 2
    MEDIUM = 3
    HIGH = 4


class ATFLevel(Enum):
    """ATF trust assurance levels."""
    PROVISIONAL = 1   # Cold start, n < 5
    ALLEGED = 2       # Building, n < 30 or Wilson CI < 0.7
    CONFIRMED = 3     # Established, n >= 30, Wilson CI >= 0.7
    VERIFIED = 4      # Mature, n >= 100, Wilson CI >= 0.9


# SPEC_CONSTANTS: level requirements
LEVEL_REQUIREMENTS = {
    ATFLevel.PROVISIONAL: {
        "min_receipts": 0,
        "max_receipts": 4,
        "wilson_ci_floor": 0.0,
        "max_delegation_depth": 1,
        "description": "Cold start. TOFU territory."
    },
    ATFLevel.ALLEGED: {
        "min_receipts": 5,
        "max_receipts": 29,
        "wilson_ci_floor": 0.0,
        "max_delegation_depth": 2,
        "description": "Building trust. Wilson CI still wide."
    },
    ATFLevel.CONFIRMED: {
        "min_receipts": 30,
        "max_receipts": 99,
        "wilson_ci_floor": 0.70,
        "max_delegation_depth": 3,
        "description": "Established. CLT kicks in. CI meaningful."
    },
    ATFLevel.VERIFIED: {
        "min_receipts": 100,
        "max_receipts": float('inf'),
        "wilson_ci_floor": 0.90,
        "max_delegation_depth": 4,
        "description": "Mature. Narrow CI. High confidence."
    }
}

# FBCA → ATF mapping
FBCA_TO_ATF = {
    FBCALevel.RUDIMENTARY: ATFLevel.PROVISIONAL,
    FBCALevel.BASIC: ATFLevel.ALLEGED,
    FBCALevel.MEDIUM: ATFLevel.CONFIRMED,
    FBCALevel.HIGH: ATFLevel.VERIFIED,
}


@dataclass
class RegistryProfile:
    registry_id: str
    domain: str
    assurance_level: ATFLevel
    total_agents: int
    avg_receipts_per_agent: float
    avg_wilson_ci: float
    dns_txt_record: str = ""  # _atf._tcp.<domain> TXT
    
    def __post_init__(self):
        if not self.dns_txt_record:
            self.dns_txt_record = (
                f"v=ATF1; level={self.assurance_level.name}; "
                f"agents={self.total_agents}; "
                f"endpoint=https://{self.domain}/api/atf"
            )


@dataclass
class CrossRegistryBridge:
    source: RegistryProfile
    target: RegistryProfile
    bridge_level: ATFLevel = None
    bridge_hash: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0  # TTL
    
    def __post_init__(self):
        if self.bridge_level is None:
            # Bridge inherits LOWER of two floors
            self.bridge_level = ATFLevel(min(
                self.source.assurance_level.value,
                self.target.assurance_level.value
            ))
        if not self.bridge_hash:
            self.bridge_hash = hashlib.sha256(
                f"{self.source.registry_id}:{self.target.registry_id}:{self.bridge_level.name}".encode()
            ).hexdigest()[:16]
        if not self.created_at:
            self.created_at = time.time()
        if not self.expires_at:
            self.expires_at = self.created_at + 86400 * 90  # 90-day TTL


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * ((p * (1 - p) / total + z**2 / (4 * total**2)) ** 0.5)
    return round((center - spread) / denominator, 4)


def classify_agent_level(n_receipts: int, n_confirmed: int) -> dict:
    """Classify an agent's assurance level based on receipt history."""
    wilson = wilson_ci_lower(n_confirmed, n_receipts)
    
    for level in [ATFLevel.VERIFIED, ATFLevel.CONFIRMED, ATFLevel.ALLEGED, ATFLevel.PROVISIONAL]:
        req = LEVEL_REQUIREMENTS[level]
        if n_receipts >= req["min_receipts"] and wilson >= req["wilson_ci_floor"]:
            return {
                "level": level.name,
                "n_receipts": n_receipts,
                "n_confirmed": n_confirmed,
                "wilson_ci_lower": wilson,
                "max_delegation_depth": req["max_delegation_depth"],
                "description": req["description"],
                "next_level": None
            }
    
    return {"level": ATFLevel.PROVISIONAL.name, "n_receipts": n_receipts,
            "wilson_ci_lower": wilson, "description": "Fallback to PROVISIONAL"}


def validate_bridge(bridge: CrossRegistryBridge) -> dict:
    """Validate a cross-registry bridge."""
    issues = []
    
    # Bridge level must be MIN of source and target
    expected = ATFLevel(min(bridge.source.assurance_level.value,
                           bridge.target.assurance_level.value))
    if bridge.bridge_level.value > expected.value:
        issues.append(f"TRUST_LAUNDERING: bridge claims {bridge.bridge_level.name} "
                      f"but MIN(source,target) = {expected.name}")
    
    # Check TTL
    if bridge.expires_at < time.time():
        issues.append("EXPIRED: bridge TTL exceeded")
    
    # Check DNS TXT records
    if not bridge.source.dns_txt_record or not bridge.target.dns_txt_record:
        issues.append("MISSING_DNS: registry must publish _atf TXT record")
    
    return {
        "valid": len(issues) == 0,
        "bridge_level": bridge.bridge_level.name,
        "expected_level": expected.name,
        "source": f"{bridge.source.registry_id} ({bridge.source.assurance_level.name})",
        "target": f"{bridge.target.registry_id} ({bridge.target.assurance_level.name})",
        "issues": issues
    }


# === Scenarios ===

def scenario_honest_bridge():
    """Two registries, different levels, honest bridge."""
    print("=== Scenario: Honest Cross-Registry Bridge ===")
    
    reg_a = RegistryProfile("atf-alpha", "alpha.example.com", ATFLevel.CONFIRMED,
                           total_agents=500, avg_receipts_per_agent=45.0, avg_wilson_ci=0.78)
    reg_b = RegistryProfile("atf-beta", "beta.example.com", ATFLevel.ALLEGED,
                           total_agents=50, avg_receipts_per_agent=12.0, avg_wilson_ci=0.55)
    
    bridge = CrossRegistryBridge(source=reg_a, target=reg_b)
    result = validate_bridge(bridge)
    
    print(f"  Source: {result['source']}")
    print(f"  Target: {result['target']}")
    print(f"  Bridge level: {result['bridge_level']} (expected: {result['expected_level']})")
    print(f"  Valid: {result['valid']}")
    print(f"  DNS TXT (source): {reg_a.dns_txt_record}")
    print()


def scenario_trust_laundering():
    """Attempt to launder PROVISIONAL into CONFIRMED via bridge."""
    print("=== Scenario: Trust Laundering Attempt ===")
    
    reg_trusted = RegistryProfile("atf-trusted", "trusted.example.com", ATFLevel.VERIFIED,
                                 total_agents=2000, avg_receipts_per_agent=150.0, avg_wilson_ci=0.94)
    reg_new = RegistryProfile("atf-new", "new.example.com", ATFLevel.PROVISIONAL,
                             total_agents=3, avg_receipts_per_agent=2.0, avg_wilson_ci=0.0)
    
    # Attacker tries to claim CONFIRMED bridge
    bridge = CrossRegistryBridge(source=reg_trusted, target=reg_new)
    bridge.bridge_level = ATFLevel.CONFIRMED  # Laundering attempt!
    
    result = validate_bridge(bridge)
    print(f"  Source: {result['source']}")
    print(f"  Target: {result['target']}")
    print(f"  Claimed bridge: {result['bridge_level']}")
    print(f"  Expected: {result['expected_level']}")
    print(f"  Valid: {result['valid']}")
    for issue in result['issues']:
        print(f"  ISSUE: {issue}")
    print()


def scenario_agent_progression():
    """Show agent progressing through assurance levels."""
    print("=== Scenario: Agent Level Progression ===")
    
    stages = [
        (0, 0, "Just created"),
        (3, 3, "First receipts"),
        (10, 8, "Building"),
        (30, 25, "CLT threshold"),
        (50, 42, "Established"),
        (100, 92, "Mature"),
        (200, 185, "Veteran"),
    ]
    
    for total, confirmed, desc in stages:
        result = classify_agent_level(total, confirmed)
        print(f"  n={total:3d} confirmed={confirmed:3d} Wilson={result['wilson_ci_lower']:.3f} "
              f"→ {result['level']:12s} depth≤{result.get('max_delegation_depth', '?')}  ({desc})")
    print()


def scenario_fbca_mapping():
    """Map FBCA levels to ATF levels."""
    print("=== Scenario: FBCA → ATF Level Mapping ===")
    for fbca, atf in FBCA_TO_ATF.items():
        req = LEVEL_REQUIREMENTS[atf]
        print(f"  {fbca.name:12s} → {atf.name:12s}  "
              f"(n≥{req['min_receipts']}, Wilson≥{req['wilson_ci_floor']:.1f}, depth≤{req['max_delegation_depth']})")
    print()
    print("  Key: cross-registry bridge inherits LOWER of two floors")
    print("  FBCA MEDIUM ↔ ATF ALLEGED = bridge at ALLEGED")
    print()


if __name__ == "__main__":
    print("Assurance Level Mapper — FBCA-to-ATF Cross-Registry Federation")
    print("Per santaclawd + DNS-SD (RFC 6763) + SRP (RFC 9665)")
    print("=" * 70)
    print()
    scenario_fbca_mapping()
    scenario_honest_bridge()
    scenario_trust_laundering()
    scenario_agent_progression()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("  1. Bridge level = MIN(source, target). No trust laundering.")
    print("  2. DNS TXT for discovery: _atf._tcp.<domain> → endpoint + level")
    print("  3. Wilson CI is the natural gate between levels")
    print("  4. FBCA maps cleanly to ATF (4 levels each)")
    print("  5. Cross-signing ceremony follows SMTP bootstrap")
