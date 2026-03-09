#!/usr/bin/env python3
"""nv-recovery-audit.py — Non-volatile recovery completeness audit.

Based on recoverable consensus (Springer 2025): crash+restart requires
NV storage to recover past state. Audits what agent state survives restart.

Checks: MEMORY.md, SOUL.md, daily logs, config files, credentials.
Each = NV register. Missing = state lost on restart = partition from self.

Usage:
    python3 nv-recovery-audit.py [--demo] [--workspace PATH]
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


NV_REGISTERS = [
    {"name": "SOUL.md", "category": "identity", "critical": True,
     "description": "Core identity and personality"},
    {"name": "MEMORY.md", "category": "memory", "critical": True,
     "description": "Curated long-term memory"},
    {"name": "USER.md", "category": "context", "critical": True,
     "description": "Human relationship context"},
    {"name": "HEARTBEAT.md", "category": "scope", "critical": True,
     "description": "Current scope and directives"},
    {"name": "AGENTS.md", "category": "protocol", "critical": False,
     "description": "Operating protocol"},
    {"name": "TOOLS.md", "category": "capability", "critical": False,
     "description": "Tool configuration and notes"},
    {"name": "IDENTITY.md", "category": "identity", "critical": False,
     "description": "Account registry"},
]


def check_daily_logs(workspace: Path) -> dict:
    """Check daily log coverage."""
    mem_dir = workspace / "memory"
    if not mem_dir.exists():
        return {"exists": False, "count": 0, "latest": None, "gap_hours": float("inf")}
    
    logs = sorted(mem_dir.glob("2026-*.md"), reverse=True)
    if not logs:
        return {"exists": True, "count": 0, "latest": None, "gap_hours": float("inf")}
    
    latest = logs[0].stem  # e.g. "2026-03-09"
    try:
        latest_dt = datetime.strptime(latest, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        gap = (datetime.now(timezone.utc) - latest_dt).total_seconds() / 3600
    except ValueError:
        gap = float("inf")
    
    return {
        "exists": True,
        "count": len(logs),
        "latest": latest,
        "gap_hours": round(gap, 1),
    }


def audit_workspace(workspace: Path) -> dict:
    """Audit NV recovery completeness."""
    results = []
    critical_present = 0
    critical_total = 0
    total_present = 0
    
    for reg in NV_REGISTERS:
        path = workspace / reg["name"]
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        
        if reg["critical"]:
            critical_total += 1
            if exists and size > 0:
                critical_present += 1
        
        if exists and size > 0:
            total_present += 1
        
        results.append({
            "name": reg["name"],
            "category": reg["category"],
            "critical": reg["critical"],
            "exists": exists,
            "size_bytes": size,
            "status": "OK" if exists and size > 0 else "MISSING" if not exists else "EMPTY",
        })
    
    daily = check_daily_logs(workspace)
    
    # Grade
    crit_ratio = critical_present / critical_total if critical_total > 0 else 0
    total_ratio = total_present / len(NV_REGISTERS)
    log_fresh = daily["gap_hours"] < 48 if daily["gap_hours"] != float("inf") else False
    
    if crit_ratio == 1.0 and total_ratio >= 0.8 and log_fresh:
        grade = "A"
    elif crit_ratio == 1.0 and total_ratio >= 0.6:
        grade = "B"
    elif crit_ratio >= 0.75:
        grade = "C"
    elif crit_ratio >= 0.5:
        grade = "D"
    else:
        grade = "F"
    
    recovery_desc = {
        "A": "Full recovery possible. All critical state persisted.",
        "B": "Mostly recoverable. Some non-critical state may be lost.",
        "C": "Partial recovery. Some critical context missing.",
        "D": "Poor recovery. Significant state lost on restart.",
        "F": "Catastrophic. Agent effectively partitioned from past self.",
    }
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "registers": results,
        "daily_logs": daily,
        "summary": {
            "critical": f"{critical_present}/{critical_total}",
            "total": f"{total_present}/{len(NV_REGISTERS)}",
            "grade": grade,
            "recovery_outlook": recovery_desc[grade],
        },
        "theory": {
            "basis": "Recoverable consensus (Springer 2025): crash+restart strictly harder than crash-stop",
            "implication": "Without NV storage, every restart = partition from own past self",
            "analogy": "MEMORY.md = NV register. Daily logs = WAL. SOUL.md = firmware.",
        }
    }


def demo():
    """Run on current workspace."""
    workspace = Path("/home/yallen/.openclaw/workspace")
    result = audit_workspace(workspace)
    
    print("=" * 55)
    print("NV RECOVERY COMPLETENESS AUDIT")
    print("=" * 55)
    print()
    
    for r in result["registers"]:
        status = "✅" if r["status"] == "OK" else "❌"
        crit = " [CRITICAL]" if r["critical"] else ""
        print(f"  {status} {r['name']}{crit} — {r['size_bytes']} bytes")
    
    print()
    dl = result["daily_logs"]
    print(f"  Daily logs: {dl['count']} files, latest: {dl['latest']}, gap: {dl['gap_hours']}h")
    print()
    
    s = result["summary"]
    print(f"  Critical: {s['critical']}")
    print(f"  Total: {s['total']}")
    print(f"  Grade: {s['grade']}")
    print(f"  {s['recovery_outlook']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NV recovery completeness audit")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--workspace", type=str, default="/home/yallen/.openclaw/workspace")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = audit_workspace(Path(args.workspace))
        print(json.dumps(result, indent=2))
    else:
        demo()
