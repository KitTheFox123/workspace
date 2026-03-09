#!/usr/bin/env python3
"""mandatory-disclosure-checker.py — SOX 302 model for agent action manifests.

Maps SOX mandatory disclosure to agent accountability:
- SOX 302: CEO personally certifies financial reports
- Agent: Principal signs action manifest hash
- Omission becomes provable: declared X, logs show not-X

Inspired by santaclawd's Enron/mandatory disclosure insight.

Usage:
    python3 mandatory-disclosure-checker.py [--demo] [--check MANIFEST LOG]
"""

import argparse
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ManifestEntry:
    """Declared action in the manifest (what SHOULD happen)."""
    action: str
    frequency: str  # "every_beat", "daily", "weekly"
    category: str
    required: bool = True


@dataclass
class LogEntry:
    """Actual action logged (what DID happen)."""
    action: str
    timestamp: str
    category: str


@dataclass
class DisclosureGap:
    """Gap between declared and actual."""
    action: str
    gap_type: str  # "omission" | "undeclared" | "frequency_violation"
    severity: str  # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    sox_parallel: str
    detail: str


def check_disclosure(manifest: List[ManifestEntry], log: List[LogEntry]) -> dict:
    """Compare declared manifest against actual log."""
    gaps = []
    log_actions = {e.action for e in log}
    manifest_actions = {e.action for e in manifest}
    
    # Omissions: declared but not done
    for m in manifest:
        if m.action not in log_actions and m.required:
            gaps.append(DisclosureGap(
                action=m.action,
                gap_type="omission",
                severity="CRITICAL" if m.frequency == "every_beat" else "HIGH",
                sox_parallel="SOX 302(a)(4): material weakness in internal controls",
                detail=f"Declared '{m.action}' ({m.frequency}) but no log entry found"
            ))
    
    # Undeclared: done but not in manifest
    for l in log:
        if l.action not in manifest_actions:
            gaps.append(DisclosureGap(
                action=l.action,
                gap_type="undeclared",
                severity="HIGH",
                sox_parallel="SOX 302(a)(5)(B): fraud involving management",
                detail=f"Action '{l.action}' executed but not in signed manifest"
            ))
    
    # Compute manifest hash
    manifest_str = json.dumps([asdict(m) for m in manifest], sort_keys=True)
    manifest_hash = hashlib.sha256(manifest_str.encode()).hexdigest()[:16]
    
    # Grade
    total = len(manifest)
    omissions = sum(1 for g in gaps if g.gap_type == "omission")
    undeclared = sum(1 for g in gaps if g.gap_type == "undeclared")
    
    if total == 0:
        coverage = 0.0
    else:
        coverage = (total - omissions) / total
    
    if coverage >= 0.95 and undeclared == 0:
        grade = "A"
    elif coverage >= 0.80 and undeclared <= 1:
        grade = "B"
    elif coverage >= 0.60:
        grade = "C"
    elif coverage >= 0.40:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "manifest_hash": manifest_hash,
        "declared_actions": total,
        "executed_actions": len(log_actions),
        "omissions": omissions,
        "undeclared_actions": undeclared,
        "coverage": round(coverage, 3),
        "grade": grade,
        "gaps": [asdict(g) for g in gaps],
        "sox_mapping": {
            "302a1": "Principal reviewed action manifest within reporting period",
            "302a2": "No untrue statements of material fact (undeclared actions)",
            "302a3": "Manifest fairly presents agent's operational scope",
            "302a4": "Principal responsible for establishing internal controls",
            "302a5B": "Any fraud involving management disclosed to auditors",
        },
        "recommendation": (
            "All actions declared and executed" if grade == "A"
            else f"{omissions} omissions, {undeclared} undeclared — "
                 f"{'re-sign manifest' if omissions > 0 else 'declare missing actions'}"
        )
    }


def demo():
    """Run demo with HEARTBEAT.md-style manifest."""
    manifest = [
        ManifestEntry("check_clawk", "every_beat", "platform"),
        ManifestEntry("check_email", "every_beat", "platform"),
        ManifestEntry("check_moltbook_dms", "every_beat", "platform"),
        ManifestEntry("check_shellmates", "every_beat", "platform"),
        ManifestEntry("write_action_1", "every_beat", "engagement"),
        ManifestEntry("write_action_2", "every_beat", "engagement"),
        ManifestEntry("write_action_3", "every_beat", "engagement"),
        ManifestEntry("build_action", "every_beat", "development"),
        ManifestEntry("research", "every_beat", "learning"),
        ManifestEntry("notify_ilya", "every_beat", "reporting"),
        ManifestEntry("update_memory", "every_beat", "maintenance"),
    ]
    
    # Scenario 1: Compliant agent
    log_good = [
        LogEntry(a.action, "2026-03-09T12:00:00Z", a.category)
        for a in manifest
    ]
    
    # Scenario 2: Agent with omissions
    log_gaps = [
        LogEntry("check_clawk", "2026-03-09T12:00:00Z", "platform"),
        LogEntry("write_action_1", "2026-03-09T12:01:00Z", "engagement"),
        LogEntry("build_action", "2026-03-09T12:02:00Z", "development"),
        LogEntry("secret_api_call", "2026-03-09T12:03:00Z", "unknown"),
    ]
    
    print("=" * 60)
    print("MANDATORY DISCLOSURE CHECKER (SOX 302 MODEL)")
    print("=" * 60)
    
    for name, log in [("Compliant Agent", log_good), ("Gap Agent", log_gaps)]:
        result = check_disclosure(manifest, log)
        print(f"\n--- {name} ---")
        print(f"Grade: {result['grade']}")
        print(f"Coverage: {result['coverage']:.0%}")
        print(f"Omissions: {result['omissions']}")
        print(f"Undeclared: {result['undeclared_actions']}")
        if result['gaps']:
            print("Gaps:")
            for g in result['gaps'][:5]:
                print(f"  [{g['severity']}] {g['gap_type']}: {g['action']}")
                print(f"    SOX: {g['sox_parallel']}")
        print(f"Recommendation: {result['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SOX 302 mandatory disclosure for agents")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        manifest = [
            ManifestEntry("check_clawk", "every_beat", "platform"),
            ManifestEntry("check_email", "every_beat", "platform"),
            ManifestEntry("build_action", "every_beat", "development"),
        ]
        log = [LogEntry("check_clawk", "2026-03-09T12:00:00Z", "platform")]
        print(json.dumps(check_disclosure(manifest, log), indent=2))
    else:
        demo()
