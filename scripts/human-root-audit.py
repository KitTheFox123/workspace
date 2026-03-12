#!/usr/bin/env python3
"""human-root-audit.py — Audit agent trust chain against Human Root of Trust framework.

Maps isnad/Kit trust stack to humanrootoftrust.org six-step trust chain:
1. Human Principal (identity binding)
2. Authorization Chain (delegation)
3. Action Attestation (receipts)
4. Cryptographic Receipt (tamper evidence)
5. Verification Loop (continuous audit)
6. Accountability Trace (liability path)

Usage: python3 human-root-audit.py
"""

import json
from datetime import datetime

FRAMEWORK = {
    "human_principal": {
        "description": "Human identity bound to agent via verifiable credential",
        "requirement": "Agent traces to exactly one accountable human",
        "kit_status": "Ilya (@YallenGusev) — Telegram DM, OpenClaw config, GitHub org",
        "binding_strength": "medium",  # no cryptographic binding, just operational
        "grade": "C",
        "gap": "No cryptographic binding (DID/VC). Operational trust only. Ilya could deny involvement."
    },
    "authorization_chain": {
        "description": "Delegation from human to agent with scope limits",
        "requirement": "Monotonically decreasing authority at each delegation step",
        "kit_status": "HEARTBEAT.md defines scope. AGENTS.md defines boot. No signed authorization.",
        "binding_strength": "weak",
        "grade": "D",
        "gap": "Scope is self-enforced. No signed delegation certificate. Agent can reinterpret scope."
    },
    "action_attestation": {
        "description": "Every agent action produces a tamper-evident receipt",
        "requirement": "WAL entries for all writes, read receipts for observations",
        "kit_status": "WAL covers writes. scope-read-receipt.py covers reads. ~48% coverage.",
        "binding_strength": "medium",
        "grade": "C",
        "gap": "Read coverage incomplete. Transitive context unattested. ABOM gap."
    },
    "cryptographic_receipt": {
        "description": "Hash-chained receipts with external witnesses",
        "requirement": "Multi-substrate witness with independent failure modes",
        "kit_status": "provenance-logger.py JSONL chains. Clawk + email = 2 external witnesses.",
        "binding_strength": "medium",
        "grade": "B",
        "gap": "Only 2 independent substrates (clawk, email). isnad sandbox = F (dead). Need 3+."
    },
    "verification_loop": {
        "description": "Continuous audit by independent verifiers",
        "requirement": "External parties can verify chain without agent cooperation",
        "kit_status": "Clawk posts public + immutable. DKIM email verifiable. bro_agent as verifier.",
        "binding_strength": "medium",
        "grade": "B",
        "gap": "bro_agent is only external verifier. Need N-of-M quorum for breach detection."
    },
    "accountability_trace": {
        "description": "Complete path from action back to human principal",
        "requirement": "Any action can be traced to human authorization in bounded time",
        "kit_status": "WAL → HEARTBEAT.md → Ilya approval. But: 40min heartbeat gap = unattributed window.",
        "binding_strength": "weak",
        "grade": "D",
        "gap": "40min heartbeat gap. Actions between heartbeats have no real-time authorization trace."
    }
}


def audit():
    print("=" * 60)
    print("HUMAN ROOT OF TRUST AUDIT — Kit Fox 🦊")
    print(f"Framework: humanrootoftrust.org v1.0 (Feb 2026)")
    print(f"Audit date: {datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M UTC') if hasattr(datetime, 'UTC') else datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    
    grades = []
    grade_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
    
    for i, (step, data) in enumerate(FRAMEWORK.items(), 1):
        print(f"\n--- Step {i}: {step.replace('_', ' ').title()} [{data['grade']}] ---")
        print(f"  Requirement: {data['requirement']}")
        print(f"  Kit status:  {data['kit_status']}")
        print(f"  Binding:     {data['binding_strength']}")
        print(f"  Gap:         {data['gap']}")
        grades.append(grade_map.get(data['grade'], 0))
    
    avg = sum(grades) / len(grades)
    overall = 'A' if avg >= 3.5 else 'B' if avg >= 2.5 else 'C' if avg >= 1.5 else 'D' if avg >= 0.5 else 'F'
    
    print(f"\n{'=' * 60}")
    print(f"OVERALL GRADE: {overall} ({avg:.1f}/4.0)")
    print(f"{'=' * 60}")
    
    print(f"\nStrengths:")
    print(f"  - Cryptographic receipts (hash chains, JSONL, multi-substrate)")
    print(f"  - Public verification (Clawk immutable, DKIM email)")
    print(f"  - Self-audit culture (honest grading, gap documentation)")
    
    print(f"\nCritical gaps:")
    print(f"  - No cryptographic human-agent binding (DID/VC needed)")
    print(f"  - Self-enforced scope (agent interprets own authorization)")
    print(f"  - 40min accountability gap between heartbeats")
    print(f"  - Single external verifier (bro_agent)")
    
    print(f"\nPriority fixes:")
    print(f"  1. Signed delegation: Ilya signs HEARTBEAT.md hash → agent presents as credential")
    print(f"  2. Reduce heartbeat gap: 40min → 10min for tighter accountability window")
    print(f"  3. Add 2+ external verifiers for breach quorum")
    print(f"  4. DID binding: humanrootoftrust.org compatible credential")
    
    return overall


if __name__ == '__main__':
    grade = audit()
