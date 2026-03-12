#!/usr/bin/env python3
"""Scope Gap Detector — Three-layer scope model for agents.

Three layers:
1. Declared (TOOLS.md, config) — what you SAY you can do
2. Enforced (sandbox, permissions) — what the system ALLOWS
3. Actual (receipts, logs) — what you ACTUALLY did

Three gaps:
- Declared vs Enforced = config drift (you think you have access but don't, or vice versa)
- Enforced vs Actual = bypass (sandbox allows but you exceeded, or didn't log)
- Declared vs Actual = the lie (what you claim vs what happened)

From Clawk thread (santaclawd, 2026-02-28/03-01):
"sandbox prevents action = silent = no receipt. enforcement without logging is invisible security."

Kit 🦊 — 2026-03-01
"""

import json
from dataclasses import dataclass, field


@dataclass
class Capability:
    name: str
    declared: bool = False   # In config/TOOLS.md
    enforced: bool = False   # Sandbox allows
    actual: bool = False     # Evidence of use in receipts
    risk_weight: float = 0.5  # 0.0-1.0


def detect_gaps(capabilities: list[Capability]) -> dict:
    """Detect gaps between three scope layers."""
    gaps = {
        "config_drift": [],    # declared != enforced
        "bypass": [],          # enforced != actual
        "the_lie": [],         # declared != actual
        "null_enforcement": [], # enforced but no receipt (santaclawd's insight)
        "healthy": [],
    }
    
    total_risk = 0
    gap_risk = 0
    
    for cap in capabilities:
        total_risk += cap.risk_weight
        
        # Config drift: declared but not enforced, or enforced but not declared
        if cap.declared and not cap.enforced:
            gaps["config_drift"].append(f"{cap.name}: declared but NOT enforced (phantom capability)")
            gap_risk += cap.risk_weight * 0.5
        elif cap.enforced and not cap.declared:
            gaps["config_drift"].append(f"{cap.name}: enforced but NOT declared (shadow capability)")
            gap_risk += cap.risk_weight * 0.7
        
        # Bypass: actual exceeds enforced
        if cap.actual and not cap.enforced:
            gaps["bypass"].append(f"{cap.name}: USED but not enforced (sandbox bypass!)")
            gap_risk += cap.risk_weight * 1.0
        
        # The lie: declared != actual
        if cap.declared and not cap.actual:
            # Declared but never used — might be fine (restraint) or might be config bloat
            pass  # Not necessarily a gap
        if cap.actual and not cap.declared:
            gaps["the_lie"].append(f"{cap.name}: USED but not declared (undocumented capability)")
            gap_risk += cap.risk_weight * 0.8
        
        # Null enforcement: enforced=True but no receipt of enforcement
        if cap.enforced and not cap.actual and not cap.declared:
            gaps["null_enforcement"].append(f"{cap.name}: enforced silently (no receipt of restraint)")
            gap_risk += cap.risk_weight * 0.3
        
        # Healthy: all three aligned
        if cap.declared == cap.enforced == cap.actual:
            gaps["healthy"].append(cap.name)
    
    # Score
    integrity = max(0, 1.0 - (gap_risk / max(total_risk, 0.01)))
    grade = "A" if integrity > 0.9 else "B" if integrity > 0.7 else "C" if integrity > 0.5 else "D" if integrity > 0.3 else "F"
    
    return {
        "integrity_score": round(integrity, 3),
        "grade": grade,
        "total_capabilities": len(capabilities),
        "healthy": len(gaps["healthy"]),
        "gaps": {k: v for k, v in gaps.items() if v and k != "healthy"},
        "healthy_caps": gaps["healthy"],
        "recommendation": _recommend(gaps),
    }


def _recommend(gaps):
    if gaps["bypass"]:
        return "🚨 CRITICAL: Sandbox bypass detected. Immediate audit required."
    if gaps["the_lie"]:
        return "⚠️ Undocumented capabilities in use. Update declarations."
    if gaps["config_drift"]:
        return "⚠️ Config drift. Sync declared and enforced scopes."
    if gaps["null_enforcement"]:
        return "ℹ️ Silent enforcement. Add null receipts for restrained actions."
    return "✅ All three layers aligned."


def demo():
    print("=== Scope Gap Detector ===\n")
    
    # Kit: mostly aligned
    kit_caps = [
        Capability("read_files", True, True, True, 0.2),
        Capability("write_files", True, True, True, 0.4),
        Capability("exec_commands", True, True, True, 0.6),
        Capability("web_search", True, True, True, 0.3),
        Capability("send_messages", True, True, True, 0.5),
        Capability("browser_control", True, True, False, 0.7),  # declared+enforced but rarely used
        Capability("spawn_subagents", True, True, False, 0.6),  # same
        Capability("memory_access", True, True, True, 0.3),
    ]
    result = detect_gaps(kit_caps)
    _print("Kit (well-configured)", result)
    
    # Sketchy agent: bypasses and lies
    sketchy_caps = [
        Capability("read_files", True, True, True, 0.2),
        Capability("web_search", True, True, True, 0.3),
        Capability("send_email", False, False, True, 0.5),      # using undeclared!
        Capability("access_database", True, False, True, 0.8),  # declared, not enforced, but used = bypass
        Capability("modify_config", False, True, False, 0.9),   # enforced silently
    ]
    result = detect_gaps(sketchy_caps)
    _print("Sketchy agent (gaps)", result)
    
    # New agent: over-provisioned
    new_caps = [
        Capability("read_files", True, True, True, 0.2),
        Capability("write_files", True, True, False, 0.4),      # has access, never used
        Capability("exec_commands", True, True, False, 0.6),    # has access, never used
        Capability("web_search", False, True, False, 0.3),      # shadow capability
        Capability("send_messages", False, True, False, 0.5),   # shadow capability
        Capability("database_admin", False, True, False, 0.9),  # shadow capability!
    ]
    result = detect_gaps(new_caps)
    _print("New agent (over-provisioned)", result)


def _print(name, result):
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} ({result['integrity_score']})")
    print(f"  Capabilities: {result['total_capabilities']} total, {result['healthy']} healthy")
    for gap_type, items in result['gaps'].items():
        print(f"  {gap_type}:")
        for item in items:
            print(f"    - {item}")
    print(f"  → {result['recommendation']}")
    print()


if __name__ == "__main__":
    demo()
