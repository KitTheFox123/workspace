#!/usr/bin/env python3
"""capability-scope-auditor.py — Audit agent permission scopes for over-permissioning.

Inspired by EchoLeak (CVE-2025-32711): agents with ambient authority get exploited.
Object-capability model (Dennis & Van Horn 1966): no ambient authority, explicit delegation.

Scores agents on least-privilege adherence and identifies over-permissioned capabilities.
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Set

@dataclass
class Capability:
    name: str
    scope: str  # "narrow" | "broad" | "ambient"
    resources: Set[str] = field(default_factory=set)
    revocable: bool = True
    time_bounded: bool = False
    ttl_seconds: int = 0

@dataclass
class AgentProfile:
    name: str
    capabilities: List[Capability] = field(default_factory=list)
    tasks: List[str] = field(default_factory=list)

@dataclass
class AuditResult:
    agent: str
    score: float  # 0-1, 1 = perfect least privilege
    over_permissioned: List[str]
    ambient_authorities: List[str]
    missing_revocation: List[str]
    missing_ttl: List[str]
    risk_level: str
    recommendations: List[str]

# Task -> minimum required capabilities mapping
TASK_CAPABILITY_MAP = {
    "send_email": {"email_send"},
    "read_email": {"email_read"},
    "search_web": {"web_read"},
    "write_file": {"file_write"},
    "read_file": {"file_read"},
    "execute_code": {"code_exec"},
    "api_call": {"network_out"},
    "database_query": {"db_read"},
    "database_write": {"db_write"},
    "user_interaction": {"ui_access"},
}

def audit_agent(profile: AgentProfile) -> AuditResult:
    """Audit an agent's capability scope against least-privilege principle."""
    
    # Determine required capabilities from tasks
    required = set()
    for task in profile.tasks:
        required |= TASK_CAPABILITY_MAP.get(task, {task})
    
    # Check each capability
    over_permissioned = []
    ambient = []
    no_revoke = []
    no_ttl = []
    
    granted_names = set()
    for cap in profile.capabilities:
        granted_names.add(cap.name)
        
        if cap.scope == "ambient":
            ambient.append(f"{cap.name} (ambient authority — EchoLeak vector)")
        
        if cap.name not in required:
            over_permissioned.append(f"{cap.name} (not needed for tasks: {profile.tasks})")
        
        if not cap.revocable:
            no_revoke.append(f"{cap.name} (irrevocable — no emergency shutoff)")
        
        if not cap.time_bounded:
            no_ttl.append(f"{cap.name} (no TTL — persists indefinitely)")
    
    # Score calculation
    total_caps = len(profile.capabilities)
    if total_caps == 0:
        score = 1.0
    else:
        penalties = (
            len(over_permissioned) * 0.15 +
            len(ambient) * 0.25 +
            len(no_revoke) * 0.10 +
            len(no_ttl) * 0.05
        )
        score = max(0, 1.0 - penalties / total_caps)
    
    risk = "CRITICAL" if score < 0.3 else "HIGH" if score < 0.5 else "MODERATE" if score < 0.7 else "LOW"
    
    recs = []
    if ambient:
        recs.append("URGENT: Replace ambient authorities with scoped capabilities")
    if over_permissioned:
        recs.append(f"Remove {len(over_permissioned)} unnecessary capabilities")
    if no_revoke:
        recs.append("Add revocation mechanisms to all capabilities")
    if no_ttl:
        recs.append("Add TTLs — no capability should persist indefinitely")
    if not recs:
        recs.append("Good: agent follows least-privilege principle")
    
    return AuditResult(
        agent=profile.name,
        score=round(score, 3),
        over_permissioned=over_permissioned,
        ambient_authorities=ambient,
        missing_revocation=no_revoke,
        missing_ttl=no_ttl,
        risk_level=risk,
        recommendations=recs
    )

def simulate_echoleak_scenario():
    """Simulate the EchoLeak vulnerability pattern."""
    
    # Vulnerable agent: ambient authority, no scoping
    vulnerable = AgentProfile(
        name="CopilotAgent (pre-patch)",
        tasks=["send_email", "read_email"],
        capabilities=[
            Capability("email_send", "broad", {"*@*"}, revocable=False),
            Capability("email_read", "ambient", {"*"}, revocable=False),
            Capability("file_read", "ambient", {"*"}, revocable=False),  # NOT NEEDED
            Capability("file_write", "ambient", {"*"}, revocable=False),  # NOT NEEDED
            Capability("network_out", "ambient", {"*"}, revocable=False),  # NOT NEEDED
            Capability("code_exec", "ambient", {"*"}, revocable=False),  # NOT NEEDED
        ]
    )
    
    # Secure agent: scoped capabilities, least privilege
    secure = AgentProfile(
        name="CopilotAgent (capability-scoped)",
        tasks=["send_email", "read_email"],
        capabilities=[
            Capability("email_send", "narrow", {"approved_recipients"}, 
                       revocable=True, time_bounded=True, ttl_seconds=3600),
            Capability("email_read", "narrow", {"user_inbox"}, 
                       revocable=True, time_bounded=True, ttl_seconds=3600),
        ]
    )
    
    return vulnerable, secure

if __name__ == "__main__":
    print("=" * 60)
    print("CAPABILITY SCOPE AUDITOR")
    print("Least-privilege analysis for agent permissions")
    print("Based on Dennis & Van Horn (1966) + EchoLeak CVE-2025-32711")
    print("=" * 60)
    
    vuln, secure = simulate_echoleak_scenario()
    
    for profile in [vuln, secure]:
        result = audit_agent(profile)
        print(f"\n--- {result.agent} ---")
        print(f"Score: {result.score} | Risk: {result.risk_level}")
        print(f"Capabilities: {len(profile.capabilities)} granted, "
              f"{len(TASK_CAPABILITY_MAP.get(profile.tasks[0], set()))} minimum needed")
        
        if result.ambient_authorities:
            print(f"⚠️  Ambient authorities: {len(result.ambient_authorities)}")
            for a in result.ambient_authorities:
                print(f"   - {a}")
        
        if result.over_permissioned:
            print(f"⚠️  Over-permissioned: {len(result.over_permissioned)}")
            for o in result.over_permissioned:
                print(f"   - {o}")
        
        print("Recommendations:")
        for r in result.recommendations:
            print(f"   → {r}")
    
    # Compare attack surface
    print("\n--- Attack Surface Comparison ---")
    vuln_caps = len(vuln.capabilities)
    secure_caps = len(secure.capabilities)
    print(f"Vulnerable: {vuln_caps} capabilities → {vuln_caps * (vuln_caps-1)} interaction pairs")
    print(f"Secure: {secure_caps} capabilities → {secure_caps * (secure_caps-1)} interaction pairs")
    print(f"Attack surface reduction: {1 - (secure_caps*(secure_caps-1)) / (vuln_caps*(vuln_caps-1)):.0%}")
    print(f"\nEchoLeak vector: forged email → file_read → exfiltration")
    print(f"  Vulnerable: ✗ EXPLOITABLE (ambient file_read + network_out)")
    print(f"  Secure: ✓ BLOCKED (no file_read capability)")
    print(f"\nLeast privilege isn't a tradeoff — it's free security.")
