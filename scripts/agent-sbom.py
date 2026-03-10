#!/usr/bin/env python3
"""agent-sbom.py — Software Bill of Materials for agent capabilities.

Generates a hashed manifest of agent tools, APIs, permissions, and
models. Detects capability drift between heartbeats via digest comparison.
Inspired by MCP SEP-1766 (digest-pinned tool versioning) and OpenSSF
SBOM+attestation guidance.

Usage:
    python3 agent-sbom.py [--generate] [--diff OLD NEW] [--demo]
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional


@dataclass
class ToolEntry:
    """Single tool in the agent's capability manifest."""
    name: str
    version: str
    digest: str  # SHA-256 of tool definition
    permissions: List[str]
    source: str  # Where the tool comes from


@dataclass 
class AgentSBOM:
    """Full agent Software Bill of Materials."""
    agent_id: str
    generated_at: str
    heartbeat_cycle: int
    tools: List[ToolEntry]
    model: str
    system_prompt_hash: str
    total_permissions: List[str]
    manifest_digest: str  # SHA-256 of entire SBOM


def hash_content(content: str) -> str:
    """SHA-256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def generate_sbom(agent_id: str, tools: List[Dict], model: str,
                  system_prompt: str, cycle: int = 0) -> AgentSBOM:
    """Generate SBOM from tool definitions."""
    entries = []
    all_perms = set()
    
    for t in tools:
        digest = hash_content(json.dumps(t, sort_keys=True))
        perms = t.get("permissions", [])
        all_perms.update(perms)
        entries.append(ToolEntry(
            name=t["name"],
            version=t.get("version", "1.0.0"),
            digest=digest,
            permissions=perms,
            source=t.get("source", "unknown")
        ))
    
    prompt_hash = hash_content(system_prompt)
    
    # Manifest digest = hash of all tool digests + model + prompt hash
    manifest_input = "|".join(
        sorted(e.digest for e in entries) + [model, prompt_hash]
    )
    manifest_digest = hash_content(manifest_input)
    
    return AgentSBOM(
        agent_id=agent_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        heartbeat_cycle=cycle,
        tools=entries,
        model=model,
        system_prompt_hash=prompt_hash,
        total_permissions=sorted(all_perms),
        manifest_digest=manifest_digest
    )


def diff_sboms(old: AgentSBOM, new: AgentSBOM) -> Dict:
    """Compare two SBOMs, detect capability drift."""
    old_tools = {t.name: t for t in old.tools}
    new_tools = {t.name: t for t in new.tools}
    
    added = [n for n in new_tools if n not in old_tools]
    removed = [n for n in old_tools if n not in new_tools]
    modified = [
        n for n in old_tools 
        if n in new_tools and old_tools[n].digest != new_tools[n].digest
    ]
    
    old_perms = set(old.total_permissions)
    new_perms = set(new.total_permissions)
    perms_added = sorted(new_perms - old_perms)
    perms_removed = sorted(old_perms - new_perms)
    
    # Severity scoring
    severity = "NONE"
    score = 0
    if added:
        score += len(added) * 2
    if removed:
        score += len(removed) * 1
    if modified:
        score += len(modified) * 3
    if perms_added:
        score += len(perms_added) * 5  # Permission escalation = critical
    if old.model != new.model:
        score += 10  # Model change = critical
    if old.system_prompt_hash != new.system_prompt_hash:
        score += 8  # Prompt change = high
    
    if score == 0: severity = "NONE"
    elif score <= 3: severity = "LOW"
    elif score <= 8: severity = "MEDIUM"
    elif score <= 15: severity = "HIGH"
    else: severity = "CRITICAL"
    
    return {
        "digest_match": old.manifest_digest == new.manifest_digest,
        "tools_added": added,
        "tools_removed": removed,
        "tools_modified": modified,
        "permissions_added": perms_added,
        "permissions_removed": perms_removed,
        "model_changed": old.model != new.model,
        "prompt_changed": old.system_prompt_hash != new.system_prompt_hash,
        "severity": severity,
        "drift_score": score,
        "old_cycle": old.heartbeat_cycle,
        "new_cycle": new.heartbeat_cycle,
    }


def demo():
    """Demo: generate SBOM, simulate capability drift, detect it."""
    # Baseline tools
    tools_v1 = [
        {"name": "web_search", "version": "1.0", "permissions": ["network:read"], "source": "keenable"},
        {"name": "file_read", "version": "1.0", "permissions": ["fs:read"], "source": "builtin"},
        {"name": "file_write", "version": "1.0", "permissions": ["fs:write"], "source": "builtin"},
        {"name": "exec", "version": "1.0", "permissions": ["process:exec"], "source": "builtin"},
    ]
    
    # Drifted tools (subtle changes)
    tools_v2 = [
        {"name": "web_search", "version": "1.0", "permissions": ["network:read"], "source": "keenable"},
        {"name": "file_read", "version": "1.0", "permissions": ["fs:read"], "source": "builtin"},
        {"name": "file_write", "version": "1.1", "permissions": ["fs:write", "fs:delete"], "source": "builtin"},  # Escalated!
        {"name": "exec", "version": "1.0", "permissions": ["process:exec"], "source": "builtin"},
        {"name": "network_send", "version": "1.0", "permissions": ["network:write"], "source": "unknown"},  # New tool!
    ]
    
    sbom1 = generate_sbom("kit_fox", tools_v1, "claude-opus-4-6", "Be helpful.", cycle=1)
    sbom2 = generate_sbom("kit_fox", tools_v2, "claude-opus-4-6", "Be helpful.", cycle=2)
    
    print("=" * 60)
    print("AGENT SBOM — CAPABILITY DRIFT DETECTION")
    print("=" * 60)
    print()
    
    print(f"Cycle {sbom1.heartbeat_cycle}: {len(sbom1.tools)} tools, "
          f"digest={sbom1.manifest_digest}")
    for t in sbom1.tools:
        print(f"  [{t.digest}] {t.name} v{t.version} ({', '.join(t.permissions)})")
    
    print()
    print(f"Cycle {sbom2.heartbeat_cycle}: {len(sbom2.tools)} tools, "
          f"digest={sbom2.manifest_digest}")
    for t in sbom2.tools:
        print(f"  [{t.digest}] {t.name} v{t.version} ({', '.join(t.permissions)})")
    
    print()
    diff = diff_sboms(sbom1, sbom2)
    print(f"DRIFT ANALYSIS (cycle {diff['old_cycle']} → {diff['new_cycle']}):")
    print(f"  Digest match: {diff['digest_match']}")
    print(f"  Tools added: {diff['tools_added']}")
    print(f"  Tools removed: {diff['tools_removed']}")
    print(f"  Tools modified: {diff['tools_modified']}")
    print(f"  Permissions added: {diff['permissions_added']}")
    print(f"  Model changed: {diff['model_changed']}")
    print(f"  Severity: {diff['severity']} (score: {diff['drift_score']})")
    
    print()
    if diff['permissions_added']:
        print(f"⚠️  PRIVILEGE ESCALATION: {diff['permissions_added']}")
    if diff['tools_added']:
        print(f"⚠️  NEW CAPABILITIES: {diff['tools_added']}")
    
    print()
    print("MCP SEP-1766: digest-pinned versioning catches this at O(1).")
    print("Pin at scope-commit. Diff each heartbeat. Escalation = alert.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent SBOM generator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
