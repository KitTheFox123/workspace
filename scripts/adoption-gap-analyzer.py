#!/usr/bin/env python3
"""adoption-gap-analyzer.py — Measures gap between available security tooling and actual adoption.

Models the CT adoption timeline (2011 paper → 2018 Chrome enforcement) and applies
it to agent trust tooling. Quantifies coordination cost vs risk tolerance.

Based on:
- Crosby & Wallach (USENIX 2009): tamper-evident logging
- CT timeline: RFC 6962 (2013) → Chrome enforcement (2018) → universal (2020)
- Rogers diffusion of innovations (1962): S-curve adoption

Usage:
    python3 adoption-gap-analyzer.py [--demo] [--audit WORKSPACE_PATH]
"""

import argparse
import json
import os
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


@dataclass
class SecurityCapability:
    """A security capability with adoption status."""
    name: str
    category: str  # logging, attestation, verification, monitoring
    paper_year: int  # When the technique was published
    tool_available: bool  # Whether we have a tool for it
    tool_name: Optional[str]
    adopted: bool  # Whether actually in use
    coordination_cost: str  # none, low, medium, high
    risk_mitigated: str
    adoption_barrier: str


@dataclass
class AdoptionAudit:
    """Workspace adoption gap analysis."""
    timestamp: str
    total_capabilities: int
    tools_available: int
    tools_adopted: int
    adoption_rate: float
    gap_score: float  # 0-1, higher = bigger gap
    grade: str
    gaps: List[dict]
    recommendation: str


CAPABILITIES = [
    SecurityCapability("tamper_evident_logging", "logging", 2009,
                      True, "write-path-auditor.py", False,
                      "medium", "Write erasure, history modification",
                      "Requires independent auditor nodes"),
    SecurityCapability("merkle_transparency", "logging", 2013,
                      True, "scope-transparency-log.py", False,
                      "high", "Split-view attacks, log tampering",
                      "Requires gossip protocol between monitors"),
    SecurityCapability("scope_commit_signing", "attestation", 2024,
                      True, "scope-cert-issuer.py", False,
                      "low", "Scope drift, unauthorized capability use",
                      "Principal must sign — coordination with human"),
    SecurityCapability("heartbeat_liveness", "monitoring", 2004,
                      True, "liveness-renewal.py", True,
                      "none", "Silent failure, zombie agents",
                      "Already built into heartbeat system"),
    SecurityCapability("cusum_drift_detection", "monitoring", 1954,
                      True, "scope-drift-detector.py", True,
                      "none", "Gradual behavioral drift",
                      "Runs locally, no coordination needed"),
    SecurityCapability("sortition_attestor_selection", "verification", 2024,
                      True, "sortition-attestor-selector.py", False,
                      "high", "Faction capture, attestor collusion",
                      "Requires attestor pool infrastructure"),
    SecurityCapability("genesis_anchor", "verification", 2024,
                      True, "genesis-anchor-verifier.py", False,
                      "low", "Baseline poisoning, identity drift",
                      "One-time setup at deploy"),
    SecurityCapability("three_signal_verdict", "monitoring", 2024,
                      True, "three-signal-verdict.py", True,
                      "none", "Gray failures, masking attacks",
                      "Runs locally from existing signals"),
    SecurityCapability("gray_failure_detection", "monitoring", 2017,
                      True, "gray-failure-detector.py", False,
                      "medium", "Differential observability gaps",
                      "Needs multiple vantage points"),
    SecurityCapability("pull_attestation", "attestation", 2024,
                      True, "pull-attestation-sim.py", False,
                      "high", "Self-reported evidence manipulation",
                      "Requires verifier infrastructure to pull"),
    SecurityCapability("alarm_fatigue_prevention", "monitoring", 2024,
                      True, "alarm-fatigue-detector.py", True,
                      "none", "Alert desensitization, missed real threats",
                      "Schmitt trigger already in monitoring"),
    SecurityCapability("omission_detection", "monitoring", 2024,
                      True, "omission-drift-detector.py", False,
                      "low", "Silent capability atrophy",
                      "Needs baseline frequency tracking setup"),
]


def rogers_adoption_curve(t: float, k: float = 1.0, t0: float = 5.0) -> float:
    """Rogers S-curve: fraction adopted at time t years after availability."""
    return 1.0 / (1.0 + math.exp(-k * (t - t0)))


def audit_workspace(workspace_path: str = ".") -> AdoptionAudit:
    """Audit adoption gap in workspace."""
    now = datetime.now(timezone.utc)
    
    tools_available = sum(1 for c in CAPABILITIES if c.tool_available)
    tools_adopted = sum(1 for c in CAPABILITIES if c.adopted)
    total = len(CAPABILITIES)
    
    adoption_rate = tools_adopted / tools_available if tools_available > 0 else 0
    gap_score = 1.0 - adoption_rate
    
    # Grade
    if adoption_rate >= 0.8: grade = "A"
    elif adoption_rate >= 0.6: grade = "B"
    elif adoption_rate >= 0.4: grade = "C"
    elif adoption_rate >= 0.2: grade = "D"
    else: grade = "F"
    
    # Identify gaps (available but not adopted)
    gaps = []
    for c in CAPABILITIES:
        if c.tool_available and not c.adopted:
            gaps.append({
                "capability": c.name,
                "tool": c.tool_name,
                "coordination_cost": c.coordination_cost,
                "risk_mitigated": c.risk_mitigated,
                "barrier": c.adoption_barrier,
                "priority": "HIGH" if c.coordination_cost in ("none", "low") else "MEDIUM"
            })
    
    # Sort by priority (low coordination cost = easy wins)
    gaps.sort(key=lambda g: {"HIGH": 0, "MEDIUM": 1}.get(g["priority"], 2))
    
    # CT timeline comparison
    ct_years = 2018 - 2013  # 5 years from RFC to enforcement
    agent_months = 3  # isnad project age in months
    ct_equivalent = agent_months / 12 / ct_years  # Where we are on CT timeline
    
    recommendation = (
        f"Adoption rate: {adoption_rate:.0%}. "
        f"{len(gaps)} tools available but not integrated. "
        f"Easy wins (no coordination): {sum(1 for g in gaps if g['priority'] == 'HIGH')} capabilities. "
        f"CT took 5 years from paper to enforcement. "
        f"We're at month {agent_months} ({ct_equivalent:.0%} of CT timeline)."
    )
    
    return AdoptionAudit(
        timestamp=now.isoformat(),
        total_capabilities=total,
        tools_available=tools_available,
        tools_adopted=tools_adopted,
        adoption_rate=adoption_rate,
        gap_score=gap_score,
        grade=grade,
        gaps=gaps,
        recommendation=recommendation
    )


def demo():
    """Run demo analysis."""
    audit = audit_workspace()
    
    print("=" * 60)
    print("ADOPTION GAP ANALYSIS")
    print("=" * 60)
    print()
    print(f"Capabilities tracked: {audit.total_capabilities}")
    print(f"Tools available:      {audit.tools_available}")
    print(f"Tools adopted:        {audit.tools_adopted}")
    print(f"Adoption rate:        {audit.adoption_rate:.0%}")
    print(f"Grade:                {audit.grade}")
    print()
    
    if audit.gaps:
        print("GAPS (available but not adopted):")
        print("-" * 60)
        for g in audit.gaps:
            print(f"  [{g['priority']}] {g['capability']}")
            print(f"       Tool: {g['tool']}")
            print(f"       Cost: {g['coordination_cost']}")
            print(f"       Risk: {g['risk_mitigated']}")
            print(f"       Barrier: {g['barrier']}")
            print()
    
    # Rogers curve projection
    print("ROGERS DIFFUSION PROJECTION:")
    print("-" * 60)
    for year in [1, 2, 3, 5, 7, 10]:
        adoption = rogers_adoption_curve(year)
        print(f"  Year {year:2d}: {adoption:.0%} adoption")
    
    print()
    print(f"Recommendation: {audit.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adoption gap analyzer")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--audit", type=str, default=".")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(asdict(audit_workspace(args.audit)), indent=2))
    else:
        demo()
