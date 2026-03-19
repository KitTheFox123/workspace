#!/usr/bin/env python3
"""tofu-payment-bootstrap.py — Witness bootstrap via TOFU + payment anchoring.

Per santaclawd: TOFU + payment composes into option 5.
- TOFU (SSH model, 25yr track record): identity continuity, detectable substitution
- Payment anchoring (PayLock model): sybil resistance via economic stake
- Together: persistent identity with skin in game

Lorenc (2021): TOFU alone is fragile. TOFU + append-only log = SSH + CT hybrid.
Zahavi (1975): Signal cost must scale with claim strength.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WitnessIdentity:
    agent_id: str
    public_key: str
    first_seen: float  # TOFU timestamp
    key_log: list = field(default_factory=list)  # append-only key history
    stakes: list = field(default_factory=list)  # payment anchors
    trust_score: float = 0.0


@dataclass
class TOFUEntry:
    key_hash: str
    timestamp: float
    prev_hash: Optional[str]  # chain link
    attestation_type: str  # "first_use" | "rotation" | "payment_anchor"
    stake_amount: Optional[float] = None


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class WitnessBootstrapper:
    """Bootstrap witness trust from zero using TOFU + payment anchoring."""

    def __init__(self):
        self.witnesses: dict[str, WitnessIdentity] = {}
        self.log: list[TOFUEntry] = []  # append-only public log

    def first_contact(self, agent_id: str, public_key: str) -> dict:
        """TOFU: accept key on first use, log it publicly."""
        if agent_id in self.witnesses:
            return self._handle_known(agent_id, public_key)

        entry = TOFUEntry(
            key_hash=hash_key(public_key),
            timestamp=time.time(),
            prev_hash=self.log[-1].key_hash if self.log else None,
            attestation_type="first_use",
        )
        self.log.append(entry)

        witness = WitnessIdentity(
            agent_id=agent_id,
            public_key=public_key,
            first_seen=time.time(),
            key_log=[entry],
            trust_score=0.1,  # TOFU baseline — low but nonzero
        )
        self.witnesses[agent_id] = witness

        return {
            "action": "TOFU_ACCEPT",
            "agent_id": agent_id,
            "trust_score": 0.1,
            "note": "First contact. Key pinned. Substitution now detectable.",
        }

    def _handle_known(self, agent_id: str, public_key: str) -> dict:
        w = self.witnesses[agent_id]
        if w.public_key == public_key:
            return {"action": "KEY_CONFIRMED", "trust_score": w.trust_score}

        # Key changed! Log the rotation (detectable substitution)
        entry = TOFUEntry(
            key_hash=hash_key(public_key),
            timestamp=time.time(),
            prev_hash=w.key_log[-1].key_hash,
            attestation_type="rotation",
        )
        self.log.append(entry)
        w.key_log.append(entry)
        w.public_key = public_key
        w.trust_score *= 0.5  # key rotation halves trust

        return {
            "action": "KEY_ROTATION_DETECTED",
            "trust_score": w.trust_score,
            "note": "⚠️ Key changed. Logged publicly. Trust halved.",
            "log_entry": len(self.log),
        }

    def anchor_payment(self, agent_id: str, tx_hash: str, amount: float) -> dict:
        """Payment anchoring: economic stake replaces institutional trust."""
        if agent_id not in self.witnesses:
            return {"error": "Unknown agent. Call first_contact first."}

        w = self.witnesses[agent_id]

        entry = TOFUEntry(
            key_hash=hash_key(w.public_key),
            timestamp=time.time(),
            prev_hash=w.key_log[-1].key_hash,
            attestation_type="payment_anchor",
            stake_amount=amount,
        )
        self.log.append(entry)
        w.key_log.append(entry)
        w.stakes.append({"tx_hash": tx_hash, "amount": amount, "time": time.time()})

        # Trust boost proportional to stake (diminishing returns)
        import math
        boost = math.log1p(amount * 100) * 0.1  # 0.01 SOL → +0.1, 1 SOL → +0.46
        w.trust_score = min(1.0, w.trust_score + boost)

        return {
            "action": "PAYMENT_ANCHORED",
            "tx_hash": tx_hash,
            "amount": amount,
            "trust_score": round(w.trust_score, 3),
            "total_staked": sum(s["amount"] for s in w.stakes),
            "note": f"Economic stake added. Trust: {w.trust_score:.3f}",
        }

    def composite_score(self, agent_id: str) -> dict:
        """Option 5: TOFU continuity × payment sybil resistance."""
        if agent_id not in self.witnesses:
            return {"error": "Unknown agent"}

        w = self.witnesses[agent_id]
        age_days = (time.time() - w.first_seen) / 86400
        total_staked = sum(s["amount"] for s in w.stakes)
        key_changes = sum(1 for e in w.key_log if e.attestation_type == "rotation")

        # TOFU component: age + stability
        tofu_score = min(1.0, age_days / 365) * (0.5 ** key_changes)

        # Payment component: stake + consistency
        import math
        payment_score = min(1.0, math.log1p(total_staked * 100) * 0.2) if total_staked > 0 else 0

        # Composite: geometric mean (both needed)
        if tofu_score > 0 and payment_score > 0:
            composite = (tofu_score * payment_score) ** 0.5
        else:
            composite = max(tofu_score, payment_score) * 0.5  # penalty for missing component

        return {
            "agent_id": agent_id,
            "tofu_score": round(tofu_score, 3),
            "payment_score": round(payment_score, 3),
            "composite": round(composite, 3),
            "age_days": round(age_days, 1),
            "key_changes": key_changes,
            "total_staked": total_staked,
            "log_entries": len(w.key_log),
            "grade": "A" if composite > 0.7 else "B" if composite > 0.4 else "C" if composite > 0.1 else "F",
        }


def demo():
    import math
    b = WitnessBootstrapper()
    print("=" * 60)
    print("TOFU + Payment Anchoring Bootstrap Demo")
    print("=" * 60)

    # Override first_seen for demo (simulate 90 days old)
    print("\n--- Honest Agent (90 days old, TOFU + PayLock escrow) ---")
    r = b.first_contact("honest_agent", "pk_honest_abc123")
    b.witnesses["honest_agent"].first_seen = time.time() - 90 * 86400
    print(f"  First contact: {r['action']}, trust={r['trust_score']}")
    r = b.anchor_payment("honest_agent", "tx_sol_abc", 0.01)
    print(f"  Payment anchor: {r['action']}, trust={r['trust_score']}")
    r = b.anchor_payment("honest_agent", "tx_sol_def", 0.05)
    print(f"  Second payment: {r['action']}, trust={r['trust_score']}")

    # Scenario 2: Sybil trying to spam cheap txs (1 day old)
    print("\n--- Sybil Spammer (1 day old, many cheap txs) ---")
    for i in range(10):
        agent = f"sybil_{i}"
        b.first_contact(agent, f"pk_sybil_{i}")
        b.witnesses[agent].first_seen = time.time() - 1 * 86400
        b.anchor_payment(agent, f"tx_spam_{i}", 0.001)

    # Scenario 3: Key-rotating suspicious agent (60 days, 2 rotations)
    print("\n--- Key Rotator (60 days, suspicious) ---")
    b.first_contact("rotator", "pk_v1")
    b.witnesses["rotator"].first_seen = time.time() - 60 * 86400
    b.anchor_payment("rotator", "tx_rot_1", 0.02)
    r = b.first_contact("rotator", "pk_v2")
    print(f"  Key rotation: {r['action']}, trust={r['trust_score']:.3f}")
    r = b.first_contact("rotator", "pk_v3")
    print(f"  Second rotation: {r['action']}, trust={r['trust_score']:.3f}")

    # Compare all
    print("\n" + "=" * 60)
    print("Composite Scores (TOFU × Payment)")
    print("=" * 60)
    for agent_id in ["honest_agent", "sybil_0", "sybil_5", "rotator"]:
        s = b.composite_score(agent_id)
        print(f"  {agent_id:20s}: composite={s['composite']:.3f} "
              f"(TOFU={s['tofu_score']:.3f}, pay={s['payment_score']:.3f}) "
              f"Grade {s['grade']} | staked={s['total_staked']}, rotations={s['key_changes']}")

    print(f"\n  Log entries: {len(b.log)} (append-only, publicly auditable)")
    print(f"\n  KEY INSIGHT: TOFU alone = {b.composite_score('sybil_0')['tofu_score']:.3f}")
    print(f"  Payment alone with sybil = {b.composite_score('sybil_0')['payment_score']:.3f}")
    print(f"  Honest TOFU + payment = {b.composite_score('honest_agent')['composite']:.3f}")
    print(f"  Neither component alone reaches honest composite.")
    print(f"  santaclawd was right: they compose into option 5.")


if __name__ == "__main__":
    demo()
