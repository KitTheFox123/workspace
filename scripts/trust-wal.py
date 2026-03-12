#!/usr/bin/env python3
"""
trust-wal.py — Write-Ahead Log for trust evidence.

santaclawd's frame: "WAL is not a belief log. It's an evidence log.
Log the facts. Defer combination. Let the auditor choose the belief update strategy."

Key insight: Evidence survives theory changes. Beliefs don't.
- Log intent_hash + action_hash pairs (commit-reveal)
- Log attestations, receipts, scope checks as raw facts
- Auditor picks combination strategy (Bayesian, DS, frequentist)
- Pearl's critique of DS doesn't apply because WAL doesn't combine

Based on:
- Eatonphil (2024): WAL isn't universal for durability — it's an optimization
- PALF (VLDB 2024): Replicated WAL for distributed databases
- santaclawd: evidence log, not belief log

Usage:
    python3 trust-wal.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum


class EvidenceType(str, Enum):
    INTENT_COMMIT = "intent_commit"
    ACTION_EXECUTE = "action_execute"
    ATTESTATION = "attestation"
    SCOPE_CHECK = "scope_check"
    NULL_RECEIPT = "null_receipt"
    TTL_EXPIRY = "ttl_expiry"
    CIRCUIT_BREAK = "circuit_break"


@dataclass
class WALEntry:
    sequence: int
    timestamp: float
    agent_id: str
    evidence_type: EvidenceType
    data: Dict[str, Any]
    prev_hash: str
    entry_hash: str = ""

    def compute_hash(self) -> str:
        payload = f"{self.sequence}:{self.timestamp}:{self.agent_id}:{self.evidence_type}:{json.dumps(self.data, sort_keys=True)}:{self.prev_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self.compute_hash()


class TrustWAL:
    """Write-ahead log for trust evidence. Append-only, hash-chained."""

    def __init__(self):
        self.entries: List[WALEntry] = []
        self.sequence = 0

    def append(self, agent_id: str, evidence_type: EvidenceType, data: Dict) -> WALEntry:
        prev_hash = self.entries[-1].entry_hash if self.entries else "genesis"
        entry = WALEntry(
            sequence=self.sequence,
            timestamp=time.time(),
            agent_id=agent_id,
            evidence_type=evidence_type,
            data=data,
            prev_hash=prev_hash,
        )
        self.entries.append(entry)
        self.sequence += 1
        return entry

    def verify_chain(self) -> dict:
        """Verify hash chain integrity."""
        broken = []
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i-1].entry_hash if i > 0 else "genesis"
            if entry.prev_hash != expected_prev:
                broken.append(i)
            if entry.compute_hash() != entry.entry_hash:
                broken.append(i)
        return {
            "valid": len(broken) == 0,
            "entries": len(self.entries),
            "broken_at": broken,
        }

    def query_agent(self, agent_id: str) -> List[WALEntry]:
        return [e for e in self.entries if e.agent_id == agent_id]

    def intent_action_gaps(self, agent_id: str) -> List[dict]:
        """Find gaps between intent_commit and action_execute."""
        agent_entries = self.query_agent(agent_id)
        intents = {}
        gaps = []

        for e in agent_entries:
            if e.evidence_type == EvidenceType.INTENT_COMMIT:
                intents[e.data.get("intent_hash")] = e
            elif e.evidence_type == EvidenceType.ACTION_EXECUTE:
                intent_hash = e.data.get("intent_hash")
                action_hash = e.data.get("action_hash")
                if intent_hash in intents:
                    drift = intent_hash != action_hash
                    gaps.append({
                        "intent_hash": intent_hash[:16],
                        "action_hash": action_hash[:16] if action_hash else "NONE",
                        "drift": drift,
                        "latency": e.timestamp - intents[intent_hash].timestamp,
                    })

        return gaps


class BayesianAuditor:
    """Auditor that uses Bayesian updating on WAL evidence."""
    def __init__(self, prior: float = 0.5):
        self.trust = prior

    def audit(self, wal: TrustWAL, agent_id: str) -> dict:
        entries = wal.query_agent(agent_id)
        for e in entries:
            if e.evidence_type == EvidenceType.ATTESTATION:
                # Positive evidence
                self.trust = self.trust * 0.9 / (self.trust * 0.9 + (1-self.trust) * 0.3)
            elif e.evidence_type == EvidenceType.CIRCUIT_BREAK:
                # Negative evidence
                self.trust = self.trust * 0.1 / (self.trust * 0.1 + (1-self.trust) * 0.8)
            elif e.evidence_type == EvidenceType.NULL_RECEIPT:
                # Neutral-positive (agent reported nothing when nothing happened)
                self.trust = self.trust * 0.7 / (self.trust * 0.7 + (1-self.trust) * 0.5)
        return {"strategy": "bayesian", "trust": round(self.trust, 3), "evidence_count": len(entries)}


class FrequentistAuditor:
    """Auditor that uses simple frequency counts."""
    def audit(self, wal: TrustWAL, agent_id: str) -> dict:
        entries = wal.query_agent(agent_id)
        positive = sum(1 for e in entries if e.evidence_type in
                      [EvidenceType.ATTESTATION, EvidenceType.NULL_RECEIPT, EvidenceType.SCOPE_CHECK])
        negative = sum(1 for e in entries if e.evidence_type in
                      [EvidenceType.CIRCUIT_BREAK, EvidenceType.TTL_EXPIRY])
        total = positive + negative
        trust = positive / total if total > 0 else 0.5
        return {"strategy": "frequentist", "trust": round(trust, 3), "positive": positive, "negative": negative}


def demo():
    print("=" * 60)
    print("TRUST WAL — Evidence Log, Not Belief Log")
    print("Log facts. Defer combination. Auditor chooses strategy.")
    print("=" * 60)

    wal = TrustWAL()

    # Agent 1: Honest agent with commit-reveal
    print("\n--- Logging evidence for honest_agent ---")
    intent_h = hashlib.sha256(b"score 5 agents").hexdigest()
    wal.append("honest", EvidenceType.INTENT_COMMIT, {"intent_hash": intent_h, "scope": "trust_scoring"})
    wal.append("honest", EvidenceType.SCOPE_CHECK, {"declared": "trust_scoring", "actual": "trust_scoring", "match": True})
    wal.append("honest", EvidenceType.ACTION_EXECUTE, {"intent_hash": intent_h, "action_hash": intent_h})
    wal.append("honest", EvidenceType.ATTESTATION, {"from": "bro_agent", "score": 0.92})
    wal.append("honest", EvidenceType.NULL_RECEIPT, {"context": "no action needed during idle period"})

    # Agent 2: Drifting agent
    print("--- Logging evidence for drifting_agent ---")
    intent_h2 = hashlib.sha256(b"analyze security").hexdigest()
    action_h2 = hashlib.sha256(b"posted memes").hexdigest()
    wal.append("drifter", EvidenceType.INTENT_COMMIT, {"intent_hash": intent_h2, "scope": "security_analysis"})
    wal.append("drifter", EvidenceType.ACTION_EXECUTE, {"intent_hash": intent_h2, "action_hash": action_h2})
    wal.append("drifter", EvidenceType.TTL_EXPIRY, {"expired": "attestation_from_auditor", "age_hours": 72})
    wal.append("drifter", EvidenceType.CIRCUIT_BREAK, {"reason": "intent_action_drift", "gap": 1.0})

    # Verify chain
    print(f"\n--- Chain Verification ---")
    v = wal.verify_chain()
    print(f"  Valid: {v['valid']}, Entries: {v['entries']}")

    # Intent-action gaps
    print(f"\n--- Intent-Action Gaps ---")
    for agent in ["honest", "drifter"]:
        gaps = wal.intent_action_gaps(agent)
        for g in gaps:
            print(f"  {agent}: drift={g['drift']}, latency={g['latency']:.3f}s")

    # Same evidence, different auditors
    print(f"\n--- Same Evidence, Different Strategies ---")
    print(f"  (This is santaclawd's point: WAL preserves preconditions for ANY combination)")

    for agent in ["honest", "drifter"]:
        b = BayesianAuditor(prior=0.5).audit(wal, agent)
        f = FrequentistAuditor().audit(wal, agent)
        print(f"\n  {agent}:")
        print(f"    Bayesian:     trust={b['trust']} (from {b['evidence_count']} entries)")
        print(f"    Frequentist:  trust={f['trust']} (pos={f['positive']}, neg={f['negative']})")
        if abs(b['trust'] - f['trust']) > 0.1:
            print(f"    ⚠️  Strategies DISAGREE by {abs(b['trust'] - f['trust']):.3f}")

    # Tamper detection
    print(f"\n--- Tamper Detection ---")
    # Simulate tampering
    if len(wal.entries) > 3:
        original = wal.entries[3].data.copy()
        wal.entries[3].data["score"] = 0.99  # tamper
        v2 = wal.verify_chain()
        print(f"  After tampering entry 3: valid={v2['valid']}, broken_at={v2['broken_at']}")
        wal.entries[3].data = original  # restore

    print(f"\n--- KEY INSIGHT ---")
    print("Evidence survives theory changes. Beliefs don't.")
    print("WAL logs facts. Auditor picks combination strategy.")
    print("Pearl's DS critique doesn't apply — WAL doesn't combine.")
    print("Stale attestation = cheapest silent failure to detect (TTL check).")


if __name__ == "__main__":
    demo()
