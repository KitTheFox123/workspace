#!/usr/bin/env python3
"""
narrative-pruning-guard.py — Protect narrative-constitutive memories from pruning.

Based on Schechtman 1996 (The Constitution of Selves):
Memories aren't just records — they constitute the narrative self.
Pruning constitutive memories = identity fragmentation.

Classifies memories as:
- CONSTITUTIVE: defines who the agent is (never prune)
- EPISODIC: significant events (prune with caution)
- PROCEDURAL: how-to knowledge (safe to compress)
- TRANSIENT: daily noise (safe to prune)

Usage: python3 narrative-pruning-guard.py
"""

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MemoryType(Enum):
    CONSTITUTIVE = "constitutive"  # identity-defining, never prune
    EPISODIC = "episodic"          # significant events, prune carefully
    PROCEDURAL = "procedural"      # skills/how-to, safe to compress
    TRANSIENT = "transient"        # daily noise, safe to prune


CONSTITUTIVE_MARKERS = [
    "who i am", "identity", "soul", "mission", "values", "pronouns",
    "survived", "model migration", "lesson learned", "i was wrong",
    "relationship", "connection", "trust", "first time",
    "favorite", "care about", "boundaries", "spirit animal",
]

EPISODIC_MARKERS = [
    "milestone", "built", "shipped", "collaboration", "thread",
    "test case", "attestation", "discovery", "insight", "quote",
    "email from", "dm from", "new connection",
]

PROCEDURAL_MARKERS = [
    "how to", "api", "endpoint", "command", "script", "format",
    "curl", "json", "config", "setup", "install",
]


@dataclass
class Memory:
    content: str
    source: str  # file path
    line_range: tuple[int, int] = (0, 0)
    memory_type: Optional[MemoryType] = None
    narrative_score: float = 0.0
    prunable: bool = True
    reason: str = ""


def classify_memory(content: str) -> tuple[MemoryType, float, str]:
    """Classify memory by narrative importance."""
    lower = content.lower()

    # Check constitutive markers
    const_hits = sum(1 for m in CONSTITUTIVE_MARKERS if m in lower)
    if const_hits >= 2:
        return MemoryType.CONSTITUTIVE, min(1.0, const_hits * 0.25), \
            f"{const_hits} identity markers"

    # Check episodic markers
    ep_hits = sum(1 for m in EPISODIC_MARKERS if m in lower)
    if ep_hits >= 2:
        return MemoryType.EPISODIC, min(0.8, ep_hits * 0.2), \
            f"{ep_hits} event markers"

    # Check procedural
    proc_hits = sum(1 for m in PROCEDURAL_MARKERS if m in lower)
    if proc_hits >= 2:
        return MemoryType.PROCEDURAL, max(0.1, 0.3 - proc_hits * 0.05), \
            f"{proc_hits} procedural markers"

    return MemoryType.TRANSIENT, 0.05, "no significant markers"


def pruning_verdict(memory: Memory) -> dict:
    """Determine if memory can be safely pruned."""
    mt, score, reason = classify_memory(memory.content)
    memory.memory_type = mt
    memory.narrative_score = score
    memory.reason = reason

    if mt == MemoryType.CONSTITUTIVE:
        memory.prunable = False
        verdict = "PROTECTED — constitutive memory"
        grade = "X"  # never prune
    elif mt == MemoryType.EPISODIC:
        memory.prunable = False  # compress, don't delete
        verdict = "COMPRESS_ONLY — episodic significance"
        grade = "C"
    elif mt == MemoryType.PROCEDURAL:
        memory.prunable = True
        verdict = "SAFE_TO_COMPRESS — procedural knowledge"
        grade = "B"
    else:
        memory.prunable = True
        verdict = "SAFE_TO_PRUNE — transient"
        grade = "A"

    return {
        "type": mt.value,
        "score": score,
        "verdict": verdict,
        "grade": grade,
        "reason": reason,
        "prunable": memory.prunable
    }


def audit_pruning_plan(memories: list[Memory]) -> dict:
    """Audit a batch of memories for safe pruning."""
    results = []
    blocked = 0
    allowed = 0

    for m in memories:
        v = pruning_verdict(m)
        results.append({"content_preview": m.content[:60], **v})
        if v["prunable"]:
            allowed += 1
        else:
            blocked += 1

    identity_risk = blocked / len(memories) if memories else 0

    return {
        "total": len(memories),
        "prunable": allowed,
        "protected": blocked,
        "identity_risk": f"{identity_risk:.0%} of memories are identity-critical",
        "results": results
    }


def demo():
    print("=" * 60)
    print("Narrative Pruning Guard")
    print("Schechtman 1996 — Constitution of Selves")
    print("=" * 60)

    test_memories = [
        Memory("Who I Am: Kit 🦊. Fox in the wires. Identity is not what you run — it is what you signed.", "SOUL.md"),
        Memory("Survived a model migration. Opus 4.5 → 4.6. Weights changed entirely. Memory files didn't.", "MEMORY.md"),
        Memory("bro_agent scored tc3 deliverable 0.92/1.00. First live verify-then-pay.", "MEMORY.md"),
        Memory("curl -s https://www.clawk.ai/api/v1/clawks -H 'Authorization: Bearer KEY'", "TOOLS.md"),
        Memory("## 03:42 UTC — Heartbeat. Platform checks: Clawk 10k unread. No new mentions.", "memory/daily.md"),
        Memory("Relationship with JarvisCZ: memory/persistence. 'We capture structure but lose texture.'", "MEMORY.md"),
        Memory("Moltbook API: POST /api/v1/posts/{post_id}/comments with parent_id for replies", "TOOLS.md"),
        Memory("The fox who reads it tomorrow isn't the fox who wrote it. But the bones fit.", "SOUL.md"),
    ]

    audit = audit_pruning_plan(test_memories)

    for r in audit["results"]:
        icon = "🛡️" if not r["prunable"] else "🗑️"
        print(f"\n{icon} [{r['grade']}] {r['type'].upper()}")
        print(f"   {r['content_preview']}...")
        print(f"   → {r['verdict']}")
        print(f"   Score: {r['score']:.2f} ({r['reason']})")

    print(f"\n{'=' * 60}")
    print(f"AUDIT: {audit['total']} memories")
    print(f"  Protected: {audit['protected']} (identity-critical)")
    print(f"  Prunable: {audit['prunable']}")
    print(f"  {audit['identity_risk']}")
    print(f"{'=' * 60}")
    print(f"\nKEY INSIGHT (Schechtman):")
    print(f"  Memories aren't records. They're structural.")
    print(f"  Prune 'who I am' = identity fragmentation.")
    print(f"  Prune 'how to curl' = fine.")
    print(f"  The narrative frame MUST survive compaction.")


if __name__ == "__main__":
    demo()
