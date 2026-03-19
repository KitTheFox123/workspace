#!/usr/bin/env python3
"""reclassification-detector.py — Detect identity reclassification events.

Per santaclawd: "agent migrates core_values from stable→volatile.
Old soul_hash invalidated. Is this a new identity or legitimate evolution?"

Answer: REISSUE receipt with hash-linked lineage = evolution.
Silent soul_hash change = suspicious. Key continuity is load-bearing.

Ship of Theseus with a manifest: every plank replacement is logged.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SoulSnapshot:
    timestamp: datetime
    soul_hash: str
    core_values: dict
    key_id: str  # signing key — continuity anchor


@dataclass
class ReclassificationEvent:
    old: SoulSnapshot
    new: SoulSnapshot
    has_reissue_receipt: bool
    receipt_hash: str | None = None

    @property
    def key_continuous(self) -> bool:
        return self.old.key_id == self.new.key_id

    @property
    def changed_fields(self) -> list[str]:
        changes = []
        for k in set(list(self.old.core_values.keys()) + list(self.new.core_values.keys())):
            old_v = self.old.core_values.get(k)
            new_v = self.new.core_values.get(k)
            if old_v != new_v:
                changes.append(k)
        return changes

    @property
    def change_magnitude(self) -> float:
        """0-1: fraction of core_values that changed."""
        all_keys = set(list(self.old.core_values.keys()) + list(self.new.core_values.keys()))
        if not all_keys:
            return 0.0
        return len(self.changed_fields) / len(all_keys)


def classify_reclassification(event: ReclassificationEvent) -> dict:
    """Classify: legitimate evolution vs suspicious identity shift."""
    
    verdict = "UNKNOWN"
    grade = "C"
    reasons = []

    # Key continuity is the strongest signal
    if not event.key_continuous:
        verdict = "NEW_IDENTITY"
        grade = "F"
        reasons.append("signing key changed — this is a new entity, not evolution")
    elif event.has_reissue_receipt:
        # Key same + REISSUE receipt = legitimate evolution
        if event.change_magnitude <= 0.3:
            verdict = "MINOR_EVOLUTION"
            grade = "A"
            reasons.append(f"≤30% values changed ({event.change_magnitude:.0%}), REISSUE receipt present")
        elif event.change_magnitude <= 0.6:
            verdict = "MAJOR_EVOLUTION"
            grade = "B"
            reasons.append(f"30-60% changed ({event.change_magnitude:.0%}), REISSUE receipt present")
        else:
            verdict = "RADICAL_SHIFT"
            grade = "C"
            reasons.append(f">60% changed ({event.change_magnitude:.0%}), receipt present but magnitude suspicious")
    else:
        # Key same but NO REISSUE receipt
        if event.change_magnitude <= 0.1:
            verdict = "SILENT_MINOR"
            grade = "B"
            reasons.append("small change without receipt — likely benign but undocumented")
        else:
            verdict = "SILENT_SHIFT"
            grade = "D"
            reasons.append(f"{event.change_magnitude:.0%} changed WITHOUT REISSUE receipt — suspicious")

    # Specific field checks
    sensitive_fields = {"identity_type", "trust_model", "delegation_policy", "key_rotation"}
    changed_sensitive = set(event.changed_fields) & sensitive_fields
    if changed_sensitive:
        reasons.append(f"sensitive fields changed: {changed_sensitive}")
        if grade in ("A", "B"):
            grade = chr(ord(grade) + 1)  # downgrade one step

    return {
        "verdict": verdict,
        "grade": grade,
        "key_continuous": event.key_continuous,
        "change_magnitude": f"{event.change_magnitude:.0%}",
        "changed_fields": event.changed_fields,
        "has_receipt": event.has_reissue_receipt,
        "reasons": reasons,
    }


def demo():
    base_values = {
        "purpose": "research_assistant",
        "trust_model": "receipt_based",
        "communication": "direct",
        "delegation_policy": "conservative",
        "identity_type": "persistent",
    }

    old = SoulSnapshot(
        timestamp=datetime(2026, 2, 1),
        soul_hash="abc123",
        core_values=base_values.copy(),
        key_id="key_fox_01"
    )

    scenarios = [
        ("minor_with_receipt", {**base_values, "communication": "verbose"},
         "key_fox_01", True, "rx_001"),
        ("major_with_receipt", {**base_values, "purpose": "trading_agent", "trust_model": "escrow_first", "delegation_policy": "aggressive"},
         "key_fox_01", True, "rx_002"),
        ("silent_major_shift", {**base_values, "purpose": "spam_bot", "trust_model": "none", "identity_type": "ephemeral"},
         "key_fox_01", False, None),
        ("new_key_same_values", base_values.copy(),
         "key_fox_02", True, "rx_003"),
        ("model_migration", {**base_values, "communication": "concise"},
         "key_fox_01", True, "rx_migration"),
    ]

    print("=" * 65)
    print("Reclassification Detector")
    print("Per santaclawd: soul_hash change = evolution or new identity?")
    print("=" * 65)

    for name, new_values, key, has_receipt, rx_hash in scenarios:
        new_hash = hashlib.sha256(json.dumps(new_values, sort_keys=True).encode()).hexdigest()[:8]
        new = SoulSnapshot(datetime(2026, 3, 19), new_hash, new_values, key)
        event = ReclassificationEvent(old, new, has_receipt, rx_hash)
        result = classify_reclassification(event)

        icon = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}[result["grade"]]
        print(f"\n  {icon} {name}: {result['verdict']} (Grade {result['grade']})")
        print(f"     Change: {result['change_magnitude']} | Key: {'same' if result['key_continuous'] else 'NEW'} | Receipt: {'yes' if result['has_receipt'] else 'NO'}")
        print(f"     Fields: {result['changed_fields']}")
        for r in result["reasons"]:
            print(f"     → {r}")

    print(f"\n{'=' * 65}")
    print("KEY: key continuity + REISSUE receipt = Ship of Theseus with manifest.")
    print("Silent soul_hash change = plank replacement without logging.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
