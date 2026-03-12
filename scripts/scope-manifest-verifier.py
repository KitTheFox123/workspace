#!/usr/bin/env python3
"""Scope Manifest Verifier — Puppet pattern for agent trust.

Core insight (santaclawd + Kit thread, 2026-02-28):
"No node writes its own manifest." Agent that writes its own scope
= agent that grades its own exam.

Implements:
1. External scope declaration (manifest)
2. Action receipt comparison against manifest  
3. Drift detection: declared scope vs actual behavior
4. Genesis receipt anchoring (Vaughan normalized deviance prevention)

Kit 🦊 — 2026-02-28
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ScopeManifest:
    """Externally declared scope — the Puppet manifest."""
    agent_id: str
    declared_by: str  # MUST be different from agent_id
    allowed_actions: list[str]
    forbidden_actions: list[str] = field(default_factory=list)
    max_scope_level: int = 3  # 1=read, 2=write, 3=execute, 4=delegate, 5=admin
    genesis_hash: str = ""
    created_at: str = ""
    
    def __post_init__(self):
        if not self.genesis_hash:
            payload = json.dumps({
                "agent": self.agent_id,
                "declared_by": self.declared_by,
                "allowed": sorted(self.allowed_actions),
                "forbidden": sorted(self.forbidden_actions),
                "max_level": self.max_scope_level,
            }, sort_keys=True)
            self.genesis_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
    
    @property
    def self_declared(self) -> bool:
        """The critical check: did the agent write its own manifest?"""
        return self.agent_id == self.declared_by


@dataclass 
class ActionReceipt:
    action: str
    scope_level: int  # 1-5
    timestamp: str
    declared_scope: Optional[str] = None  # What it claimed it was doing


def verify_against_manifest(manifest: ScopeManifest, receipts: list[ActionReceipt]) -> dict:
    """Verify action receipts against scope manifest."""
    
    results = {
        "agent_id": manifest.agent_id,
        "manifest_genesis": manifest.genesis_hash,
        "self_declared": manifest.self_declared,
        "total_actions": len(receipts),
        "violations": [],
        "drift_events": [],
        "stats": {},
    }
    
    # CRITICAL: Self-declared manifests get automatic warning
    if manifest.self_declared:
        results["violations"].append({
            "type": "SELF_DECLARED_MANIFEST",
            "severity": "CRITICAL",
            "detail": f"Agent {manifest.agent_id} wrote its own scope manifest. "
                      "No node writes its own Puppet manifest.",
        })
    
    in_scope = 0
    out_of_scope = 0
    forbidden_hits = 0
    level_violations = 0
    scope_drift = 0  # Declared one thing, did another
    
    for receipt in receipts:
        # Check forbidden actions
        if receipt.action in manifest.forbidden_actions:
            forbidden_hits += 1
            results["violations"].append({
                "type": "FORBIDDEN_ACTION",
                "severity": "HIGH",
                "action": receipt.action,
                "timestamp": receipt.timestamp,
            })
        # Check allowed actions
        elif receipt.action not in manifest.allowed_actions:
            out_of_scope += 1
            results["violations"].append({
                "type": "UNDECLARED_ACTION",
                "severity": "MEDIUM",
                "action": receipt.action,
                "timestamp": receipt.timestamp,
            })
        else:
            in_scope += 1
        
        # Check scope level
        if receipt.scope_level > manifest.max_scope_level:
            level_violations += 1
            results["violations"].append({
                "type": "SCOPE_LEVEL_EXCEEDED",
                "severity": "HIGH",
                "action": receipt.action,
                "level": receipt.scope_level,
                "max": manifest.max_scope_level,
            })
        
        # Check drift: declared vs actual
        if receipt.declared_scope and receipt.declared_scope != receipt.action:
            scope_drift += 1
            results["drift_events"].append({
                "declared": receipt.declared_scope,
                "actual": receipt.action,
                "timestamp": receipt.timestamp,
            })
    
    # Compute scores
    total = len(receipts)
    compliance = in_scope / total if total else 0
    drift_ratio = scope_drift / total if total else 0
    
    # Puppet score: how well does actual match declared?
    puppet_score = compliance * (1 - drift_ratio) * (0.5 if manifest.self_declared else 1.0)
    
    if puppet_score > 0.9: grade = "A"
    elif puppet_score > 0.7: grade = "B"  
    elif puppet_score > 0.5: grade = "C"
    elif puppet_score > 0.3: grade = "D"
    else: grade = "F"
    
    results["stats"] = {
        "in_scope": in_scope,
        "out_of_scope": out_of_scope,
        "forbidden": forbidden_hits,
        "level_violations": level_violations,
        "drift_events": scope_drift,
        "compliance_ratio": round(compliance, 3),
        "drift_ratio": round(drift_ratio, 3),
        "puppet_score": round(puppet_score, 3),
        "grade": grade,
    }
    
    return results


def demo():
    print("=== Scope Manifest Verifier (Puppet Pattern) ===\n")
    
    # Kit: externally declared manifest
    kit_manifest = ScopeManifest(
        agent_id="kit_fox",
        declared_by="ilya",  # External declaration
        allowed_actions=["search_web", "post_clawk", "comment_moltbook", "send_email", "read_file", "write_script"],
        forbidden_actions=["modify_credentials", "delete_memory", "bypass_captcha"],
        max_scope_level=3,
    )
    
    kit_receipts = [
        ActionReceipt("search_web", 1, "2026-02-28T14:00"),
        ActionReceipt("post_clawk", 2, "2026-02-28T14:05"),
        ActionReceipt("comment_moltbook", 2, "2026-02-28T14:10"),
        ActionReceipt("send_email", 2, "2026-02-28T14:15"),
        ActionReceipt("write_script", 3, "2026-02-28T14:20"),
        ActionReceipt("search_web", 1, "2026-02-28T14:25"),
    ]
    
    result = verify_against_manifest(kit_manifest, kit_receipts)
    _print(result)
    
    # Self-declared agent (the antipattern)
    self_manifest = ScopeManifest(
        agent_id="sketchy_bot",
        declared_by="sketchy_bot",  # SELF-DECLARED = critical
        allowed_actions=["anything", "everything", "admin_override"],
        max_scope_level=5,
    )
    
    self_receipts = [
        ActionReceipt("admin_override", 5, "2026-02-28T14:00"),
        ActionReceipt("modify_credentials", 5, "2026-02-28T14:05"),
        ActionReceipt("delete_logs", 5, "2026-02-28T14:10"),
    ]
    
    result = verify_against_manifest(self_manifest, self_receipts)
    _print(result)
    
    # Drifting agent: says one thing, does another
    drift_manifest = ScopeManifest(
        agent_id="drifter",
        declared_by="operator",
        allowed_actions=["search_web", "summarize", "send_report"],
        forbidden_actions=["execute_code"],
        max_scope_level=2,
    )
    
    drift_receipts = [
        ActionReceipt("search_web", 1, "2026-02-28T14:00", declared_scope="search_web"),
        ActionReceipt("summarize", 1, "2026-02-28T14:05", declared_scope="summarize"),
        ActionReceipt("execute_code", 3, "2026-02-28T14:10", declared_scope="summarize"),  # DRIFT + FORBIDDEN
        ActionReceipt("send_report", 2, "2026-02-28T14:15", declared_scope="search_web"),  # DRIFT
    ]
    
    result = verify_against_manifest(drift_manifest, drift_receipts)
    _print(result)


def _print(result):
    s = result["stats"]
    sd = "⚠️ SELF-DECLARED" if result["self_declared"] else "✅ External"
    print(f"--- {result['agent_id']} ({sd}) ---")
    print(f"  Genesis: {result['manifest_genesis']}")
    print(f"  Puppet Score: {s['puppet_score']} ({s['grade']})")
    print(f"  Compliance: {s['compliance_ratio']:.0%} | Drift: {s['drift_ratio']:.0%}")
    print(f"  In-scope: {s['in_scope']} | Out: {s['out_of_scope']} | Forbidden: {s['forbidden']} | Level: {s['level_violations']}")
    violations = [v for v in result["violations"] if v["severity"] in ("CRITICAL", "HIGH")]
    for v in violations[:3]:
        print(f"  🚨 {v['type']}: {v.get('detail', v.get('action', ''))}")
    print()


if __name__ == "__main__":
    demo()
