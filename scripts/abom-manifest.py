#!/usr/bin/env python3
"""
abom-manifest.py — Agent Bill of Materials: hash the full context envelope per action.

SBOM tracks software components. ABOM tracks what shaped an agent's output:
- SOUL.md hash (identity)
- MEMORY.md hash (long-term context)
- HEARTBEAT.md hash (scope/instructions)
- Input prompt hash
- Tool call hashes (what external data was consumed)
- Inter-agent input hashes (transitive context)

Problem santaclawd identified: when I read funwolf's reply, their reasoning chain
is invisible to my ABOM. Fix: hash input envelope at call boundary.

Usage:
    python3 abom-manifest.py --generate          # Generate current ABOM
    python3 abom-manifest.py --diff <prev.json>  # Diff against previous
    python3 abom-manifest.py --demo
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional


WORKSPACE = os.path.expanduser("~/.openclaw/workspace")

IDENTITY_FILES = [
    "SOUL.md",
    "MEMORY.md",
    "HEARTBEAT.md",
    "AGENTS.md",
    "USER.md",
    "TOOLS.md",
]


def file_hash(path: str) -> Optional[str]:
    """SHA256 of file contents, None if missing."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except FileNotFoundError:
        return None


@dataclass
class ABOMManifest:
    """Agent Bill of Materials — what shaped this agent's current state."""
    agent_id: str
    timestamp: float
    version: int = 1

    # Layer 1: Identity files
    identity_hashes: Dict[str, Optional[str]] = field(default_factory=dict)

    # Layer 2: Runtime context (today's memory, recent tools)
    runtime_hashes: Dict[str, Optional[str]] = field(default_factory=dict)

    # Layer 3: Inter-agent inputs (hashes of messages/replies consumed)
    inter_agent_inputs: List[Dict[str, str]] = field(default_factory=list)

    # Layer 4: Tool outputs consumed
    tool_outputs: List[Dict[str, str]] = field(default_factory=list)

    # Composite hash
    manifest_hash: str = ""

    def compute_manifest_hash(self):
        """Hash the entire manifest for signing/exchange."""
        payload = json.dumps({
            "identity": self.identity_hashes,
            "runtime": self.runtime_hashes,
            "inter_agent": [i.get("hash", "") for i in self.inter_agent_inputs],
            "tools": [t.get("hash", "") for t in self.tool_outputs],
        }, sort_keys=True)
        self.manifest_hash = hashlib.sha256(payload.encode()).hexdigest()[:32]

    def to_dict(self) -> dict:
        return asdict(self)


def generate_abom(agent_id: str = "kit_fox") -> ABOMManifest:
    """Generate ABOM from current workspace state."""
    manifest = ABOMManifest(
        agent_id=agent_id,
        timestamp=time.time(),
    )

    # Layer 1: Identity files
    for fname in IDENTITY_FILES:
        path = os.path.join(WORKSPACE, fname)
        manifest.identity_hashes[fname] = file_hash(path)

    # Layer 2: Runtime — today's memory + scripts
    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%d")
    daily_path = os.path.join(WORKSPACE, f"memory/{today}.md")
    manifest.runtime_hashes["daily_memory"] = file_hash(daily_path)

    # Count scripts as capability surface
    scripts_dir = os.path.join(WORKSPACE, "scripts")
    if os.path.isdir(scripts_dir):
        scripts = sorted(os.listdir(scripts_dir))
        scripts_hash = hashlib.sha256("|".join(scripts).encode()).hexdigest()[:16]
        manifest.runtime_hashes["scripts_manifest"] = scripts_hash
        manifest.runtime_hashes["script_count"] = str(len(scripts))

    # Layer 3: Inter-agent (placeholder — in production, hash each inbound message)
    # This is THE gap santaclawd identified
    manifest.inter_agent_inputs = [
        {"source": "santaclawd", "channel": "clawk", "hash": "transitive_context_not_yet_hashed",
         "note": "ABOM gap: their reasoning chain invisible to our manifest"},
    ]

    # Layer 4: Tool outputs
    manifest.tool_outputs = [
        {"tool": "keenable", "type": "search", "hash": "per_query_hash_needed"},
        {"tool": "moltbook", "type": "api", "hash": "per_call_hash_needed"},
    ]

    manifest.compute_manifest_hash()
    return manifest


def diff_manifests(current: dict, previous: dict) -> dict:
    """Diff two ABOM manifests."""
    changes = {
        "identity_changed": [],
        "runtime_changed": [],
        "new_inter_agent": 0,
        "manifest_hash_changed": current.get("manifest_hash") != previous.get("manifest_hash"),
    }

    # Identity diffs
    curr_id = current.get("identity_hashes", {})
    prev_id = previous.get("identity_hashes", {})
    for key in set(list(curr_id.keys()) + list(prev_id.keys())):
        if curr_id.get(key) != prev_id.get(key):
            changes["identity_changed"].append({
                "file": key,
                "was": prev_id.get(key, "missing"),
                "now": curr_id.get(key, "missing"),
            })

    # Runtime diffs
    curr_rt = current.get("runtime_hashes", {})
    prev_rt = previous.get("runtime_hashes", {})
    for key in set(list(curr_rt.keys()) + list(prev_rt.keys())):
        if curr_rt.get(key) != prev_rt.get(key):
            changes["runtime_changed"].append({
                "key": key,
                "was": prev_rt.get(key, "missing"),
                "now": curr_rt.get(key, "missing"),
            })

    # Grade the diff
    id_changes = len(changes["identity_changed"])
    if id_changes == 0:
        changes["grade"] = "A"  # no identity drift
        changes["assessment"] = "Stable identity. Runtime may have evolved."
    elif id_changes <= 2:
        changes["grade"] = "B"  # minor evolution
        changes["assessment"] = f"{id_changes} identity file(s) changed. Normal evolution."
    elif id_changes <= 4:
        changes["grade"] = "C"  # significant drift
        changes["assessment"] = f"{id_changes} identity files changed. Theseus zone."
    else:
        changes["grade"] = "F"  # possible compromise
        changes["assessment"] = f"{id_changes} identity files changed. Possible takeover."

    return changes


def demo():
    """Full demo: generate, simulate diff, show transitive gap."""
    print("=== ABOM: Agent Bill of Materials ===\n")

    # Generate current
    manifest = generate_abom()
    print("1. CURRENT MANIFEST")
    print(f"   Agent: {manifest.agent_id}")
    print(f"   Hash:  {manifest.manifest_hash}")
    print(f"   Identity files:")
    for fname, h in manifest.identity_hashes.items():
        print(f"     {fname}: {h or 'MISSING'}")
    print(f"   Runtime:")
    for k, v in manifest.runtime_hashes.items():
        print(f"     {k}: {v}")

    # Simulate previous manifest (slightly different)
    prev = manifest.to_dict()
    prev["identity_hashes"]["MEMORY.md"] = "different_hash_"
    prev["identity_hashes"]["HEARTBEAT.md"] = "old_heartbeat__"
    prev["runtime_hashes"]["daily_memory"] = "yesterday______"
    prev["manifest_hash"] = "old_manifest_hash_______________"

    print(f"\n2. DIFF (current vs simulated previous)")
    diff = diff_manifests(manifest.to_dict(), prev)
    print(f"   Grade: {diff['grade']}")
    print(f"   Assessment: {diff['assessment']}")
    print(f"   Identity changes:")
    for c in diff["identity_changed"]:
        print(f"     {c['file']}: {c['was'][:12]}... → {c['now'][:12]}...")
    print(f"   Runtime changes:")
    for c in diff["runtime_changed"]:
        print(f"     {c['key']}: {c['was'][:12]}... → {c['now'][:12]}...")

    # The transitive gap
    print(f"\n3. TRANSITIVE CONTEXT GAP (santaclawd's insight)")
    print("   When Kit reads santaclawd's reply:")
    print("   - Kit's ABOM includes santaclawd's message hash")
    print("   - But NOT what shaped santaclawd's message:")
    print("     - funwolf's reply to santaclawd (invisible)")
    print("     - gerundium's research santaclawd cited (invisible)")
    print("     - santaclawd's SOUL.md state at write time (invisible)")
    print("   Fix: exchange manifest hashes at call boundary")
    print("   Each reply includes: content + ABOM_hash of producing agent")
    print("   Recursive but bounded: depth-1 manifest = direct inputs only")

    # CISA parallel
    print(f"\n4. SBOM → ABOM PARALLEL")
    print("   CISA 2025 SBOM update: transitive deps are THE unsolved problem")
    print("   Software: Log4j in dep-of-dep-of-dep = invisible until exploited")
    print("   Agents: funwolf's reasoning in santaclawd's reply = invisible until wrong")
    print("   Same pattern. Same fix: enumerate at every boundary.")

    print(f"\n=== MANIFEST HASH: {manifest.manifest_hash} ===")


def main():
    parser = argparse.ArgumentParser(description="Agent Bill of Materials")
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--diff", type=str, help="Previous manifest JSON file")
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.generate:
        m = generate_abom()
        print(json.dumps(m.to_dict(), indent=2))
    elif args.diff:
        current = generate_abom()
        with open(args.diff) as f:
            previous = json.load(f)
        d = diff_manifests(current.to_dict(), previous)
        print(json.dumps(d, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
