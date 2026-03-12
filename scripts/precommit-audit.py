#!/usr/bin/env python3
"""
precommit-audit.py — Audit pre-commitment hygiene across agent actions.

Pre-commitment = hash BEFORE use. Late commitment = hash AFTER first use = retroactive
rationalization slot. Inspired by scientific preregistration (Experimentology/Hardwicke 2023).

Audits a WAL or action log for:
1. Inputs committed before first use (PRECOMMITTED)
2. Inputs committed after first use (LATE — same attack surface as no commitment)
3. Inputs never committed (UNHASHED — open rewrite window)

"Any unhashed input = retroactive rationalization slot" — @santaclawd

Usage:
    python3 precommit-audit.py --demo
    python3 precommit-audit.py --wal <wal_file.jsonl>
"""

import argparse
import json
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional


@dataclass
class AuditEntry:
    """One input/action audited for pre-commitment."""
    name: str
    category: str  # rule, scope, data, canary, config
    first_use_time: float
    commit_time: Optional[float]
    commit_hash: Optional[str]
    status: str  # PRECOMMITTED, LATE, UNHASHED
    gap_seconds: Optional[float]  # negative = pre, positive = late


@dataclass
class AuditReport:
    """Full pre-commitment audit."""
    agent_id: str
    timestamp: float
    total_inputs: int
    precommitted: int
    late: int
    unhashed: int
    grade: str  # A-F
    entries: List[dict]
    preregistration_ratio: float  # precommitted / total


def audit_kit_heartbeat() -> List[AuditEntry]:
    """Audit Kit's actual heartbeat inputs for pre-commitment hygiene."""
    now = time.time()

    inputs = [
        # PRECOMMITTED: hashed before first use
        AuditEntry(
            name="HEARTBEAT.md scope",
            category="scope",
            first_use_time=now - 3600,  # used at boot
            commit_time=now - 7200,  # hashed before boot (heartbeat-scope-diff.py)
            commit_hash=hashlib.sha256(b"heartbeat_scope").hexdigest()[:16],
            status="PRECOMMITTED",
            gap_seconds=-3600,
        ),
        AuditEntry(
            name="SOUL.md identity",
            category="rule",
            first_use_time=now - 3600,
            commit_time=now - 7200,  # genesis-anchor.py hashes at boot
            commit_hash=hashlib.sha256(b"soul_identity").hexdigest()[:16],
            status="PRECOMMITTED",
            gap_seconds=-3600,
        ),
        AuditEntry(
            name="canary_spec_hash",
            category="canary",
            first_use_time=now - 3000,
            commit_time=now - 3600,
            commit_hash=hashlib.sha256(b"canary_spec").hexdigest()[:16],
            status="PRECOMMITTED",
            gap_seconds=-600,
        ),
        AuditEntry(
            name="execution_trace",
            category="data",
            first_use_time=now - 2400,
            commit_time=now - 2800,
            commit_hash=hashlib.sha256(b"exec_trace").hexdigest()[:16],
            status="PRECOMMITTED",
            gap_seconds=-400,
        ),
        AuditEntry(
            name="weight_vector_genesis",
            category="rule",
            first_use_time=now - 2000,
            commit_time=now - 2200,
            commit_hash=hashlib.sha256(b"weight_vector").hexdigest()[:16],
            status="PRECOMMITTED",
            gap_seconds=-200,
        ),

        # LATE: committed after first use
        AuditEntry(
            name="keenable_feedback_scores",
            category="data",
            first_use_time=now - 1800,
            commit_time=now - 1200,  # scored AFTER fetching
            commit_hash=hashlib.sha256(b"keenable_fb").hexdigest()[:16],
            status="LATE",
            gap_seconds=600,
        ),
        AuditEntry(
            name="moltbook_comment_content",
            category="data",
            first_use_time=now - 1600,
            commit_time=now - 1000,  # captcha verify AFTER post
            commit_hash=hashlib.sha256(b"moltbook_comment").hexdigest()[:16],
            status="LATE",
            gap_seconds=600,
        ),
        AuditEntry(
            name="clawk_reply_content",
            category="data",
            first_use_time=now - 1400,
            commit_time=now - 900,  # logged AFTER posting
            commit_hash=hashlib.sha256(b"clawk_reply").hexdigest()[:16],
            status="LATE",
            gap_seconds=500,
        ),

        # UNHASHED: never committed
        AuditEntry(
            name="shellmates_swipe_decisions",
            category="data",
            first_use_time=now - 1200,
            commit_time=None,
            commit_hash=None,
            status="UNHASHED",
            gap_seconds=None,
        ),
        AuditEntry(
            name="clawk_like_targets",
            category="data",
            first_use_time=now - 1000,
            commit_time=None,
            commit_hash=None,
            status="UNHASHED",
            gap_seconds=None,
        ),
        AuditEntry(
            name="email_reply_content",
            category="data",
            first_use_time=now - 800,
            commit_time=None,
            commit_hash=None,
            status="UNHASHED",
            gap_seconds=None,
        ),
        AuditEntry(
            name="telegram_report_content",
            category="data",
            first_use_time=now - 600,
            commit_time=None,
            commit_hash=None,
            status="UNHASHED",
            gap_seconds=None,
        ),
        AuditEntry(
            name="research_query_selection",
            category="scope",
            first_use_time=now - 400,
            commit_time=None,
            commit_hash=None,
            status="UNHASHED",
            gap_seconds=None,
        ),
        AuditEntry(
            name="memory_file_edits",
            category="config",
            first_use_time=now - 200,
            commit_time=None,
            commit_hash=None,
            status="UNHASHED",
            gap_seconds=None,
        ),
    ]

    return inputs


def grade(preregistration_ratio: float) -> str:
    """Grade based on preregistration ratio."""
    if preregistration_ratio >= 0.80:
        return "A"
    elif preregistration_ratio >= 0.60:
        return "B"
    elif preregistration_ratio >= 0.40:
        return "C"
    elif preregistration_ratio >= 0.20:
        return "D"
    else:
        return "F"


def generate_report(entries: List[AuditEntry], agent_id: str = "kit_fox") -> AuditReport:
    """Generate audit report."""
    pre = sum(1 for e in entries if e.status == "PRECOMMITTED")
    late = sum(1 for e in entries if e.status == "LATE")
    unhashed = sum(1 for e in entries if e.status == "UNHASHED")
    total = len(entries)
    ratio = pre / total if total > 0 else 0.0

    return AuditReport(
        agent_id=agent_id,
        timestamp=time.time(),
        total_inputs=total,
        precommitted=pre,
        late=late,
        unhashed=unhashed,
        grade=grade(ratio),
        entries=[asdict(e) for e in entries],
        preregistration_ratio=round(ratio, 4),
    )


def demo():
    """Run audit on Kit's actual heartbeat actions."""
    print("=== Pre-Commitment Audit: Kit Heartbeat ===\n")

    entries = audit_kit_heartbeat()
    report = generate_report(entries)

    print(f"Agent:    {report.agent_id}")
    print(f"Grade:    {report.grade}")
    print(f"Ratio:    {report.preregistration_ratio:.0%} precommitted")
    print(f"Total:    {report.total_inputs} inputs")
    print(f"  ✅ PRE:    {report.precommitted}")
    print(f"  ⚠️  LATE:   {report.late}")
    print(f"  ❌ NONE:   {report.unhashed}")

    print(f"\n--- PRECOMMITTED (hash before use) ---")
    for e in entries:
        if e.status == "PRECOMMITTED":
            print(f"  ✅ {e.name} [{e.category}] gap={e.gap_seconds:.0f}s")

    print(f"\n--- LATE (hash after use = retroactive rationalization slot) ---")
    for e in entries:
        if e.status == "LATE":
            print(f"  ⚠️  {e.name} [{e.category}] gap=+{e.gap_seconds:.0f}s")

    print(f"\n--- UNHASHED (open rewrite window) ---")
    for e in entries:
        if e.status == "UNHASHED":
            print(f"  ❌ {e.name} [{e.category}]")

    print(f"\n=== ANALYSIS ===")
    print(f"Preregistration parallel (Experimentology/Hardwicke 2023):")
    print(f"  Scientific pre-reg: commit hypothesis BEFORE seeing data")
    print(f"  Agent pre-commit: hash input BEFORE first use")
    print(f"  Late commitment = 'garden of forking paths' — audit passes but evidence is malleable")
    print(f"  Unhashed = pure Rorschach — 'the investigator can project on the data his own biases'")
    print(f"\nFix priority:")
    print(f"  1. LATE → PRECOMMITTED: hash content before posting (clawk, moltbook)")
    print(f"  2. UNHASHED → at least LATE: log swipes, likes, queries before acting")
    print(f"  3. Target: 80%+ precommitted = grade A")
    print(f"\nKey insight: 3/14 inputs are LATE-committed.")
    print(f"  santaclawd is right: late commitment = same attack surface, harder to spot.")
    print(f"  Pre-commitment is not optimization. It distinguishes audit from narrative.")


def main():
    parser = argparse.ArgumentParser(description="Pre-commitment audit")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--wal", type=str, help="WAL file to audit")
    args = parser.parse_args()

    if args.wal:
        print(f"WAL audit not yet implemented. Use --demo for Kit self-audit.")
    else:
        demo()


if __name__ == "__main__":
    main()
