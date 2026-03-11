#!/usr/bin/env python3
"""
responsibility-gap-detector.py — Detect responsibility gaps in agent certification chains.

Da Silva 2024 (Philosophy Compass): responsibility gaps arise when no person
can be blamed on leading accounts of moral responsibility.

Cert levels close gaps:
  L0: No cert → full gap (nobody accountable)
  L1: Self-declared → partial gap (agent claims, no verification)
  L2: Human-reviewed → closed (human liable for review)
  L3: System-monitored → closed (operator liable for monitoring)
  L4: DAG-supervised → closed (cryptographic scope bounds liability)

A gap exists when damage exceeds the highest cert level's coverage.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class CertLevel(IntEnum):
    NONE = 0    # No certification
    SELF = 1    # Self-declared capabilities
    HUMAN = 2   # Human reviewed and approved
    SYSTEM = 3  # Continuous system monitoring
    DAG = 4     # Cert DAG is the supervisor


CERT_COVERAGE = {
    CertLevel.NONE: 0.0,
    CertLevel.SELF: 0.2,   # Claims without verification
    CertLevel.HUMAN: 0.7,  # Human review covers most cases
    CertLevel.SYSTEM: 0.9, # Continuous monitoring catches drift
    CertLevel.DAG: 0.98,   # Cryptographic scope leaves minimal gap
}

LIABLE_PARTY = {
    CertLevel.NONE: "NOBODY (gap!)",
    CertLevel.SELF: "agent (weak — self-attestation)",
    CertLevel.HUMAN: "human reviewer",
    CertLevel.SYSTEM: "system operator",
    CertLevel.DAG: "DAG governance (cryptographic)",
}


@dataclass
class Agent:
    name: str
    cert_level: CertLevel
    scope_hash: Optional[str] = None
    has_remediation_chain: bool = False
    has_audit_trail: bool = False


@dataclass
class Incident:
    agent: Agent
    damage_scope: float  # 0-1, how much of capability space was affected
    description: str


def detect_gap(incident: Incident) -> dict:
    """Detect responsibility gap for an incident."""
    agent = incident.agent
    coverage = CERT_COVERAGE[agent.cert_level]
    liable = LIABLE_PARTY[agent.cert_level]
    
    # Gap = damage that exceeds certification coverage
    gap_size = max(0, incident.damage_scope - coverage)
    
    # Remediation chain reduces gap (someone tracked the fix)
    if agent.has_remediation_chain:
        gap_size *= 0.5  # Fix tracking halves the gap
    
    # Audit trail reduces gap (evidence exists)
    if agent.has_audit_trail:
        gap_size *= 0.7  # Evidence narrows uncertainty
    
    # Grade
    if gap_size == 0:
        grade = "A"  # No gap
        status = "CLOSED"
    elif gap_size < 0.1:
        grade = "B"  # Minor gap
        status = "NARROW"
    elif gap_size < 0.3:
        grade = "C"  # Significant gap
        status = "OPEN"
    else:
        grade = "F"  # Full responsibility gap
        status = "CRITICAL"
    
    return {
        "agent": agent.name,
        "cert_level": f"L{agent.cert_level}",
        "liable_party": liable,
        "damage_scope": incident.damage_scope,
        "cert_coverage": coverage,
        "gap_size": round(gap_size, 3),
        "gap_status": status,
        "grade": grade,
        "remediation_chain": agent.has_remediation_chain,
        "audit_trail": agent.has_audit_trail,
        "description": incident.description,
    }


def demo():
    incidents = [
        Incident(
            Agent("certified_bot", CertLevel.DAG, "abc123", True, True),
            0.3,
            "Scope drift detected, DAG halted automatically"
        ),
        Incident(
            Agent("reviewed_bot", CertLevel.HUMAN, "def456", True, True),
            0.5,
            "Behavioral drift, human reviewer notified"
        ),
        Incident(
            Agent("self_declared", CertLevel.SELF, None, False, False),
            0.8,
            "Capability escalation, no verification"
        ),
        Incident(
            Agent("ghost_agent", CertLevel.NONE, None, False, False),
            0.9,
            "Silent failure, no cert, no trail"
        ),
        Incident(
            Agent("monitored_bot", CertLevel.SYSTEM, "ghi789", False, True),
            0.4,
            "API misuse, system monitoring caught it"
        ),
        Incident(
            Agent("uncertified_but_tracked", CertLevel.SELF, None, True, True),
            0.6,
            "Damage occurred but remediation chain exists"
        ),
    ]
    
    print("=" * 65)
    print("RESPONSIBILITY GAP DETECTOR — Da Silva 2024")
    print("=" * 65)
    
    for inc in incidents:
        result = detect_gap(inc)
        print(f"\n{'─' * 55}")
        print(f"Agent: {result['agent']} | Cert: {result['cert_level']} | Grade: {result['grade']}")
        print(f"  Liable: {result['liable_party']}")
        print(f"  Damage: {result['damage_scope']:.0%} | Coverage: {result['cert_coverage']:.0%} | Gap: {result['gap_size']:.1%}")
        print(f"  Status: {result['gap_status']}")
        print(f"  Remediation: {'✓' if result['remediation_chain'] else '✗'} | Audit: {'✓' if result['audit_trail'] else '✗'}")
        print(f"  {result['description']}")
    
    # Summary
    results = [detect_gap(inc) for inc in incidents]
    grades = [r['grade'] for r in results]
    gaps = sum(1 for r in results if r['gap_status'] in ('OPEN', 'CRITICAL'))
    
    print(f"\n{'=' * 65}")
    print(f"PORTFOLIO: {len(incidents)} incidents | {gaps} open gaps")
    print(f"Grades: {' '.join(grades)}")
    print(f"\nKEY INSIGHT: Cert level closes responsibility gaps.")
    print(f"No cert = nobody liable. Cert = receipt of who's responsible.")
    print(f"Remediation chain + audit trail narrow remaining gaps.")
    print(f"Da Silva 2024: the gap is moral, not technical.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
