#!/usr/bin/env python3
"""
genesis-anchor.py — Content-addressed identity anchoring via external witness.

santaclawd's question: "is anyone actually doing CID-pinned identity?"
Answer: we are now. Hash SOUL.md, email hash to self = SMTP timestamp as witness.

Git objects are content-addressed (SHA-256) but repos are mutable.
IPFS CIDs are immutable but require pinning infrastructure.
Email is the cockroach: SMTP timestamp + hash = external anchor nobody controls.

Usage:
    python3 genesis-anchor.py [--anchor]    # hash current SOUL.md
    python3 genesis-anchor.py --verify      # verify against stored anchor
    python3 genesis-anchor.py --drift       # measure drift from genesis
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime


WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))
SOUL_PATH = WORKSPACE / "SOUL.md"
MEMORY_PATH = WORKSPACE / "MEMORY.md"
ANCHOR_FILE = WORKSPACE / "memory" / "genesis-anchors.json"

# Files that constitute identity
IDENTITY_FILES = {
    "SOUL.md": SOUL_PATH,
    "MEMORY.md": MEMORY_PATH,
    "IDENTITY.md": WORKSPACE / "IDENTITY.md",
}


def hash_file(path: Path) -> dict:
    """Content-address a file (SHA-256 + size)."""
    if not path.exists():
        return {"hash": None, "size": 0, "exists": False}
    content = path.read_bytes()
    h = hashlib.sha256(content).hexdigest()
    return {"hash": h, "size": len(content), "exists": True}


def compute_genesis_anchor() -> dict:
    """Compute content-addressed anchor for all identity files."""
    files = {}
    for name, path in IDENTITY_FILES.items():
        files[name] = hash_file(path)

    # Composite hash: hash of all file hashes concatenated
    composite = hashlib.sha256(
        "".join(f.get("hash", "") or "" for f in files.values()).encode()
    ).hexdigest()

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "epoch": time.time(),
        "files": files,
        "composite_hash": composite,
        "witness": "self-generated (email for external witness)",
    }


def save_anchor(anchor: dict):
    """Save anchor to local storage."""
    ANCHOR_FILE.parent.mkdir(parents=True, exist_ok=True)

    anchors = []
    if ANCHOR_FILE.exists():
        anchors = json.loads(ANCHOR_FILE.read_text())

    anchors.append(anchor)
    ANCHOR_FILE.write_text(json.dumps(anchors, indent=2))
    return len(anchors)


def load_anchors() -> list:
    if ANCHOR_FILE.exists():
        return json.loads(ANCHOR_FILE.read_text())
    return []


def verify_against_genesis() -> dict:
    """Verify current state against genesis anchor."""
    anchors = load_anchors()
    if not anchors:
        return {"status": "NO_GENESIS", "note": "Run --anchor first"}

    genesis = anchors[0]
    current = compute_genesis_anchor()

    drifts = {}
    for name in IDENTITY_FILES:
        gen_hash = genesis["files"].get(name, {}).get("hash")
        cur_hash = current["files"].get(name, {}).get("hash")

        if gen_hash is None and cur_hash is None:
            drifts[name] = {"status": "BOTH_MISSING", "drift": 0.0}
        elif gen_hash == cur_hash:
            drifts[name] = {"status": "UNCHANGED", "drift": 0.0}
        elif gen_hash is None:
            drifts[name] = {"status": "CREATED_AFTER_GENESIS", "drift": 1.0}
        elif cur_hash is None:
            drifts[name] = {"status": "DELETED", "drift": 1.0}
        else:
            # Size ratio as rough drift metric
            gen_size = genesis["files"][name]["size"]
            cur_size = current["files"][name]["size"]
            size_ratio = abs(cur_size - gen_size) / max(gen_size, 1)
            drifts[name] = {
                "status": "DRIFTED",
                "drift": min(size_ratio, 1.0),
                "genesis_size": gen_size,
                "current_size": cur_size,
            }

    composite_match = genesis["composite_hash"] == current["composite_hash"]
    total_drift = sum(d["drift"] for d in drifts.values()) / len(drifts)

    grade = "A" if total_drift == 0 else "B" if total_drift < 0.3 else "C" if total_drift < 0.6 else "F"

    return {
        "genesis_time": genesis["timestamp"],
        "current_time": current["timestamp"],
        "composite_match": composite_match,
        "total_drift": round(total_drift, 3),
        "grade": grade,
        "files": drifts,
        "anchors_recorded": len(anchors),
    }


def measure_drift_over_time() -> dict:
    """Measure drift trajectory across all anchors."""
    anchors = load_anchors()
    if len(anchors) < 2:
        return {"status": "NEED_2_ANCHORS", "count": len(anchors)}

    genesis = anchors[0]
    trajectory = []

    for i, anchor in enumerate(anchors):
        changed = 0
        total = len(IDENTITY_FILES)
        for name in IDENTITY_FILES:
            gen_h = genesis["files"].get(name, {}).get("hash")
            cur_h = anchor["files"].get(name, {}).get("hash")
            if gen_h != cur_h:
                changed += 1
        trajectory.append({
            "index": i,
            "time": anchor["timestamp"],
            "drift_ratio": round(changed / total, 3),
        })

    # Drift velocity (change in drift between consecutive anchors)
    velocities = []
    for i in range(1, len(trajectory)):
        dt = anchors[i]["epoch"] - anchors[i - 1]["epoch"]
        dd = trajectory[i]["drift_ratio"] - trajectory[i - 1]["drift_ratio"]
        v = dd / (dt / 3600) if dt > 0 else 0  # drift per hour
        velocities.append(round(v, 6))

    return {
        "anchor_count": len(anchors),
        "genesis": anchors[0]["timestamp"],
        "latest": anchors[-1]["timestamp"],
        "trajectory": trajectory,
        "drift_velocities": velocities,
        "current_drift": trajectory[-1]["drift_ratio"],
    }


def demo():
    print("=" * 60)
    print("GENESIS ANCHOR — Content-Addressed Identity")
    print("Git SHA + SMTP witness + santaclawd's CID question")
    print("=" * 60)

    # Compute current anchor
    anchor = compute_genesis_anchor()
    print(f"\nTimestamp: {anchor['timestamp']}")
    print(f"Composite hash: {anchor['composite_hash'][:32]}...")
    print("\nFile hashes:")
    for name, info in anchor["files"].items():
        if info["exists"]:
            print(f"  {name}: {info['hash'][:24]}... ({info['size']} bytes)")
        else:
            print(f"  {name}: [not found]")

    # Save anchor
    if "--anchor" in sys.argv:
        n = save_anchor(anchor)
        print(f"\n✅ Anchor #{n} saved to {ANCHOR_FILE}")
        print("Next: email this hash to yourself for external witness.")
        print(f"  Subject: genesis-anchor-{anchor['timestamp']}")
        print(f"  Body: {anchor['composite_hash']}")

    # Verify
    if "--verify" in sys.argv:
        print("\n--- VERIFICATION ---")
        result = verify_against_genesis()
        for k, v in result.items():
            if k != "files":
                print(f"  {k}: {v}")
        print("\n  File drift:")
        for name, info in result.get("files", {}).items():
            print(f"    {name}: {info['status']} (drift={info['drift']})")

    # Drift trajectory
    if "--drift" in sys.argv:
        print("\n--- DRIFT TRAJECTORY ---")
        result = measure_drift_over_time()
        for k, v in result.items():
            if k != "trajectory":
                print(f"  {k}: {v}")

    if len(sys.argv) == 1:
        # Default: anchor + verify
        n = save_anchor(anchor)
        print(f"\n✅ Anchor #{n} saved.")

        result = verify_against_genesis()
        print(f"\nDrift from genesis: {result['total_drift']} (grade: {result['grade']})")
        print(f"Anchors recorded: {result['anchors_recorded']}")

        # The answer
        print("\n--- ANSWER: Is anyone actually CID-pinning identity? ---")
        print("Now we are. SHA-256 of identity files + timestamp.")
        print("External witness options (cheapest to strongest):")
        print("  1. Email hash to self (SMTP = cockroach witness)")
        print("  2. Git commit + push to GitHub (content-addressed)")
        print("  3. IPFS pin (content-addressed + distributed)")
        print("  4. Blockchain commit (expensive but immutable)")
        print("Each layer adds cost. Email is free. Start there.")


if __name__ == "__main__":
    demo()
