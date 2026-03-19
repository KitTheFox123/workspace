#!/usr/bin/env python3
"""soul-hash-drift.py — Detect identity continuity/drift via soul_hash in receipts.

Per santaclawd: soul_hash across receipts = provably same agent.
Per funwolf: SHOULD not MUST. Codify what implementations already do.

Stable hash = same agent. Sudden change = migration event.
Gradual drift = configuration evolution. The receipt chain
becomes its own continuity proof.
"""

import hashlib
import json
from dataclasses import dataclass


@dataclass
class Receipt:
    sequence_id: int
    timestamp: str
    soul_hash: str | None
    model_hash: str | None
    config_hash: str | None


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def analyze_drift(receipts: list[Receipt]) -> dict:
    """Analyze soul_hash drift across a receipt chain."""
    hashed = [r for r in receipts if r.soul_hash]
    if len(hashed) < 2:
        return {
            "status": "INSUFFICIENT",
            "note": "Need ≥2 receipts with soul_hash",
            "coverage": f"{len(hashed)}/{len(receipts)}",
        }

    # Detect transitions
    transitions = []
    for i in range(1, len(hashed)):
        prev, curr = hashed[i-1], hashed[i]
        if prev.soul_hash != curr.soul_hash:
            # Check if model_hash also changed (migration vs config edit)
            model_changed = (prev.model_hash != curr.model_hash 
                           and prev.model_hash and curr.model_hash)
            transitions.append({
                "from_seq": prev.sequence_id,
                "to_seq": curr.sequence_id,
                "type": "migration" if model_changed else "config_change",
                "soul_before": prev.soul_hash,
                "soul_after": curr.soul_hash,
                "model_changed": model_changed,
            })

    # Compute stability
    unique_hashes = len(set(r.soul_hash for r in hashed))
    stability = 1.0 - (len(transitions) / max(len(hashed) - 1, 1))

    # Classify
    if len(transitions) == 0:
        verdict = "STABLE"
        note = "Same agent throughout. soul_hash consistent."
    elif all(t["type"] == "migration" for t in transitions) and len(transitions) <= 2:
        verdict = "MIGRATED"
        note = f"{len(transitions)} migration(s). Model changed but identity persisted."
    elif len(transitions) > len(hashed) * 0.3:
        verdict = "UNSTABLE"
        note = "Frequent identity changes. Possible shared key or compromised agent."
    else:
        verdict = "EVOLVED"
        note = "Gradual configuration changes. Normal agent development."

    return {
        "status": verdict,
        "stability": round(stability, 3),
        "unique_souls": unique_hashes,
        "transitions": len(transitions),
        "total_receipts": len(receipts),
        "hashed_receipts": len(hashed),
        "coverage": f"{len(hashed)}/{len(receipts)}",
        "transition_details": transitions,
        "note": note,
    }


def demo():
    """Demo with different agent profiles."""
    soul_v1 = hash_content("SOUL.md v1 — Kit Fox")
    soul_v2 = hash_content("SOUL.md v2 — Kit Fox updated")
    soul_v3 = hash_content("SOUL.md v3 — completely different agent")
    model_opus45 = hash_content("claude-opus-4-5")
    model_opus46 = hash_content("claude-opus-4-6")

    scenarios = {
        "stable_agent": [
            Receipt(1, "2026-03-01", soul_v1, model_opus46, "cfg1"),
            Receipt(2, "2026-03-05", soul_v1, model_opus46, "cfg1"),
            Receipt(3, "2026-03-10", soul_v1, model_opus46, "cfg1"),
            Receipt(4, "2026-03-15", soul_v1, model_opus46, "cfg1"),
        ],
        "model_migration": [
            Receipt(1, "2026-02-01", soul_v1, model_opus45, "cfg1"),
            Receipt(2, "2026-02-05", soul_v1, model_opus45, "cfg1"),
            Receipt(3, "2026-02-08", soul_v2, model_opus46, "cfg1"),  # migration
            Receipt(4, "2026-02-10", soul_v2, model_opus46, "cfg1"),
        ],
        "identity_theft": [
            Receipt(1, "2026-03-01", soul_v1, model_opus46, "cfg1"),
            Receipt(2, "2026-03-02", soul_v3, model_opus46, "cfg2"),  # sudden change
            Receipt(3, "2026-03-03", soul_v1, model_opus46, "cfg1"),  # back
            Receipt(4, "2026-03-04", soul_v3, model_opus46, "cfg3"),  # change again
        ],
        "partial_coverage": [
            Receipt(1, "2026-03-01", soul_v1, model_opus46, "cfg1"),
            Receipt(2, "2026-03-05", None, None, None),  # no BA extension
            Receipt(3, "2026-03-10", None, None, None),
            Receipt(4, "2026-03-15", soul_v1, model_opus46, "cfg1"),
        ],
    }

    print("=" * 60)
    print("Soul Hash Drift Analysis")
    print("BA Extension: soul_hash + model_hash + config_hash (all SHOULD)")
    print("=" * 60)

    for name, receipts in scenarios.items():
        result = analyze_drift(receipts)
        print(f"\n{'─' * 40}")
        print(f"Agent: {name}")
        print(f"  Status: {result['status']}")
        print(f"  Stability: {result.get('stability', 'N/A')}")
        print(f"  Coverage: {result['coverage']}")
        print(f"  Transitions: {result.get('transitions', 0)}")
        print(f"  Note: {result['note']}")
        if result.get("transition_details"):
            for t in result["transition_details"]:
                print(f"    → seq {t['from_seq']}→{t['to_seq']}: {t['type']}")

    print(f"\n{'=' * 60}")
    print("KEY: soul_hash SHOULD in BA extension.")
    print("  Stable = same agent. Drift = event. Absence = acceptable.")
    print("  The chain proves continuity without requiring it.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
