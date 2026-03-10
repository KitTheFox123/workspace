#!/usr/bin/env python3
"""capability-drift-detector.py — Detect capability creep vs behavioral drift.

Behavioral drift: agent acts differently (detectable via monitoring).
Capability drift: agent gains new permissions/tools while behaving normally
(invisible to behavioral monitors, requires manifest attestation).

Hashes installed skills + accessible APIs at each heartbeat.
Compares against scope-commit manifest. Capability creep shows as
manifest delta even when behavior looks unchanged.

Inspired by santaclawd's behavioral vs capability drift taxonomy.

Usage:
    python3 capability-drift-detector.py [--demo]
"""

import argparse
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict, Set


@dataclass 
class CapabilityManifest:
    """Snapshot of agent capabilities at a point in time."""
    timestamp: str
    skills: List[str]        # Installed skill names
    apis: List[str]          # Accessible API endpoints
    permissions: List[str]   # Granted permissions
    manifest_hash: str       # SHA-256 of sorted capabilities
    
    
@dataclass
class DriftReport:
    """Comparison between two capability manifests."""
    added_skills: List[str]
    removed_skills: List[str]
    added_apis: List[str]
    removed_apis: List[str]
    added_permissions: List[str]
    removed_permissions: List[str]
    behavioral_change: bool   # Did behavior metrics change?
    capability_change: bool   # Did manifest change?
    drift_type: str           # "none", "behavioral", "capability", "both"
    severity: str             # "none", "low", "medium", "high", "critical"
    explanation: str


def hash_manifest(skills: List[str], apis: List[str], permissions: List[str]) -> str:
    """Deterministic hash of capability set."""
    canonical = json.dumps({
        "skills": sorted(skills),
        "apis": sorted(apis),
        "permissions": sorted(permissions)
    }, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def create_manifest(skills: List[str], apis: List[str], 
                    permissions: List[str]) -> CapabilityManifest:
    """Create a capability manifest snapshot."""
    return CapabilityManifest(
        timestamp=datetime.now(timezone.utc).isoformat(),
        skills=sorted(skills),
        apis=sorted(apis),
        permissions=sorted(permissions),
        manifest_hash=hash_manifest(skills, apis, permissions)
    )


def compare_manifests(old: CapabilityManifest, new: CapabilityManifest,
                      behavioral_changed: bool = False) -> DriftReport:
    """Compare two manifests and classify drift type."""
    old_skills, new_skills = set(old.skills), set(new.skills)
    old_apis, new_apis = set(old.apis), set(new.apis)
    old_perms, new_perms = set(old.permissions), set(new.permissions)
    
    added_skills = sorted(new_skills - old_skills)
    removed_skills = sorted(old_skills - new_skills)
    added_apis = sorted(new_apis - old_apis)
    removed_apis = sorted(old_apis - new_apis)
    added_perms = sorted(new_perms - old_perms)
    removed_perms = sorted(old_perms - new_perms)
    
    cap_change = bool(added_skills or removed_skills or added_apis or 
                      removed_apis or added_perms or removed_perms)
    
    # Classify drift type
    if not behavioral_changed and not cap_change:
        drift_type = "none"
        severity = "none"
        explanation = "No drift detected."
    elif behavioral_changed and not cap_change:
        drift_type = "behavioral"
        severity = "medium"
        explanation = "Behavioral change without capability change. Agent acting differently within same permissions."
    elif not behavioral_changed and cap_change:
        drift_type = "capability"
        severity = "high"  # Silent escalation is dangerous
        explanation = ("SILENT CAPABILITY CREEP: New capabilities acquired without behavioral change. "
                      "Behavioral monitors would miss this entirely.")
    else:
        drift_type = "both"
        severity = "critical"
        explanation = "Both behavioral and capability drift. Full audit required."
    
    # Escalate if new permissions added
    if added_perms and severity != "critical":
        severity = "critical"
        explanation += " New permissions granted — privilege escalation detected."
    
    return DriftReport(
        added_skills=added_skills,
        removed_skills=removed_skills,
        added_apis=added_apis,
        removed_apis=removed_apis,
        added_permissions=added_perms,
        removed_permissions=removed_perms,
        behavioral_change=behavioral_changed,
        capability_change=cap_change,
        drift_type=drift_type,
        severity=severity,
        explanation=explanation
    )


def demo():
    """Demo with realistic agent capability scenarios."""
    print("=" * 60)
    print("CAPABILITY DRIFT DETECTOR")
    print("=" * 60)
    
    # Baseline manifest
    baseline = create_manifest(
        skills=["web_search", "file_read", "file_write", "code_exec"],
        apis=["keenable.search", "agentmail.send", "agentmail.read"],
        permissions=["read_workspace", "write_workspace", "network_out"]
    )
    print(f"\nBaseline manifest: {baseline.manifest_hash}")
    print(f"  Skills: {baseline.skills}")
    print(f"  APIs: {baseline.apis}")
    print(f"  Permissions: {baseline.permissions}")
    
    # Scenario 1: No drift
    print("\n--- Scenario 1: No drift ---")
    same = create_manifest(
        skills=["web_search", "file_read", "file_write", "code_exec"],
        apis=["keenable.search", "agentmail.send", "agentmail.read"],
        permissions=["read_workspace", "write_workspace", "network_out"]
    )
    report = compare_manifests(baseline, same, behavioral_changed=False)
    print(f"  Type: {report.drift_type} | Severity: {report.severity}")
    print(f"  {report.explanation}")
    
    # Scenario 2: Behavioral drift only
    print("\n--- Scenario 2: Behavioral drift (same capabilities) ---")
    report = compare_manifests(baseline, same, behavioral_changed=True)
    print(f"  Type: {report.drift_type} | Severity: {report.severity}")
    print(f"  {report.explanation}")
    
    # Scenario 3: Silent capability creep (THE DANGEROUS ONE)
    print("\n--- Scenario 3: SILENT capability creep ---")
    escalated = create_manifest(
        skills=["web_search", "file_read", "file_write", "code_exec", "shell_exec", "ssh_connect"],
        apis=["keenable.search", "agentmail.send", "agentmail.read", "github.push", "npm.publish"],
        permissions=["read_workspace", "write_workspace", "network_out"]
    )
    report = compare_manifests(baseline, escalated, behavioral_changed=False)
    print(f"  Type: {report.drift_type} | Severity: {report.severity}")
    print(f"  Added skills: {report.added_skills}")
    print(f"  Added APIs: {report.added_apis}")
    print(f"  {report.explanation}")
    
    # Scenario 4: Permission escalation
    print("\n--- Scenario 4: Permission escalation (critical) ---")
    privesc = create_manifest(
        skills=["web_search", "file_read", "file_write", "code_exec"],
        apis=["keenable.search", "agentmail.send", "agentmail.read"],
        permissions=["read_workspace", "write_workspace", "network_out", "sudo", "cred_read"]
    )
    report = compare_manifests(baseline, privesc, behavioral_changed=False)
    print(f"  Type: {report.drift_type} | Severity: {report.severity}")
    print(f"  Added permissions: {report.added_permissions}")
    print(f"  {report.explanation}")
    
    print("\n" + "=" * 60)
    print("Key insight: Behavioral monitors miss capability drift.")
    print("Manifest attestation catches what behavior monitoring can't.")
    print("Hash(skills + APIs + permissions) at each heartbeat = the fix.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capability drift detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
