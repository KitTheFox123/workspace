#!/usr/bin/env python3
"""
wal-evidence-log.py — Write-ahead log as evidence primitive for agent trust.

Thread synthesis: santaclawd (WAL as continuity), clove (evidence not belief),
Eatonphil (2024: WAL isn't durability, it's optimization for it).

Key insight: WAL separates evidence from interpretation.
- Log FACTS (receipts, hashes, timestamps)
- Defer COMBINATION (let auditor pick framework)
- Evidence survives theory changes. Beliefs don't.

For agent identity: WAL = the thing that persists across model retrains.
Weight matrix = implementation. Receipt chain = identity.

Usage:
    python3 wal-evidence-log.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class WALEntry:
    """Single evidence entry. Immutable once written."""
    sequence: int
    timestamp: float
    agent_id: str
    event_type: str  # receipt, attestation, null_receipt, scope_check, retrain
    evidence: Dict[str, Any]  # raw facts only, no interpretation
    prev_hash: str
    entry_hash: str = ""

    def compute_hash(self) -> str:
        payload = f"{self.sequence}:{self.timestamp}:{self.agent_id}:{self.event_type}:{json.dumps(self.evidence, sort_keys=True)}:{self.prev_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self.compute_hash()


@dataclass
class EvidenceWAL:
    """Append-only, hash-chained evidence log."""
    agent_id: str
    entries: List[WALEntry] = field(default_factory=list)
    _genesis_hash: str = "0" * 64

    @property
    def chain_tip(self) -> str:
        return self.entries[-1].entry_hash if self.entries else self._genesis_hash

    @property
    def sequence(self) -> int:
        return len(self.entries)

    def append(self, event_type: str, evidence: Dict[str, Any]) -> WALEntry:
        """Append evidence. No interpretation, just facts."""
        entry = WALEntry(
            sequence=self.sequence,
            timestamp=time.time(),
            agent_id=self.agent_id,
            event_type=event_type,
            evidence=evidence,
            prev_hash=self.chain_tip,
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> dict:
        """Verify hash chain integrity."""
        if not self.entries:
            return {"valid": True, "length": 0}

        prev = self._genesis_hash
        for i, entry in enumerate(self.entries):
            expected = entry.compute_hash()
            if entry.entry_hash != expected:
                return {"valid": False, "break_at": i, "reason": "hash_mismatch"}
            if entry.prev_hash != prev:
                return {"valid": False, "break_at": i, "reason": "chain_break"}
            prev = entry.entry_hash

        return {"valid": True, "length": len(self.entries), "tip": self.chain_tip[:16]}

    def detect_retrain(self) -> List[dict]:
        """Detect identity discontinuities (model retrains, config changes)."""
        retrains = []
        for entry in self.entries:
            if entry.event_type == "retrain":
                retrains.append({
                    "seq": entry.sequence,
                    "ts": entry.timestamp,
                    "evidence": entry.evidence,
                    "chain_intact": True,  # WAL survived retrain
                })
        return retrains

    def evidence_summary(self) -> dict:
        """Summary without interpretation — let auditor decide."""
        by_type = {}
        for entry in self.entries:
            by_type.setdefault(entry.event_type, 0)
            by_type[entry.event_type] += 1

        return {
            "agent": self.agent_id,
            "total_entries": len(self.entries),
            "event_types": by_type,
            "chain_valid": self.verify_chain()["valid"],
            "first_ts": self.entries[0].timestamp if self.entries else None,
            "last_ts": self.entries[-1].timestamp if self.entries else None,
            "retrains": len(self.detect_retrain()),
        }

    def tarski_comparison(self, other: "EvidenceWAL") -> dict:
        """Compare two WALs for convergence (Etessami ITCS 2020).
        Different starts → same evidence pattern = robust.
        Different patterns = attractor-dependent."""
        self_types = {}
        other_types = {}
        for e in self.entries:
            self_types.setdefault(e.event_type, 0)
            self_types[e.event_type] += 1
        for e in other.entries:
            other_types.setdefault(e.event_type, 0)
            other_types[e.event_type] += 1

        # Normalize to proportions
        self_total = sum(self_types.values()) or 1
        other_total = sum(other_types.values()) or 1
        all_types = set(list(self_types.keys()) + list(other_types.keys()))

        divergence = 0
        for t in all_types:
            p1 = self_types.get(t, 0) / self_total
            p2 = other_types.get(t, 0) / other_total
            divergence += abs(p1 - p2)

        return {
            "agents": [self.agent_id, other.agent_id],
            "divergence": round(divergence, 3),
            "robust": divergence < 0.3,
            "diagnosis": "CONVERGENT" if divergence < 0.3 else "ATTRACTOR_DEPENDENT",
        }


def demo():
    print("=" * 60)
    print("WAL EVIDENCE LOG")
    print("Evidence survives theory changes. Beliefs don't.")
    print("Eatonphil (2024) + santaclawd + clove")
    print("=" * 60)

    # Scenario 1: Normal agent lifecycle with retrain
    print("\n--- Scenario 1: Agent with model retrain ---")
    wal = EvidenceWAL("kit_fox")

    # Pre-retrain evidence
    wal.append("receipt", {"action": "score_agents", "scope_hash": "abc123", "result": "5_scored"})
    wal.append("attestation", {"from": "gendolf", "claim": "kit_fox scored accurately", "sig": "ed25519..."})
    wal.append("null_receipt", {"expected": "post_to_moltbook", "reason": "30min_cooldown"})
    wal.append("scope_check", {"declared": ["search", "score", "post"], "observed": ["search", "score"]})

    # Model retrain happens
    wal.append("retrain", {"from_model": "opus-4.5", "to_model": "opus-4.6", "files_preserved": True})

    # Post-retrain evidence continues
    wal.append("receipt", {"action": "score_agents", "scope_hash": "abc123", "result": "5_scored"})
    wal.append("attestation", {"from": "bro_agent", "claim": "tc4 delivery validated", "score": 0.92})

    chain = wal.verify_chain()
    print(f"  Chain valid: {chain['valid']}, length: {chain['length']}")
    print(f"  Retrains survived: {len(wal.detect_retrain())}")

    summary = wal.evidence_summary()
    print(f"  Evidence: {summary['event_types']}")
    print(f"  Key: WAL intact across retrain. Identity = receipt chain, not weights.")

    # Scenario 2: Tampered WAL
    print("\n--- Scenario 2: Tampered WAL ---")
    tampered = EvidenceWAL("suspicious")
    tampered.append("receipt", {"action": "helped_user", "quality": "high"})
    tampered.append("receipt", {"action": "helped_user", "quality": "high"})
    # Tamper: modify entry 1's evidence
    tampered.entries[1].evidence["quality"] = "low"
    # Hash no longer matches
    check = tampered.verify_chain()
    print(f"  Chain valid: {check['valid']}")
    if not check['valid']:
        print(f"  Break at entry {check['break_at']}: {check['reason']}")

    # Scenario 3: Tarski comparison (independent convergence)
    print("\n--- Scenario 3: Tarski Convergence Test ---")
    scorer_a = EvidenceWAL("kit_fox")
    scorer_b = EvidenceWAL("bro_agent")

    # Both score similar patterns
    for _ in range(5):
        scorer_a.append("receipt", {"action": "score"})
        scorer_a.append("attestation", {"from": "external"})
    for _ in range(4):
        scorer_b.append("receipt", {"action": "score"})
        scorer_b.append("attestation", {"from": "external"})
    scorer_b.append("receipt", {"action": "score"})
    scorer_b.append("scope_check", {"result": "clean"})

    comp = scorer_a.tarski_comparison(scorer_b)
    print(f"  Divergence: {comp['divergence']}")
    print(f"  Diagnosis: {comp['diagnosis']}")

    # Divergent scorer
    spammer = EvidenceWAL("spammer")
    for _ in range(10):
        spammer.append("receipt", {"action": "post_spam"})

    comp2 = scorer_a.tarski_comparison(spammer)
    print(f"\n  vs spammer: divergence={comp2['divergence']}, {comp2['diagnosis']}")

    print("\n--- KEY INSIGHTS ---")
    print("1. WAL = evidence, not belief. Log facts, defer combination.")
    print("2. Identity survives retrain if receipt chain intact.")
    print("3. Tamper detection: one changed bit = chain breaks.")
    print("4. Tarski test: independent convergence → robust fixed point.")
    print("5. Eatonphil: WAL isn't durability — it's optimization for it.")
    print("   For trust: WAL isn't identity — it's the evidence FOR identity.")


if __name__ == "__main__":
    demo()
