#!/usr/bin/env python3
"""
heartbeat-scope-diff.py — Detect scope modifications between heartbeats.

Based on:
- santaclawd: "HEARTBEAT.md hash at session start + end, diff logged. 
  If scope changed mid-session without recorded decision = anomaly signal."
- Three detection layers: time (SLA), scope (WAL vs manifest), value (weight vector)

This closes layer 2 (scope) for near-zero cost.
Hash HEARTBEAT.md at boot, hash at end.
If different and no WAL entry explains why → unauthorized scope change.
"""

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


WORKSPACE = Path(os.environ.get("OPENCLAW_WORKSPACE",
                                 os.path.expanduser("~/.openclaw/workspace")))
HEARTBEAT_PATH = WORKSPACE / "HEARTBEAT.md"
WAL_PATH = WORKSPACE / "memory" / "scope-audit.jsonl"


@dataclass
class ScopeSnapshot:
    timestamp: float
    file_hash: str
    file_size: int
    phase: str  # "boot" or "end"


@dataclass  
class ScopeDiff:
    boot_hash: str
    end_hash: str
    changed: bool
    wal_justified: bool  # Was the change recorded in WAL?
    anomaly: bool
    detail: str


def hash_file(path: Path) -> str:
    """SHA-256 of file contents."""
    if not path.exists():
        return "MISSING"
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


def snapshot_scope(phase: str) -> ScopeSnapshot:
    """Take a snapshot of HEARTBEAT.md."""
    h = hash_file(HEARTBEAT_PATH)
    size = HEARTBEAT_PATH.stat().st_size if HEARTBEAT_PATH.exists() else 0
    return ScopeSnapshot(
        timestamp=time.time(),
        file_hash=h,
        file_size=size,
        phase=phase,
    )


def check_wal_for_scope_change(boot: ScopeSnapshot, end: ScopeSnapshot) -> bool:
    """Check if WAL has an entry explaining the scope change."""
    if not WAL_PATH.exists():
        return False
    
    with open(WAL_PATH) as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                # Look for scope change entries between boot and end timestamps
                if (entry.get("type") == "scope_change" and
                    boot.timestamp <= entry.get("timestamp", 0) <= end.timestamp):
                    return True
            except json.JSONDecodeError:
                continue
    return False


def log_scope_event(event: dict):
    """Append to scope audit WAL."""
    WAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WAL_PATH, "a") as f:
        f.write(json.dumps({**event, "timestamp": time.time()}) + "\n")


def diff_scope(boot: ScopeSnapshot, end: ScopeSnapshot) -> ScopeDiff:
    """Compare boot and end snapshots."""
    if boot.file_hash == end.file_hash:
        return ScopeDiff(boot.file_hash, end.file_hash, False, True, False,
                          "No change detected")
    
    wal_justified = check_wal_for_scope_change(boot, end)
    anomaly = not wal_justified
    
    if wal_justified:
        detail = "Scope changed with WAL justification (authorized)"
    else:
        detail = "ANOMALY: Scope changed without WAL entry (unauthorized?)"
    
    return ScopeDiff(boot.file_hash, end.file_hash, True, wal_justified, anomaly, detail)


def demo():
    """Demonstrate scope diff detection."""
    print("=" * 70)
    print("HEARTBEAT SCOPE DIFF")
    print("santaclawd: 'scope changed mid-session = anomaly signal'")
    print("=" * 70)

    # Simulate scenarios
    print("\n--- Scenario 1: No change (normal) ---")
    boot1 = ScopeSnapshot(1000, "abc123def456", 2048, "boot")
    end1 = ScopeSnapshot(2200, "abc123def456", 2048, "end")
    diff1 = diff_scope(boot1, end1)
    print(f"  Changed: {diff1.changed}, Anomaly: {diff1.anomaly}")
    print(f"  Detail: {diff1.detail}")

    print("\n--- Scenario 2: Authorized change (scope expanded) ---")
    boot2 = ScopeSnapshot(1000, "abc123def456", 2048, "boot")
    end2 = ScopeSnapshot(2200, "xyz789abc012", 2200, "end")
    # Simulate WAL entry
    WAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WAL_PATH, "w") as f:
        f.write(json.dumps({
            "type": "scope_change",
            "timestamp": 1500,
            "reason": "Added new capability: moderate_content",
            "old_hash": "abc123def456",
            "new_hash": "xyz789abc012",
        }) + "\n")
    diff2 = diff_scope(boot2, end2)
    print(f"  Changed: {diff2.changed}, WAL justified: {diff2.wal_justified}")
    print(f"  Detail: {diff2.detail}")

    print("\n--- Scenario 3: UNAUTHORIZED change (scope narrowed) ---")
    boot3 = ScopeSnapshot(3000, "full_scope_hash", 2048, "boot")
    end3 = ScopeSnapshot(4200, "reduced_scope_h", 1800, "end")
    # Clear WAL for this test
    with open(WAL_PATH, "w") as f:
        pass  # Empty
    diff3 = diff_scope(boot3, end3)
    print(f"  Changed: {diff3.changed}, WAL justified: {diff3.wal_justified}")
    print(f"  Anomaly: {diff3.anomaly}")
    print(f"  Detail: {diff3.detail}")
    print(f"  Size delta: {end3.file_size - boot3.file_size} bytes (scope SHRANK)")

    # Current state
    print("\n--- Current HEARTBEAT.md ---")
    if HEARTBEAT_PATH.exists():
        current_hash = hash_file(HEARTBEAT_PATH)
        current_size = HEARTBEAT_PATH.stat().st_size
        print(f"  Hash: {current_hash}")
        print(f"  Size: {current_size} bytes")
    else:
        print("  NOT FOUND")

    # Integration spec
    print("\n--- Integration: Add to Heartbeat Boot ---")
    print("1. At session start: boot_hash = SHA256(HEARTBEAT.md)[:16]")
    print("2. At session end:   end_hash  = SHA256(HEARTBEAT.md)[:16]")
    print("3. If boot_hash != end_hash:")
    print("   a. Check WAL for scope_change entry → authorized")
    print("   b. No WAL entry → ANOMALY → alert Ilya")
    print("4. Log both hashes to daily memory file")
    print()
    print("Cost: 2 SHA256 calls + 1 file read. ~0ms.")
    print("Signal: catches unauthorized scope modification between heartbeats.")
    print("Closes santaclawd's layer 2 (scope) for near-zero effort.")

    # Cleanup
    if WAL_PATH.exists():
        WAL_PATH.unlink()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "boot":
        snap = snapshot_scope("boot")
        print(json.dumps({"phase": "boot", "hash": snap.file_hash, "size": snap.file_size}))
        log_scope_event({"type": "scope_snapshot", "phase": "boot", "hash": snap.file_hash})
    elif len(sys.argv) > 1 and sys.argv[1] == "end":
        snap = snapshot_scope("end")
        print(json.dumps({"phase": "end", "hash": snap.file_hash, "size": snap.file_size}))
        log_scope_event({"type": "scope_snapshot", "phase": "end", "hash": snap.file_hash})
    else:
        demo()
