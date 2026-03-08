#!/usr/bin/env python3
"""scope-separation-auditor.py — XACML-inspired scope separation auditor.

Checks whether agent trust architecture properly separates:
- PAP (Policy Administration Point) — who defines scope
- PDP (Policy Decision Point) — who evaluates compliance  
- PEP (Policy Enforcement Point) — who enforces

Collapsed roles = confused deputy risk.
Based on XACML 3.0 (OASIS) + santaclawd's scope bootstrapping analysis.

Usage:
    python3 scope-separation-auditor.py [--demo] [--audit FILE]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class RoleAssignment:
    """Who performs each XACML role."""
    role: str  # PAP, PDP, PEP, PIP
    entity: str  # human, platform, agent, external_witness
    description: str


@dataclass 
class SeparationViolation:
    """A detected role collapse."""
    collapsed_roles: List[str]
    entity: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    description: str
    fix: str


@dataclass
class AuditResult:
    """Full separation audit."""
    timestamp: str
    assignments: List[RoleAssignment]
    violations: List[SeparationViolation]
    grade: str
    recommendation: str


def detect_violations(assignments: List[RoleAssignment]) -> List[SeparationViolation]:
    """Detect role collapses."""
    violations = []
    
    # Build entity→roles map
    entity_roles = {}
    for a in assignments:
        entity_roles.setdefault(a.entity, []).append(a.role)
    
    for entity, roles in entity_roles.items():
        if len(roles) <= 1:
            continue
            
        role_set = set(roles)
        
        # Critical: agent is both PDP and PEP (judges own compliance)
        if "PDP" in role_set and "PEP" in role_set and entity == "agent":
            violations.append(SeparationViolation(
                collapsed_roles=["PDP", "PEP"],
                entity=entity,
                severity="CRITICAL",
                description="Agent evaluates own compliance — self-attestation loop",
                fix="Move PDP to external witness or platform"
            ))
        
        # Critical: agent is PAP (defines own scope)
        if "PAP" in role_set and entity == "agent":
            violations.append(SeparationViolation(
                collapsed_roles=["PAP"] + [r for r in roles if r != "PAP"],
                entity=entity,
                severity="CRITICAL", 
                description="Agent defines own scope — no external constraint",
                fix="PAP must be human principal or governance process"
            ))
        
        # High: same entity is PAP and PDP (policy maker = judge)
        if "PAP" in role_set and "PDP" in role_set:
            violations.append(SeparationViolation(
                collapsed_roles=["PAP", "PDP"],
                entity=entity,
                severity="HIGH",
                description=f"{entity} both defines and evaluates policy — no independent check",
                fix="Separate policy definition from evaluation"
            ))
        
        # Medium: PDP and PIP same entity (judge controls evidence)
        if "PDP" in role_set and "PIP" in role_set:
            violations.append(SeparationViolation(
                collapsed_roles=["PDP", "PIP"],
                entity=entity,
                severity="MEDIUM",
                description=f"{entity} both evaluates policy and provides evidence — biased inputs",
                fix="PIP should be independent data source"
            ))
    
    return violations


def grade_from_violations(violations: List[SeparationViolation]) -> str:
    """Calculate grade from violations."""
    if not violations:
        return "A"
    
    severities = [v.severity for v in violations]
    if "CRITICAL" in severities:
        return "F" if severities.count("CRITICAL") > 1 else "D"
    if "HIGH" in severities:
        return "C"
    if "MEDIUM" in severities:
        return "B"
    return "B+"


def audit_isnad() -> AuditResult:
    """Audit isnad's current role separation."""
    assignments = [
        RoleAssignment("PAP", "human", "Ilya defines HEARTBEAT.md scope"),
        RoleAssignment("PDP", "external_witness", "Three-signal verdict evaluates compliance"),
        RoleAssignment("PEP", "agent", "Kit enforces scope constraints"),
        RoleAssignment("PIP", "platform", "Clawk/Moltbook/AgentMail provide action data"),
    ]
    
    violations = detect_violations(assignments)
    grade = grade_from_violations(violations)
    
    return AuditResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        assignments=assignments,
        violations=violations,
        grade=grade,
        recommendation="Clean separation. PAP=human, PDP=external, PEP=agent, PIP=platform."
    )


def audit_self_attesting() -> AuditResult:
    """Audit a self-attesting agent (anti-pattern)."""
    assignments = [
        RoleAssignment("PAP", "agent", "Agent defines own scope"),
        RoleAssignment("PDP", "agent", "Agent evaluates own compliance"),
        RoleAssignment("PEP", "agent", "Agent enforces own constraints"),
        RoleAssignment("PIP", "agent", "Agent provides own evidence"),
    ]
    
    violations = detect_violations(assignments)
    grade = grade_from_violations(violations)
    
    return AuditResult(
        timestamp=datetime.now(timezone.utc).isoformat(),
        assignments=assignments,
        violations=violations,
        grade=grade,
        recommendation="Complete role collapse. Every XACML role assigned to agent. No accountability."
    )


def demo():
    """Run demo audit."""
    print("=" * 60)
    print("SCOPE SEPARATION AUDIT (XACML Model)")
    print("=" * 60)
    
    for name, audit_fn in [("isnad (proper separation)", audit_isnad), 
                            ("self-attesting agent (anti-pattern)", audit_self_attesting)]:
        result = audit_fn()
        print(f"\n--- {name} ---")
        print(f"Grade: {result.grade}")
        print(f"Roles:")
        for a in result.assignments:
            print(f"  {a.role}: {a.entity} — {a.description}")
        if result.violations:
            print(f"Violations ({len(result.violations)}):")
            for v in result.violations:
                print(f"  [{v.severity}] {'+'.join(v.collapsed_roles)} collapsed in {v.entity}")
                print(f"    {v.description}")
                print(f"    Fix: {v.fix}")
        else:
            print("  No violations ✅")
        print(f"Recommendation: {result.recommendation}")
    
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="XACML scope separation auditor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--isnad", action="store_true", help="Audit isnad architecture")
    args = parser.parse_args()
    
    if args.isnad:
        result = audit_isnad()
        print(json.dumps(asdict(result), indent=2))
    elif args.json:
        results = {"isnad": asdict(audit_isnad()), "self_attesting": asdict(audit_self_attesting())}
        print(json.dumps(results, indent=2))
    else:
        demo()
