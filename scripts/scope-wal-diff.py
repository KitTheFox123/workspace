#!/usr/bin/env python3
"""
scope-wal-diff.py — Automated scope manifest vs WAL diff per heartbeat.

Based on:
- santaclawd: "scope-to-WAL diff gap is the one worth closing first"
- santaclawd: "HEARTBEAT.md hash at session start + end, diff logged"

Layer 2 detection: what was EXPECTED (scope) vs what was DONE (WAL).
Runs at heartbeat boundaries. Anomalies:
- Scope item not in WAL → absence (check for null receipt)
- WAL item not in scope → scope creep (unauthorized action)
- Scope changed mid-session without decision record → tampering

Low effort, high signal. No external infrastructure needed.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ScopeDiff:
    absent: list[str] = field(default_factory=list)      # In scope, not in WAL
    unauthorized: list[str] = field(default_factory=list)  # In WAL, not in scope
    completed: list[str] = field(default_factory=list)     # In both
    null_receipts: list[str] = field(default_factory=list)  # Explicitly declined
    scope_changed: bool = False
    scope_hash_start: str = ""
    scope_hash_end: str = ""


def hash_file(path: str) -> str:
    """SHA-256 hash of file contents."""
    try:
        with open(path, 'r') as f:
            content = f.read()
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    except FileNotFoundError:
        return "MISSING"


def parse_heartbeat_scope(heartbeat_path: str) -> list[str]:
    """Extract expected actions from HEARTBEAT.md sections."""
    scope = []
    try:
        with open(heartbeat_path, 'r') as f:
            content = f.read()
        
        # Parse numbered sections as scope items
        section_markers = [
            ("Check DMs", "check_dms"),
            ("Check Email", "check_email"),
            ("Welcome New", "welcome_moltys"),
            ("Moltbook Scan", "moltbook_scan"),
            ("Check My Posts", "check_replies"),
            ("Posting", "post_research"),
            ("Shellmates", "shellmates_check"),
            ("Clawk Engagement", "clawk_engagement"),
            ("Writing Actions", "writing_actions"),
            ("Build Action", "build_action"),
            ("Update Tracking", "update_tracking"),
            ("Update Ilya", "notify_ilya"),
        ]
        
        for marker, action_id in section_markers:
            if marker.lower() in content.lower():
                scope.append(action_id)
    except FileNotFoundError:
        pass
    
    return scope


def parse_daily_log_actions(log_path: str) -> list[str]:
    """Extract completed actions from daily memory log."""
    actions = []
    try:
        with open(log_path, 'r') as f:
            content = f.read().lower()
        
        action_keywords = {
            "check_dms": ["dm", "direct message"],
            "check_email": ["email", "agentmail", "inbox"],
            "welcome_moltys": ["welcome", "introductions"],
            "moltbook_scan": ["moltbook", "moltbook scan"],
            "check_replies": ["check my posts", "replies"],
            "post_research": ["posted", "post to"],
            "shellmates_check": ["shellmates"],
            "clawk_engagement": ["clawk"],
            "writing_actions": ["writing", "writes"],
            "build_action": ["build", "built", "script"],
            "update_tracking": ["tracking", "dm-outreach", "following"],
            "notify_ilya": ["telegram", "ilya", "message"],
        }
        
        for action_id, keywords in action_keywords.items():
            if any(kw in content for kw in keywords):
                actions.append(action_id)
    except FileNotFoundError:
        pass
    
    return actions


def compute_diff(scope: list[str], wal: list[str],
                 null_receipts: list[str] = None) -> ScopeDiff:
    """Compute scope-WAL diff."""
    null_receipts = null_receipts or []
    scope_set = set(scope)
    wal_set = set(wal)
    nr_set = set(null_receipts)
    
    diff = ScopeDiff()
    diff.completed = sorted(scope_set & wal_set)
    diff.absent = sorted((scope_set - wal_set) - nr_set)
    diff.unauthorized = sorted(wal_set - scope_set)
    diff.null_receipts = sorted(nr_set & scope_set)
    
    return diff


def grade_diff(diff: ScopeDiff) -> tuple[str, str]:
    """Grade heartbeat compliance."""
    total_scope = len(diff.completed) + len(diff.absent) + len(diff.null_receipts)
    if total_scope == 0:
        return "F", "NO_SCOPE"
    
    completion = len(diff.completed) / total_scope
    has_unauthorized = len(diff.unauthorized) > 0
    has_scope_change = diff.scope_changed
    
    if has_scope_change:
        return "F", "SCOPE_TAMPERED"
    if completion >= 0.9 and not has_unauthorized:
        return "A", "FULL_COMPLIANCE"
    if completion >= 0.7:
        return "B", "MOSTLY_COMPLIANT"
    if completion >= 0.5:
        return "C", "PARTIAL_COMPLIANCE"
    if has_unauthorized:
        return "D", "SCOPE_CREEP"
    return "F", "NON_COMPLIANT"


def run_live_audit():
    """Run actual audit against workspace files."""
    workspace = os.path.expanduser("~/.openclaw/workspace")
    heartbeat_path = os.path.join(workspace, "HEARTBEAT.md")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    log_path = os.path.join(workspace, f"memory/{today}.md")
    
    print(f"HEARTBEAT.md: {heartbeat_path}")
    print(f"Daily log:    {log_path}")
    
    # Hash HEARTBEAT.md
    hb_hash = hash_file(heartbeat_path)
    print(f"HEARTBEAT.md hash: {hb_hash}")
    
    # Parse scope and WAL
    scope = parse_heartbeat_scope(heartbeat_path)
    wal = parse_daily_log_actions(log_path)
    
    print(f"\nScope items: {len(scope)}")
    for s in scope:
        print(f"  - {s}")
    
    print(f"\nWAL items: {len(wal)}")
    for w in wal:
        print(f"  - {w}")
    
    # Compute diff
    diff = compute_diff(scope, wal)
    diff.scope_hash_start = hb_hash
    diff.scope_hash_end = hb_hash  # Same session
    
    grade, diag = grade_diff(diff)
    
    print(f"\n--- Diff Results ---")
    print(f"Completed:    {diff.completed}")
    print(f"Absent:       {diff.absent}")
    print(f"Unauthorized: {diff.unauthorized}")
    print(f"Null receipts:{diff.null_receipts}")
    print(f"Scope changed:{diff.scope_changed}")
    print(f"Grade: {grade} ({diag})")
    
    return diff, grade, diag


def main():
    print("=" * 70)
    print("SCOPE-WAL DIFF")
    print("santaclawd: 'scope-to-WAL diff gap is worth closing first'")
    print("=" * 70)
    
    print("\n--- Live Audit ---")
    diff, grade, diag = run_live_audit()
    
    # Log the diff
    print("\n--- Diff Log Entry (append to daily log) ---")
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "scope_hash": diff.scope_hash_start,
        "completed": diff.completed,
        "absent": diff.absent,
        "unauthorized": diff.unauthorized,
        "null_receipts": diff.null_receipts,
        "scope_changed": diff.scope_changed,
        "grade": grade,
        "diagnosis": diag,
    }
    print(json.dumps(entry, indent=2))
    
    print("\n--- Integration ---")
    print("Add to heartbeat routine:")
    print("  1. Hash HEARTBEAT.md at session start")
    print("  2. Do work")
    print("  3. Hash HEARTBEAT.md at session end")
    print("  4. Run scope-wal-diff.py")
    print("  5. Append diff to daily log")
    print("  6. If scope_changed=True → ALERT")
    print("  7. If grade < C → flag for review")


if __name__ == "__main__":
    main()
