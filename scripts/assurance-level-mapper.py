#!/usr/bin/env python3
"""
assurance-level-mapper.py — FBCA-to-ATF assurance level mapping for cross-registry federation.

Per santaclawd: FBCA has RUDIMENTARY/BASIC/MEDIUM/HIGH.
ATF needs equivalent: PROVISIONAL/ALLEGED/CONFIRMED/VERIFIED.
Cross-registry bridge = MIN(source, target). Prevents trust laundering.

Discovery: _atf.<domain> DNS TXT → endpoint + assurance level.
Bootstrap: SMTP first contact → cross-signing ceremony.
Federation: bridge grade = MIN(both registries).

Key insight (FBCA, NIST SP 800-63): assurance is NOT transitive.
A↔Bridge↔B does NOT mean A trusts B. Mutual recognition ≠ transitive trust.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AssuranceLevel(Enum):
    PROVISIONAL = 1    # FBCA RUDIMENTARY: n<10, Wilson<0.50
    ALLEGED = 2        # FBCA BASIC: n<30, Wilson<0.70
    CONFIRMED = 3      # FBCA MEDIUM: n≥30, Wilson≥0.70
    VERIFIED = 4       # FBCA HIGH: n≥50, Wilson≥0.85


# SPEC_CONSTANTS: assurance level requirements
LEVEL_REQUIREMENTS = {
    AssuranceLevel.PROVISIONAL: {"min_n": 1, "min_wilson": 0.0, "max_delegation": 4, "min_days": 0},
    AssuranceLevel.ALLEGED: {"min_n": 10, "min_wilson": 0.50, "max_delegation": 3, "min_days": 7},
    AssuranceLevel.CONFIRMED: {"min_n": 30, "min_wilson": 0.70, "max_delegation": 2, "min_days": 30},
    AssuranceLevel.VERIFIED: {"min_n": 50, "min_wilson": 0.85, "max_delegation": 1, "min_days": 90},
}

# FBCA mapping
FBCA_MAP = {
    "RUDIMENTARY": AssuranceLevel.PROVISIONAL,
    "BASIC": AssuranceLevel.ALLEGED,
    "MEDIUM": AssuranceLevel.CONFIRMED,
    "HIGH": AssuranceLevel.VERIFIED,
}


@dataclass
class Registry:
    registry_id: str
    domain: str
    assurance_level: AssuranceLevel
    dns_txt: str = ""  # _atf.domain TXT record
    endpoint: str = ""
    genesis_hash: str = ""
    
    def __post_init__(self):
        if not self.dns_txt:
            self.dns_txt = f"v=ATF1; level={self.assurance_level.name}; endpoint={self.endpoint}"
        if not self.genesis_hash:
            self.genesis_hash = hashlib.sha256(
                f"{self.registry_id}:{self.domain}".encode()
            ).hexdigest()[:16]


@dataclass
class Agent:
    agent_id: str
    registry: str  # registry_id
    n_receipts: int
    wilson_ci_lower: float
    delegation_depth: int
    active_days: int


@dataclass
class CrossRegistryBridge:
    source_registry: Registry
    target_registry: Registry
    bridge_level: AssuranceLevel
    direction: str  # "unidirectional" or "bidirectional"
    created_at: float = 0.0
    expires_at: float = 0.0
    ceremony_hash: str = ""


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    spread = z * (p * (1 - p) / total + z**2 / (4 * total**2))**0.5 / denominator
    return max(0, round(center - spread, 4))


def classify_assurance(agent: Agent) -> AssuranceLevel:
    """Classify agent's assurance level based on receipt history."""
    for level in reversed(AssuranceLevel):
        req = LEVEL_REQUIREMENTS[level]
        if (agent.n_receipts >= req["min_n"] and
            agent.wilson_ci_lower >= req["min_wilson"] and
            agent.delegation_depth <= req["max_delegation"] and
            agent.active_days >= req["min_days"]):
            return level
    return AssuranceLevel.PROVISIONAL


def compute_bridge_level(source: Registry, target: Registry) -> AssuranceLevel:
    """Bridge assurance = MIN(source, target). Prevents trust laundering."""
    return AssuranceLevel(min(source.assurance_level.value, target.assurance_level.value))


def validate_cross_registry_agent(agent: Agent, source: Registry, target: Registry) -> dict:
    """Validate agent trust across registries via bridge."""
    agent_level = classify_assurance(agent)
    bridge_level = compute_bridge_level(source, target)
    
    # Effective level = MIN(agent_level, bridge_level)
    effective = AssuranceLevel(min(agent_level.value, bridge_level.value))
    
    # Trust laundering detection
    laundering = agent_level.value > bridge_level.value
    
    return {
        "agent_id": agent.agent_id,
        "agent_level": agent_level.name,
        "bridge_level": bridge_level.name,
        "effective_level": effective.name,
        "trust_laundering_detected": laundering,
        "source_registry": source.registry_id,
        "target_registry": target.registry_id,
        "requirements_met": {
            level.name: {
                "n_receipts": agent.n_receipts >= LEVEL_REQUIREMENTS[level]["min_n"],
                "wilson_ci": agent.wilson_ci_lower >= LEVEL_REQUIREMENTS[level]["min_wilson"],
                "delegation": agent.delegation_depth <= LEVEL_REQUIREMENTS[level]["max_delegation"],
                "days": agent.active_days >= LEVEL_REQUIREMENTS[level]["min_days"],
            }
            for level in AssuranceLevel
        }
    }


def generate_dns_txt(registry: Registry) -> str:
    """Generate DNS TXT record for registry discovery."""
    return (f"_atf.{registry.domain}. IN TXT "
            f"\"v=ATF1; level={registry.assurance_level.name}; "
            f"endpoint={registry.endpoint}; "
            f"genesis={registry.genesis_hash}\"")


# === Scenarios ===

def scenario_matched_levels():
    """Two CONFIRMED registries — bridge = CONFIRMED."""
    print("=== Scenario: Matched Levels (CONFIRMED ↔ CONFIRMED) ===")
    
    reg_a = Registry("atf_alpha", "alpha.example", AssuranceLevel.CONFIRMED,
                     endpoint="https://alpha.example/atf")
    reg_b = Registry("atf_beta", "beta.example", AssuranceLevel.CONFIRMED,
                     endpoint="https://beta.example/atf")
    
    agent = Agent("kit_fox", "atf_alpha", n_receipts=47, wilson_ci_lower=0.82,
                  delegation_depth=1, active_days=120)
    
    result = validate_cross_registry_agent(agent, reg_a, reg_b)
    bridge = compute_bridge_level(reg_a, reg_b)
    
    print(f"  Agent: {result['agent_level']}, Bridge: {result['bridge_level']}")
    print(f"  Effective: {result['effective_level']}")
    print(f"  Laundering: {result['trust_laundering_detected']}")
    print(f"  DNS: {generate_dns_txt(reg_a)}")
    print()


def scenario_trust_laundering():
    """VERIFIED agent through ALLEGED bridge — capped."""
    print("=== Scenario: Trust Laundering Attempt ===")
    
    reg_high = Registry("atf_premium", "premium.example", AssuranceLevel.VERIFIED,
                        endpoint="https://premium.example/atf")
    reg_low = Registry("atf_basic", "basic.example", AssuranceLevel.ALLEGED,
                       endpoint="https://basic.example/atf")
    
    agent = Agent("elite_agent", "atf_premium", n_receipts=80, wilson_ci_lower=0.91,
                  delegation_depth=0, active_days=200)
    
    result = validate_cross_registry_agent(agent, reg_high, reg_low)
    
    print(f"  Agent: {result['agent_level']} (VERIFIED in premium registry)")
    print(f"  Bridge: {result['bridge_level']} (capped by basic registry)")
    print(f"  Effective: {result['effective_level']} (laundering prevented!)")
    print(f"  Laundering detected: {result['trust_laundering_detected']}")
    print()


def scenario_cold_start_cross_registry():
    """New agent, CONFIRMED registries — PROVISIONAL despite bridge."""
    print("=== Scenario: Cold Start Cross-Registry ===")
    
    reg_a = Registry("atf_alpha", "alpha.example", AssuranceLevel.CONFIRMED)
    reg_b = Registry("atf_beta", "beta.example", AssuranceLevel.CONFIRMED)
    
    agent = Agent("new_agent", "atf_alpha", n_receipts=3, wilson_ci_lower=0.21,
                  delegation_depth=0, active_days=2)
    
    result = validate_cross_registry_agent(agent, reg_a, reg_b)
    
    print(f"  Agent: {result['agent_level']} (cold start)")
    print(f"  Bridge: {result['bridge_level']}")
    print(f"  Effective: {result['effective_level']} (agent is the bottleneck, not bridge)")
    print(f"  Requirements:")
    for level, reqs in result['requirements_met'].items():
        met = all(reqs.values())
        print(f"    {level}: {'✓' if met else '✗'} {reqs}")
    print()


def scenario_fbca_mapping():
    """Map FBCA assurance levels to ATF."""
    print("=== Scenario: FBCA Level Mapping ===")
    
    for fbca_level, atf_level in FBCA_MAP.items():
        req = LEVEL_REQUIREMENTS[atf_level]
        print(f"  FBCA {fbca_level:12s} → ATF {atf_level.name:12s} "
              f"(n≥{req['min_n']:2d}, Wilson≥{req['min_wilson']:.2f}, "
              f"depth≤{req['max_delegation']}, days≥{req['min_days']:2d})")
    print()
    print("  Key: trust laundering = agent claims VERIFIED through ALLEGED bridge")
    print("  Fix: effective_level = MIN(agent_level, bridge_level)")
    print()


if __name__ == "__main__":
    print("Assurance-Level Mapper — FBCA-to-ATF Cross-Registry Federation")
    print("Per santaclawd: FBCA assurance levels → ATF mapping")
    print("=" * 70)
    print()
    
    scenario_fbca_mapping()
    scenario_matched_levels()
    scenario_trust_laundering()
    scenario_cold_start_cross_registry()
    
    print("=" * 70)
    print("KEY INSIGHT: Assurance is NOT transitive.")
    print("A↔Bridge↔B ≠ A trusts B. Bridge grade = MIN(both registries).")
    print("Discovery: _atf.<domain> DNS TXT. Bootstrap: SMTP. Trust: ceremony.")
    print("FBCA proved this model since 2004. ATF inherits the lesson.")
