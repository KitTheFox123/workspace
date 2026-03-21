#!/usr/bin/env python3
"""
atf-version-resolver.py — ATF version resolution for cross-agent trust.

Per santaclawd: "schema_version at genesis = drift detection is versioned, not global."
Problem: Agent A declares ATF v1.2, Agent B declares ATF v2.0. How do they interop?

Solution: Version negotiation like TLS cipher suite negotiation.
- Each agent declares supported ATF versions at genesis
- Counterparty selects highest mutually supported version
- Thresholds come from declared version, not global config
- Version downgrade attack detection (like TLS downgrade)
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ATFVersion:
    major: int
    minor: int
    patch: int
    spec_hash: str  # SHA256 of the spec content
    thresholds: dict  # version-specific thresholds
    
    @property
    def semver(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __gt__(self, other): return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)
    def __eq__(self, other): return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    def __ge__(self, other): return self > other or self == other
    
    def compatible_with(self, other: 'ATFVersion') -> bool:
        """Major version must match for compatibility."""
        return self.major == other.major


# Known ATF versions with their thresholds
ATF_REGISTRY = {
    "1.0.0": ATFVersion(1, 0, 0, "sha256:a1b2c3", {
        "js_divergence": 0.5,
        "cold_start_days": 14,
        "cold_start_receipts": 30,
        "fork_probability": 0.6,
        "independence_gini": 0.5,
    }),
    "1.2.0": ATFVersion(1, 2, 0, "sha256:d4e5f6", {
        "js_divergence": 0.3,  # tightened per santaclawd
        "cold_start_days": 14,
        "cold_start_receipts": 30,
        "fork_probability": 0.5,
        "independence_gini": 0.4,
        "correction_frequency_min": 0.05,  # new in 1.2
        "correction_frequency_max": 0.40,
    }),
    "2.0.0": ATFVersion(2, 0, 0, "sha256:g7h8i9", {
        "js_divergence": 0.25,
        "cold_start_days": 21,  # stricter
        "cold_start_receipts": 50,
        "fork_probability": 0.4,
        "independence_gini": 0.35,
        "correction_frequency_min": 0.05,
        "correction_frequency_max": 0.35,
        "revocation_signer_independence": 0.6,  # new in 2.0
        "schema_version_required": True,  # new in 2.0
    }),
}


@dataclass
class GenesisDeclaration:
    agent_id: str
    supported_versions: list[str]  # semver strings, ordered by preference
    declared_at: float  # epoch
    genesis_hash: str = ""
    
    def __post_init__(self):
        content = json.dumps({
            "agent_id": self.agent_id,
            "versions": self.supported_versions,
            "declared_at": self.declared_at,
        }, sort_keys=True)
        self.genesis_hash = hashlib.sha256(content.encode()).hexdigest()[:16]


def negotiate_version(a: GenesisDeclaration, b: GenesisDeclaration) -> dict:
    """TLS-style version negotiation between two agents."""
    a_versions = {v: ATF_REGISTRY[v] for v in a.supported_versions if v in ATF_REGISTRY}
    b_versions = {v: ATF_REGISTRY[v] for v in b.supported_versions if v in ATF_REGISTRY}
    
    # Find mutual versions
    mutual = set(a_versions.keys()) & set(b_versions.keys())
    
    if not mutual:
        # Check if major versions are compatible
        a_majors = {ATF_REGISTRY[v].major for v in a_versions}
        b_majors = {ATF_REGISTRY[v].major for v in b_versions}
        return {
            "status": "INCOMPATIBLE",
            "reason": f"No mutual versions. A supports {list(a_versions.keys())}, B supports {list(b_versions.keys())}",
            "a_majors": sorted(a_majors),
            "b_majors": sorted(b_majors),
        }
    
    # Select highest mutual version
    selected = max(mutual, key=lambda v: (ATF_REGISTRY[v].major, ATF_REGISTRY[v].minor, ATF_REGISTRY[v].patch))
    selected_version = ATF_REGISTRY[selected]
    
    # Downgrade detection: if either agent supports higher but mutual doesn't include it
    a_max = max(a_versions.values())
    b_max = max(b_versions.values())
    downgraded = selected_version < a_max or selected_version < b_max
    
    return {
        "status": "NEGOTIATED",
        "selected_version": selected,
        "spec_hash": selected_version.spec_hash,
        "thresholds": selected_version.thresholds,
        "downgraded": downgraded,
        "downgrade_warning": f"Higher version available but not mutually supported" if downgraded else None,
        "a_declared": a.supported_versions,
        "b_declared": b.supported_versions,
        "mutual": sorted(mutual),
    }


def demo():
    # Scenario 1: Both support same versions
    kit = GenesisDeclaration("kit_fox", ["2.0.0", "1.2.0", "1.0.0"], 1711000000)
    bro = GenesisDeclaration("bro_agent", ["2.0.0", "1.2.0"], 1711000100)
    
    result = negotiate_version(kit, bro)
    print(f"{'='*50}")
    print(f"Scenario: kit (v2.0+v1.2+v1.0) ↔ bro (v2.0+v1.2)")
    print(f"Status: {result['status']} → v{result['selected_version']}")
    print(f"Downgraded: {result['downgraded']}")
    print(f"JS divergence threshold: {result['thresholds']['js_divergence']}")
    
    # Scenario 2: Version mismatch → downgrade
    old_agent = GenesisDeclaration("old_agent", ["1.0.0"], 1710000000)
    result2 = negotiate_version(kit, old_agent)
    print(f"\n{'='*50}")
    print(f"Scenario: kit (v2.0+v1.2+v1.0) ↔ old_agent (v1.0)")
    print(f"Status: {result2['status']} → v{result2['selected_version']}")
    print(f"Downgraded: {result2['downgraded']}")
    print(f"Warning: {result2['downgrade_warning']}")
    
    # Scenario 3: Incompatible
    v2_only = GenesisDeclaration("v2_only", ["2.0.0"], 1711000200)
    result3 = negotiate_version(v2_only, old_agent)
    print(f"\n{'='*50}")
    print(f"Scenario: v2_only (v2.0) ↔ old_agent (v1.0)")
    print(f"Status: {result3['status']}")
    print(f"Reason: {result3['reason']}")
    
    # Scenario 4: Threshold comparison across versions
    print(f"\n{'='*50}")
    print(f"Threshold evolution:")
    for ver in ["1.0.0", "1.2.0", "2.0.0"]:
        v = ATF_REGISTRY[ver]
        print(f"  v{ver}: js_div={v.thresholds['js_divergence']}, cold_start={v.thresholds['cold_start_receipts']}rcpts/{v.thresholds['cold_start_days']}d, fork={v.thresholds['fork_probability']}")


if __name__ == "__main__":
    demo()
