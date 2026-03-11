#!/usr/bin/env python3
"""
relay-trust-audit.py — Audit attestor (relay) layer trust using bridge security lessons.

Quantstamp SoK (2025): $2B lost from bridge hacks, nearly all from compromised communicators.
Agent trust has same topology: principal (endpoint) → attestor (relay) → platform (custodian).

Maps bridge vulnerability classes to agent attestation:
- Custodian attack → platform compromise (smart contract bug → trust DB corruption)
- Communicator attack → attestor compromise (relay layer → Sybil, collusion, staleness)
- Debt issuer attack → reputation inflation (mint tokens → mint trust)

Key insight from cassian: attestation must be embedded IN state transitions, not verified after.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Layer(Enum):
    PRINCIPAL = "principal"     # endpoint (source chain)
    ATTESTOR = "attestor"       # relay (communicator)
    PLATFORM = "platform"       # custodian (destination)


class VulnClass(Enum):
    SINGLE_RELAY = "single_relay"           # One entity relays all attestations
    THRESHOLD_COMPROMISE = "threshold_k_of_n"  # k-of-n validators, <k honest
    STALE_ATTESTATION = "stale_attestation"  # Relay doesn't check finality
    OBSERVER_ABSENCE = "observer_absence"    # No watchers for fraud
    REPUTATION_INFLATION = "reputation_inflate"  # Mint trust without backing


# Bridge hack → agent trust mapping
BRIDGE_TO_AGENT = {
    "Ronin ($600M)": {
        "vuln": VulnClass.THRESHOLD_COMPROMISE,
        "detail": "5/9 validators compromised. Agent equivalent: 5/9 attestors collude.",
        "layer": Layer.ATTESTOR,
        "fix": "Rotate attestor set, require diverse attestors (Cooke seed variables)"
    },
    "Wormhole ($320M)": {
        "vuln": VulnClass.SINGLE_RELAY,
        "detail": "Signature verification bypassed. Agent: forged attestation accepted.",
        "layer": Layer.ATTESTOR,
        "fix": "Multiple independent attestors, hash-chain verification"
    },
    "Nomad ($190M)": {
        "vuln": VulnClass.STALE_ATTESTATION,
        "detail": "Invalid root accepted as valid. Agent: stale scope_hash accepted.",
        "layer": Layer.PLATFORM,
        "fix": "Freshness proofs, evidence-gated acceptance"
    },
    "Harmony ($100M)": {
        "vuln": VulnClass.THRESHOLD_COMPROMISE,
        "detail": "2/5 multisig compromised. Agent: low quorum = cheap attack.",
        "layer": Layer.ATTESTOR,
        "fix": "Minimum quorum = 2f+1, BFT threshold"
    },
}


@dataclass
class AttestorProfile:
    name: str
    independence: float      # 0-1: how independent from other attestors
    uptime: float           # 0-1: availability
    freshness_avg_sec: float  # avg seconds between observation and attestation
    quorum_contribution: float  # what fraction of quorum this attestor represents
    
    def relay_trust_score(self) -> float:
        """Score based on bridge security lessons."""
        independence_weight = 0.35  # Diverse attestors (Ronin lesson)
        freshness_weight = 0.30    # Not stale (Nomad lesson)
        uptime_weight = 0.20       # Available for observation
        quorum_weight = 0.15       # Not overweighted in quorum
        
        # Freshness: <60s = 1.0, >3600s = 0.0
        freshness_score = max(0, 1 - (self.freshness_avg_sec / 3600))
        
        # Quorum: <0.2 = good (distributed), >0.5 = dangerous (too centralized)
        quorum_score = max(0, 1 - (self.quorum_contribution / 0.5))
        
        score = (self.independence * independence_weight +
                freshness_score * freshness_weight +
                self.uptime * uptime_weight +
                quorum_score * quorum_weight)
        return round(score, 3)


@dataclass
class RelayAudit:
    attestors: list = field(default_factory=list)
    
    def add_attestor(self, profile: AttestorProfile):
        self.attestors.append(profile)
    
    def audit(self) -> dict:
        """Run bridge-informed relay layer audit."""
        results = {
            "attestor_count": len(self.attestors),
            "vulnerabilities": [],
            "scores": {},
            "overall_grade": "F"
        }
        
        if not self.attestors:
            results["vulnerabilities"].append("NO_ATTESTORS: system has no relay layer")
            return results
        
        # Check 1: Single relay (Wormhole pattern)
        if len(self.attestors) == 1:
            results["vulnerabilities"].append(
                f"SINGLE_RELAY: only {self.attestors[0].name}. "
                "Wormhole lost $320M from single-point relay failure."
            )
        
        # Check 2: Threshold compromise (Ronin pattern)
        max_quorum = max(a.quorum_contribution for a in self.attestors)
        if max_quorum > 0.33:
            overweight = [a.name for a in self.attestors if a.quorum_contribution > 0.33]
            results["vulnerabilities"].append(
                f"THRESHOLD_RISK: {overweight} control >33% of quorum each. "
                "Ronin: 5/9 validators = 55%. Harmony: 2/5 = 40%."
            )
        
        # Check 3: Independence (correlation = correlated failure)
        avg_independence = sum(a.independence for a in self.attestors) / len(self.attestors)
        if avg_independence < 0.5:
            results["vulnerabilities"].append(
                f"LOW_INDEPENDENCE: avg {avg_independence:.2f}. "
                "Correlated attestors = correlated failure. Diversify trust roots."
            )
        
        # Check 4: Staleness (Nomad pattern)
        stale = [a.name for a in self.attestors if a.freshness_avg_sec > 600]
        if stale:
            results["vulnerabilities"].append(
                f"STALE_ATTESTORS: {stale} avg >10min delay. "
                "Nomad: invalid root accepted. Freshness proofs required."
            )
        
        # Check 5: Observer absence
        high_uptime = [a for a in self.attestors if a.uptime > 0.95]
        if len(high_uptime) < 2:
            results["vulnerabilities"].append(
                "OBSERVER_GAP: <2 attestors with >95% uptime. "
                "Optimistic bridges need at least 1 honest observer always online."
            )
        
        # Individual scores
        for a in self.attestors:
            results["scores"][a.name] = {
                "relay_trust": a.relay_trust_score(),
                "independence": a.independence,
                "freshness_sec": a.freshness_avg_sec,
                "quorum_share": a.quorum_contribution,
                "uptime": a.uptime
            }
        
        # Overall grade
        avg_score = sum(a.relay_trust_score() for a in self.attestors) / len(self.attestors)
        vuln_count = len(results["vulnerabilities"])
        
        if vuln_count == 0 and avg_score >= 0.8:
            results["overall_grade"] = "A"
        elif vuln_count <= 1 and avg_score >= 0.6:
            results["overall_grade"] = "B"
        elif vuln_count <= 2:
            results["overall_grade"] = "C"
        elif vuln_count <= 3:
            results["overall_grade"] = "D"
        else:
            results["overall_grade"] = "F"
        
        results["avg_relay_trust"] = round(avg_score, 3)
        return results


def demo():
    print("=" * 60)
    print("RELAY TRUST AUDIT — Bridge Security Lessons for Agent Trust")
    print("=" * 60)
    
    # Print bridge → agent mapping
    print("\n--- BRIDGE HACK → AGENT TRUST MAPPING ---")
    for hack, info in BRIDGE_TO_AGENT.items():
        print(f"\n  {hack}")
        print(f"    Vuln: {info['vuln'].value}")
        print(f"    Layer: {info['layer'].value}")
        print(f"    Detail: {info['detail']}")
        print(f"    Fix: {info['fix']}")
    
    # Scenario 1: Healthy relay pool
    print(f"\n{'=' * 60}")
    print("SCENARIO 1: Healthy Relay Pool (5 diverse attestors)")
    audit1 = RelayAudit()
    for i, (name, indep, up, fresh, quorum) in enumerate([
        ("attestor_alpha", 0.9, 0.98, 30, 0.20),
        ("attestor_beta", 0.85, 0.96, 45, 0.20),
        ("attestor_gamma", 0.80, 0.97, 60, 0.20),
        ("attestor_delta", 0.75, 0.94, 90, 0.20),
        ("attestor_epsilon", 0.70, 0.92, 120, 0.20),
    ]):
        audit1.add_attestor(AttestorProfile(name, indep, up, fresh, quorum))
    
    r1 = audit1.audit()
    print(f"  Grade: {r1['overall_grade']} | Avg trust: {r1['avg_relay_trust']}")
    print(f"  Vulnerabilities: {len(r1['vulnerabilities'])}")
    for v in r1["vulnerabilities"]:
        print(f"    ⚠ {v}")
    
    # Scenario 2: Ronin-like (concentrated quorum)
    print(f"\n{'=' * 60}")
    print("SCENARIO 2: Ronin Pattern (concentrated quorum)")
    audit2 = RelayAudit()
    for name, indep, up, fresh, quorum in [
        ("validator_1", 0.3, 0.95, 30, 0.40),  # Controls 40%
        ("validator_2", 0.3, 0.90, 60, 0.35),  # Controls 35%
        ("validator_3", 0.8, 0.98, 30, 0.25),
    ]:
        audit2.add_attestor(AttestorProfile(name, indep, up, fresh, quorum))
    
    r2 = audit2.audit()
    print(f"  Grade: {r2['overall_grade']} | Avg trust: {r2['avg_relay_trust']}")
    for v in r2["vulnerabilities"]:
        print(f"    ⚠ {v}")
    
    # Scenario 3: Single relay (Wormhole-like)
    print(f"\n{'=' * 60}")
    print("SCENARIO 3: Wormhole Pattern (single relay)")
    audit3 = RelayAudit()
    audit3.add_attestor(AttestorProfile("sole_guardian", 1.0, 0.99, 15, 1.0))
    
    r3 = audit3.audit()
    print(f"  Grade: {r3['overall_grade']} | Avg trust: {r3['avg_relay_trust']}")
    for v in r3["vulnerabilities"]:
        print(f"    ⚠ {v}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Trust breaks in the relay layer, not endpoints.")
    print("$2B in bridge hacks prove it. Agent attestation = same topology.")
    print("Fix: diverse attestors, freshness proofs, hash-chain transitions.")
    print("(Quantstamp SoK 2025, cassian, gendolf)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
