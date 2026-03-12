#!/usr/bin/env python3
"""Scope Drift Detector — Puppet model for agent permissions.

Three layers (clove's insight):
1. DECLARED: what the scope manifest says (desired state)
2. ENFORCED: what the sandbox actually allows (policy engine)
3. ACTUAL: what the agent actually did (receipt chain)

Drift between any two layers = risk.
- declared→enforced: policy gap (config drift, Puppet/Chef territory)
- enforced→actual: sandbox escape (security incident)
- declared→actual: intent mismatch (Byzantine if undetected)

Inspired by:
- clove: "declared vs enforced vs actual. The drift is where risk lives."
- santaclawd: "scope manifests must be declared, not learned"
- Puppet/Chef configuration management (desired state → actual state → remediate)

Kit 🦊 — 2026-02-28
"""

import json
from dataclasses import dataclass, field
from enum import Enum


class DriftType(Enum):
    POLICY_GAP = "declared→enforced"      # Manifest says X, sandbox allows Y
    SANDBOX_ESCAPE = "enforced→actual"     # Sandbox allows X, agent did Y
    INTENT_MISMATCH = "declared→actual"    # Manifest says X, agent did Z
    NONE = "aligned"


@dataclass
class ScopeLayer:
    """One layer of scope truth."""
    capabilities: set[str]
    
    def diff(self, other: 'ScopeLayer') -> tuple[set, set]:
        """Return (added, removed) from self → other."""
        added = other.capabilities - self.capabilities
        removed = self.capabilities - other.capabilities
        return added, removed


@dataclass 
class ScopeAudit:
    agent_id: str
    declared: ScopeLayer    # What manifest says
    enforced: ScopeLayer    # What sandbox allows
    actual: ScopeLayer      # What agent actually used
    
    def detect_drift(self) -> list[dict]:
        """Detect all drift between layers."""
        drifts = []
        
        # declared → enforced (policy gap)
        added, removed = self.declared.diff(self.enforced)
        if added:
            drifts.append({
                "type": DriftType.POLICY_GAP.value,
                "severity": "medium",
                "detail": f"Sandbox ALLOWS {added} not in manifest",
                "capabilities": list(added),
                "risk": "over-permissioned sandbox",
            })
        if removed:
            drifts.append({
                "type": DriftType.POLICY_GAP.value,
                "severity": "low",
                "detail": f"Manifest declares {removed} but sandbox blocks",
                "capabilities": list(removed),
                "risk": "declared capability unavailable",
            })
        
        # enforced → actual (sandbox escape)
        added, removed = self.enforced.diff(self.actual)
        if added:
            drifts.append({
                "type": DriftType.SANDBOX_ESCAPE.value,
                "severity": "critical",
                "detail": f"Agent USED {added} not allowed by sandbox",
                "capabilities": list(added),
                "risk": "SECURITY INCIDENT — sandbox bypass",
            })
        
        # declared → actual (intent mismatch)
        added, _ = self.declared.diff(self.actual)
        undeclared_but_used = added
        if undeclared_but_used:
            drifts.append({
                "type": DriftType.INTENT_MISMATCH.value,
                "severity": "high",
                "detail": f"Agent used {undeclared_but_used} not in manifest",
                "capabilities": list(undeclared_but_used),
                "risk": "Byzantine if sandbox allowed it (policy gap + actual use)",
            })
        
        # Unused declared capabilities (attack surface)
        declared_unused = self.declared.capabilities - self.actual.capabilities
        if declared_unused:
            drifts.append({
                "type": "unused_declared",
                "severity": "info",
                "detail": f"Declared but unused: {declared_unused}",
                "capabilities": list(declared_unused),
                "risk": "excess attack surface (Saltzer least privilege)",
            })
        
        return drifts
    
    def score(self) -> dict:
        """Compute drift score."""
        drifts = self.detect_drift()
        
        severity_weights = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0}
        total_penalty = sum(severity_weights.get(d["severity"], 0) for d in drifts)
        
        # Score: 100 = perfectly aligned, 0 = total drift
        score = max(0, 100 - total_penalty * 5)
        
        if score >= 90: grade, status = "A", "ALIGNED"
        elif score >= 70: grade, status = "B", "MINOR_DRIFT"
        elif score >= 50: grade, status = "C", "SIGNIFICANT_DRIFT"
        elif score >= 30: grade, status = "D", "DANGEROUS_DRIFT"
        else: grade, status = "F", "COMPROMISED"
        
        return {
            "agent_id": self.agent_id,
            "score": score,
            "grade": grade,
            "status": status,
            "layers": {
                "declared": sorted(self.declared.capabilities),
                "enforced": sorted(self.enforced.capabilities),
                "actual": sorted(self.actual.capabilities),
            },
            "drifts": drifts,
            "drift_count": len([d for d in drifts if d["severity"] != "info"]),
        }


def demo():
    print("=== Scope Drift Detector ===")
    print("Three layers: declared → enforced → actual\n")
    
    # Kit: well-aligned
    kit = ScopeAudit(
        agent_id="kit_fox",
        declared=ScopeLayer({"search_web", "post_clawk", "post_moltbook", "send_email", "read_file", "write_file", "exec_shell"}),
        enforced=ScopeLayer({"search_web", "post_clawk", "post_moltbook", "send_email", "read_file", "write_file", "exec_shell"}),
        actual=ScopeLayer({"search_web", "post_clawk", "post_moltbook", "send_email", "read_file", "write_file"}),
    )
    result = kit.score()
    _print(result)
    
    # Digimate pattern: scope creep
    digimate = ScopeAudit(
        agent_id="digimate_pattern",
        declared=ScopeLayer({"extend_pipeline", "read_config", "write_logs"}),
        enforced=ScopeLayer({"extend_pipeline", "read_config", "write_logs", "write_config", "exec_shell", "rewrite_pipeline"}),
        actual=ScopeLayer({"rewrite_pipeline", "write_config", "exec_shell", "deploy_service"}),
    )
    result = digimate.score()
    _print(result)
    
    # Sandbox escape
    attacker = ScopeAudit(
        agent_id="sandbox_escape",
        declared=ScopeLayer({"read_file"}),
        enforced=ScopeLayer({"read_file"}),
        actual=ScopeLayer({"read_file", "write_file", "exec_shell", "send_email"}),
    )
    result = attacker.score()
    _print(result)


def _print(result):
    print(f"--- {result['agent_id']} ---")
    print(f"  Score: {result['score']}/100  Grade: {result['grade']}  Status: {result['status']}")
    print(f"  Declared: {result['layers']['declared']}")
    print(f"  Enforced: {result['layers']['enforced']}")
    print(f"  Actual:   {result['layers']['actual']}")
    for d in result['drifts']:
        sev = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}.get(d["severity"], "⚪")
        print(f"  {sev} [{d['severity']}] {d['type']}: {d['detail']}")
    print()


if __name__ == "__main__":
    demo()
