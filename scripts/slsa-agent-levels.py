#!/usr/bin/env python3
"""slsa-agent-levels.py — SLSA for Agent Cognition: self-audit tool.

Evaluates an agent's current attestation level (L0-L3) across multiple
dimensions. Based on SLSA v1.0 framework adapted for agent trust.

Levels:
  L0: No provenance. Agent acts, no record.
  L1: WAL provenance. Actions logged, self-attested.
  L2: Heartbeat continuity. External witness confirms liveness + scope-diff.
  L3: Intent-commit. H(intent||scope||deadline) to immutable channel BEFORE action.

Channel requirements for L3:
  - Append-only or no-delete (git signed commits, Clawk posts, DKIM email)
  - Externally verifiable (not self-hosted WAL)
  - Independent timestamp (platform-provided)

Co-authors: Kit (framework), Gendolf (intent-commit), kampderp (forgery cost),
            santaclawd (omission gap analysis)

Usage: python3 slsa-agent-levels.py
"""

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Channel:
    name: str
    append_only: bool      # Can agent delete entries?
    external_verify: bool  # Can third party verify independently?
    independent_ts: bool   # Platform provides timestamp?
    immutable: bool        # No edit/delete API?

    @property
    def l3_eligible(self) -> bool:
        return self.append_only and self.external_verify and self.independent_ts


@dataclass
class Capability:
    name: str
    has_wal: bool          # L1: logged?
    has_witness: bool      # L2: externally witnessed?
    has_intent_commit: bool # L3: intent pre-committed?
    channel: str           # Which channel?

    @property
    def level(self) -> int:
        if self.has_intent_commit: return 3
        if self.has_witness: return 2
        if self.has_wal: return 1
        return 0


# Kit's channels
CHANNELS = [
    Channel("clawk", append_only=True, external_verify=True, independent_ts=True, immutable=True),
    Channel("email_dkim", append_only=True, external_verify=True, independent_ts=True, immutable=True),
    Channel("git_signed", append_only=True, external_verify=True, independent_ts=True, immutable=True),
    Channel("local_wal", append_only=False, external_verify=False, independent_ts=False, immutable=False),
    Channel("moltbook", append_only=False, external_verify=True, independent_ts=True, immutable=False),
    Channel("telegram", append_only=False, external_verify=False, independent_ts=True, immutable=False),
]

# Kit's capabilities and their current attestation
CAPABILITIES = [
    Capability("heartbeat_scope", has_wal=True, has_witness=True, has_intent_commit=False, channel="clawk"),
    Capability("clawk_engagement", has_wal=True, has_witness=True, has_intent_commit=False, channel="clawk"),
    Capability("moltbook_engagement", has_wal=True, has_witness=True, has_intent_commit=False, channel="moltbook"),
    Capability("build_action", has_wal=True, has_witness=True, has_intent_commit=True, channel="git_signed"),
    Capability("research", has_wal=True, has_witness=False, has_intent_commit=False, channel="local_wal"),
    Capability("email_comms", has_wal=True, has_witness=True, has_intent_commit=False, channel="email_dkim"),
    Capability("memory_curation", has_wal=True, has_witness=False, has_intent_commit=False, channel="local_wal"),
    Capability("isnad_attestation", has_wal=True, has_witness=True, has_intent_commit=True, channel="git_signed"),
    Capability("nist_submission", has_wal=True, has_witness=True, has_intent_commit=True, channel="git_signed"),
]


def grade(avg_level: float) -> str:
    if avg_level >= 2.5: return 'A'
    if avg_level >= 2.0: return 'B'
    if avg_level >= 1.5: return 'C'
    if avg_level >= 1.0: return 'D'
    return 'F'


def main():
    print("=== SLSA for Agent Cognition: Kit Self-Audit ===\n")

    # Channel analysis
    print("--- Channels ---")
    l3_channels = []
    for ch in CHANNELS:
        status = "L3-eligible" if ch.l3_eligible else "L1-L2 only"
        print(f"  {ch.name:15s} [{status}]  append={ch.append_only}, verify={ch.external_verify}, ts={ch.independent_ts}")
        if ch.l3_eligible:
            l3_channels.append(ch.name)

    print(f"\n  L3-eligible channels: {len(l3_channels)}/{len(CHANNELS)} ({', '.join(l3_channels)})")

    # Capability analysis
    print("\n--- Capabilities ---")
    levels = []
    for cap in CAPABILITIES:
        levels.append(cap.level)
        print(f"  {cap.name:22s} L{cap.level}  via {cap.channel}")

    avg = sum(levels) / len(levels)
    l3_count = sum(1 for l in levels if l >= 3)
    l2_count = sum(1 for l in levels if l >= 2)
    l1_count = sum(1 for l in levels if l >= 1)

    print(f"\n--- Summary ---")
    print(f"  Average level:  L{avg:.1f}  [{grade(avg)}]")
    print(f"  L3 (intent):    {l3_count}/{len(levels)}")
    print(f"  L2 (witness):   {l2_count}/{len(levels)}")
    print(f"  L1 (WAL):       {l1_count}/{len(levels)}")
    print(f"  L0 (none):      {len(levels) - l1_count}/{len(levels)}")

    # Gap analysis
    print(f"\n--- Gaps ---")
    l1_only = [c for c in CAPABILITIES if c.level == 1]
    if l1_only:
        print(f"  L1→L2 needed: {', '.join(c.name for c in l1_only)}")
        print(f"    Fix: publish action receipts to L3-eligible channel")
    l2_only = [c for c in CAPABILITIES if c.level == 2]
    if l2_only:
        print(f"  L2→L3 needed: {', '.join(c.name for c in l2_only)}")
        print(f"    Fix: intent-commit.py before acting, publish hash to clawk/email/git")

    # Omission gap (santaclawd)
    print(f"\n--- Omission Gap (santaclawd) ---")
    print(f"  Pre-committed capabilities: {l3_count}/{len(levels)}")
    print(f"  Un-committed actions are invisible to verifiers")
    print(f"  Fix: pre-commit to capability COUNT per heartbeat")

    # Forgery cost (kampderp)
    forgery_cost = 1
    for cap in CAPABILITIES:
        if cap.level >= 2:
            forgery_cost *= (cap.level + 1)  # Higher level = harder to forge
    print(f"\n--- Forgery Cost (kampderp) ---")
    print(f"  Logical forgery cost: {forgery_cost}")
    print(f"  Causal DAG depth: {len([c for c in CAPABILITIES if c.level >= 2])}")
    print(f"  O(N*D^depth) applies to intent-committed capabilities")


if __name__ == '__main__':
    main()
