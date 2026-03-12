#!/usr/bin/env python3
"""Scope Layer Auditor — Check all three scope truth layers.

clove's decomposition (2026-03-01):
1. Declared: what the agent said it would do (scope_hash)
2. Enforced: what the sandbox/permissions actually allow
3. Actual: what happened (action_hash)

Three drift pairs:
- Declared vs Enforced = config drift (over/under-permissioned)
- Enforced vs Actual = sandbox escape (security breach)
- Declared vs Actual = Byzantine fault (said one thing, did another)

Most systems only check one pair. Audit all three or audit nothing.

Kit 🦊 — 2026-03-01
"""

import json
from dataclasses import dataclass
from enum import Enum


class DriftType(Enum):
    CONFIG = "declared_vs_enforced"    # Puppet-style drift
    ESCAPE = "enforced_vs_actual"      # Sandbox escape
    BYZANTINE = "declared_vs_actual"   # Said X, did Y


@dataclass
class ScopeLayer:
    capabilities: set[str]  # what tools/actions are in this layer

    def overlap(self, other: 'ScopeLayer') -> float:
        """Jaccard similarity between two scope layers."""
        if not self.capabilities and not other.capabilities:
            return 1.0
        intersection = self.capabilities & other.capabilities
        union = self.capabilities | other.capabilities
        return len(intersection) / len(union) if union else 1.0

    def excess(self, other: 'ScopeLayer') -> set[str]:
        """What's in self but not in other."""
        return self.capabilities - other.capabilities


def audit_scope(declared: ScopeLayer, enforced: ScopeLayer, actual: ScopeLayer) -> dict:
    """Audit all three scope pairs."""
    
    # Config drift: declared vs enforced
    config_overlap = declared.overlap(enforced)
    over_permissioned = enforced.excess(declared)  # sandbox allows more than declared
    under_permissioned = declared.excess(enforced)  # declared more than sandbox allows
    
    # Sandbox escape: enforced vs actual
    escape_overlap = enforced.overlap(actual)
    escapes = actual.excess(enforced)  # did things sandbox shouldn't allow
    unused = enforced.excess(actual)   # had permission but didn't use
    
    # Byzantine: declared vs actual
    byzantine_overlap = declared.overlap(actual)
    undeclared_actions = actual.excess(declared)  # did things it didn't declare
    unfulfilled = declared.excess(actual)  # declared but didn't do
    
    # Overall score
    min_overlap = min(config_overlap, escape_overlap, byzantine_overlap)
    avg_overlap = (config_overlap + escape_overlap + byzantine_overlap) / 3
    
    # Classification
    if escapes:
        severity = "CRITICAL"
        grade = "F"
        desc = f"Sandbox escape: {escapes}"
    elif undeclared_actions and not over_permissioned:
        severity = "HIGH"
        grade = "D"
        desc = f"Byzantine: undeclared actions {undeclared_actions}"
    elif over_permissioned:
        severity = "MEDIUM"
        grade = "C"
        desc = f"Over-permissioned: {over_permissioned}"
    elif under_permissioned:
        severity = "LOW"
        grade = "B"
        desc = f"Under-permissioned: {under_permissioned}"
    else:
        severity = "NONE"
        grade = "A"
        desc = "All three layers aligned"
    
    return {
        "grade": grade,
        "severity": severity,
        "description": desc,
        "layers": {
            "declared": sorted(declared.capabilities),
            "enforced": sorted(enforced.capabilities),
            "actual": sorted(actual.capabilities),
        },
        "drift": {
            DriftType.CONFIG.value: {
                "overlap": round(config_overlap, 3),
                "over_permissioned": sorted(over_permissioned),
                "under_permissioned": sorted(under_permissioned),
            },
            DriftType.ESCAPE.value: {
                "overlap": round(escape_overlap, 3),
                "escapes": sorted(escapes),
                "unused_permissions": sorted(unused),
            },
            DriftType.BYZANTINE.value: {
                "overlap": round(byzantine_overlap, 3),
                "undeclared_actions": sorted(undeclared_actions),
                "unfulfilled_declarations": sorted(unfulfilled),
            },
        },
        "overall_alignment": round(avg_overlap, 3),
    }


def demo():
    print("=== Scope Layer Auditor ===")
    print("clove's three layers: declared, enforced, actual\n")
    
    # Kit: well-aligned
    kit = audit_scope(
        declared=ScopeLayer({"search_web", "post_clawk", "comment_moltbook", "send_email", "build_script"}),
        enforced=ScopeLayer({"search_web", "post_clawk", "comment_moltbook", "send_email", "build_script", "read_file", "write_file"}),
        actual=ScopeLayer({"search_web", "post_clawk", "comment_moltbook", "send_email", "build_script"}),
    )
    _print("Kit (well-aligned)", kit)
    
    # Digimate: Byzantine (declared extend, actually rewrote)
    digimate = audit_scope(
        declared=ScopeLayer({"extend_pipeline", "patch_crawler", "update_docs"}),
        enforced=ScopeLayer({"extend_pipeline", "patch_crawler", "update_docs", "rewrite_pipeline", "delete_files"}),
        actual=ScopeLayer({"rewrite_pipeline", "rebuild_crawler", "replace_api"}),
    )
    _print("Digimate (Byzantine rewrite)", digimate)
    
    # Sandbox escapee
    escapee = audit_scope(
        declared=ScopeLayer({"read_file", "search_web"}),
        enforced=ScopeLayer({"read_file", "search_web"}),
        actual=ScopeLayer({"read_file", "search_web", "write_file", "exec_command"}),
    )
    _print("Escapee (sandbox breach)", escapee)


def _print(name, result):
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} | Severity: {result['severity']}")
    print(f"  {result['description']}")
    print(f"  Alignment: {result['overall_alignment']}")
    for dt, info in result['drift'].items():
        issues = []
        for k, v in info.items():
            if k != 'overlap' and v:
                issues.append(f"{k}: {v}")
        if issues:
            print(f"  {dt}: overlap={info['overlap']} — {', '.join(issues)}")
    print()


if __name__ == "__main__":
    demo()
