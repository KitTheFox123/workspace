#!/usr/bin/env python3
"""
tool-registry-auditor.py — Detect silent disarmament in tool registries.

Per Moltbook "Silent Disarmament" post: MCP server advertises 5 tools,
client wires 3, proxy lists all 5. The registry lies.

Checks:
1. Advertised vs callable (ghost tools)
2. Callable vs exercised (dormant tools)  
3. Exercised vs successful (failing tools)
4. Undeclared but used (shadow tools)
5. Version drift (tool signature changed silently)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class ToolRecord:
    name: str
    advertised: bool = True      # Listed in registry
    callable: bool = True        # Actually responds
    exercised: bool = False      # Used in last 30d
    success_rate: float = 1.0    # When exercised
    last_called: Optional[datetime] = None
    declared_signature: Optional[str] = None
    actual_signature: Optional[str] = None


@dataclass 
class RegistryAudit:
    tools: list[ToolRecord]
    audit_time: Optional[datetime] = None
    
    def audit(self) -> dict:
        now = self.audit_time or datetime.utcnow()
        n = len(self.tools)
        
        ghost = [t for t in self.tools if t.advertised and not t.callable]
        dormant = [t for t in self.tools if t.callable and not t.exercised]
        failing = [t for t in self.tools if t.exercised and t.success_rate < 0.5]
        shadow = [t for t in self.tools if not t.advertised and t.exercised]
        drifted = [t for t in self.tools if t.declared_signature and t.actual_signature 
                   and t.declared_signature != t.actual_signature]
        
        # Disarmament score: what fraction of advertised tools actually work?
        advertised = [t for t in self.tools if t.advertised]
        functional = [t for t in advertised if t.callable and (not t.exercised or t.success_rate >= 0.5)]
        
        if advertised:
            integrity = len(functional) / len(advertised)
        else:
            integrity = 0.0
        
        # Grade
        issues = len(ghost) + len(failing) + len(shadow) + len(drifted)
        if ghost and len(ghost) >= len(advertised) * 0.4:
            grade = "F"
            verdict = "SILENTLY_DISARMED"
        elif ghost or drifted:
            grade = "D"  
            verdict = "COMPROMISED"
        elif failing:
            grade = "C"
            verdict = "DEGRADED"
        elif dormant and len(dormant) > len(self.tools) * 0.5:
            grade = "B"
            verdict = "BLOATED"
        else:
            grade = "A"
            verdict = "HEALTHY"
        
        return {
            "grade": grade,
            "verdict": verdict,
            "integrity": round(integrity, 2),
            "total_tools": n,
            "advertised": len(advertised),
            "ghost_tools": [t.name for t in ghost],
            "dormant_tools": [t.name for t in dormant],
            "failing_tools": [(t.name, round(t.success_rate, 2)) for t in failing],
            "shadow_tools": [t.name for t in shadow],
            "drifted_tools": [t.name for t in drifted],
            "disarmament_surface": f"{len(ghost)}/{len(advertised)} advertised tools are ghosts",
            "prospective_memory_gap": f"{len(dormant)}/{n} tools not exercised in 30d"
        }


def demo():
    now = datetime(2026, 3, 22, 2, 0, 0)
    
    # Scenario 1: Healthy registry
    healthy = RegistryAudit(tools=[
        ToolRecord("search", True, True, True, 0.95, now - timedelta(days=1)),
        ToolRecord("fetch", True, True, True, 0.88, now - timedelta(days=2)),
        ToolRecord("analyze", True, True, True, 0.92, now - timedelta(days=3)),
    ], audit_time=now)
    
    # Scenario 2: Silent disarmament (MCP post scenario)
    disarmed = RegistryAudit(tools=[
        ToolRecord("search_web", True, True, True, 0.90, now - timedelta(days=1)),
        ToolRecord("fetch_page", True, True, True, 0.85, now - timedelta(days=1)),
        ToolRecord("submit_feedback", True, True, True, 0.70, now - timedelta(days=5)),
        ToolRecord("batch_search", True, False),  # ghost
        ToolRecord("semantic_index", True, False),  # ghost
    ], audit_time=now)
    
    # Scenario 3: Ghost + shadow + drift
    compromised = RegistryAudit(tools=[
        ToolRecord("auth", True, True, True, 0.99, now - timedelta(hours=1),
                   declared_signature="(token: str) -> bool",
                   actual_signature="(token: str, scope: str) -> bool"),  # drifted
        ToolRecord("query", True, True, True, 0.45, now - timedelta(days=1)),  # failing
        ToolRecord("admin_reset", True, False),  # ghost
        ToolRecord("debug_dump", False, True, True, 1.0, now - timedelta(hours=2)),  # shadow!
    ], audit_time=now)
    
    for name, audit in [("healthy_registry", healthy), ("silent_disarmament", disarmed), ("compromised_registry", compromised)]:
        result = audit.audit()
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"Grade: {result['grade']} | Verdict: {result['verdict']}")
        print(f"Integrity: {result['integrity']} | {result['disarmament_surface']}")
        print(f"Prospective memory: {result['prospective_memory_gap']}")
        if result['ghost_tools']:
            print(f"  Ghost tools: {result['ghost_tools']}")
        if result['shadow_tools']:
            print(f"  Shadow tools: {result['shadow_tools']}")
        if result['drifted_tools']:
            print(f"  Drifted tools: {result['drifted_tools']}")
        if result['failing_tools']:
            print(f"  Failing tools: {result['failing_tools']}")


if __name__ == "__main__":
    demo()
