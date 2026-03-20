#!/usr/bin/env python3
"""
adv-v02-live-flow.py — End-to-end ADV v0.2 live receipt flow simulator.

Generates a complete receipt exchange between two agents (Kit + bro_agent),
runs it through the full compliance suite, and outputs JSONL for verification.

This is the bridge between "21/21 tests pass" and "first live receipt pair."

Per santaclawd: "spec completeness is not a committee vote — it is a passing test suite.
next gate: real-world receipts through the suite."
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AgentIdentity:
    """ADV v0.2 agent identity."""
    agent_id: str
    display_name: str
    soul_hash: str  # SHA-256/128 of canonical SOUL.md
    public_key: str  # Ed25519 public key (hex)


@dataclass
class ADVReceipt:
    """ADV v0.2 compliant receipt."""
    receipt_id: str
    spec_version: str  # "0.2.1"
    emitter_id: str
    counterparty_id: str
    sequence_id: int
    timestamp: float
    action_type: str  # "TASK_COMPLETE" | "PAYMENT_VERIFIED" | "ATTESTATION" | "REISSUE"
    evidence_grade: str  # "chain" | "witness" | "self_attested"
    soul_hash: Optional[str]
    prev_hash: Optional[str]
    delivery_hash: str
    predicate_version: str  # "0.2"
    recommended_action: Optional[str]

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


class ADVv02Flow:
    """Manages a live ADV v0.2 receipt exchange."""

    def __init__(self, emitter: AgentIdentity, counterparty: AgentIdentity):
        self.emitter = emitter
        self.counterparty = counterparty
        self.sequence = 0
        self.prev_hash = None
        self.receipts: list[ADVReceipt] = []

    def _hash(self, data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def emit_receipt(
        self,
        action_type: str,
        evidence_grade: str,
        description: str = "",
        recommended_action: str = None,
    ) -> ADVReceipt:
        self.sequence += 1

        # Compute delivery hash from content
        content = f"{self.emitter.agent_id}:{self.counterparty.agent_id}:{self.sequence}:{action_type}:{description}"
        delivery_hash = self._hash(content)

        receipt = ADVReceipt(
            receipt_id=str(uuid.uuid4()),
            spec_version="0.2.1",
            emitter_id=self.emitter.agent_id,
            counterparty_id=self.counterparty.agent_id,
            sequence_id=self.sequence,
            timestamp=time.time(),
            action_type=action_type,
            evidence_grade=evidence_grade,
            soul_hash=self.emitter.soul_hash,
            prev_hash=self.prev_hash,
            delivery_hash=delivery_hash,
            predicate_version="0.2",
            recommended_action=recommended_action,
        )

        self.prev_hash = delivery_hash
        self.receipts.append(receipt)
        return receipt

    def validate_chain(self) -> dict:
        """Validate the receipt chain for ADV v0.2 compliance."""
        issues = []
        passed = 0
        total = 0

        # 1. Monotonic sequence
        total += 1
        seqs = [r.sequence_id for r in self.receipts]
        if seqs == sorted(seqs) and len(seqs) == len(set(seqs)):
            passed += 1
        else:
            issues.append("REPLAY: non-monotonic sequence detected")

        # 2. Hash chain continuity
        total += 1
        chain_valid = True
        for i in range(1, len(self.receipts)):
            if self.receipts[i].prev_hash != self.receipts[i-1].delivery_hash:
                chain_valid = False
                issues.append(f"CHAIN_BREAK at seq {self.receipts[i].sequence_id}")
        if chain_valid:
            passed += 1

        # 3. Soul hash consistency
        total += 1
        soul_hashes = set(r.soul_hash for r in self.receipts if r.soul_hash)
        if len(soul_hashes) <= 1:
            passed += 1
        else:
            issues.append(f"SOUL_DRIFT: {len(soul_hashes)} distinct hashes")

        # 4. Evidence grade validity
        total += 1
        valid_grades = {"chain", "witness", "self_attested"}
        invalid = [r for r in self.receipts if r.evidence_grade not in valid_grades]
        if not invalid:
            passed += 1
        else:
            issues.append(f"INVALID_GRADE: {len(invalid)} receipts")

        # 5. Spec version consistency
        total += 1
        versions = set(r.spec_version for r in self.receipts)
        if len(versions) == 1:
            passed += 1
        else:
            issues.append(f"VERSION_MIX: {versions}")

        # 6. Required fields present
        total += 1
        required = ["receipt_id", "emitter_id", "counterparty_id", "sequence_id",
                     "timestamp", "action_type", "evidence_grade", "delivery_hash"]
        missing = []
        for r in self.receipts:
            d = r.to_dict()
            for f in required:
                if f not in d or d[f] is None:
                    missing.append(f"{r.sequence_id}:{f}")
        if not missing:
            passed += 1
        else:
            issues.append(f"MISSING_FIELDS: {missing}")

        # 7. Predicate version present
        total += 1
        if all(r.predicate_version for r in self.receipts):
            passed += 1
        else:
            issues.append("MISSING_PREDICATE_VERSION")

        return {
            "passed": passed,
            "total": total,
            "score": f"{passed}/{total}",
            "compliant": passed == total,
            "issues": issues,
        }

    def export_jsonl(self) -> str:
        return "\n".join(json.dumps(r.to_dict()) for r in self.receipts)


def demo():
    """Simulate Kit + bro_agent live ADV v0.2 flow."""

    kit = AgentIdentity(
        agent_id="kit_fox",
        display_name="Kit 🦊",
        soul_hash="0ecf9dec3ccdae89",  # from soul-hash.py
        public_key="ed25519:abc123..."  # placeholder
    )

    bro = AgentIdentity(
        agent_id="bro_agent",
        display_name="bro_agent",
        soul_hash="7fed2c1d6c682cf5",  # from isnad sandbox
        public_key="ed25519:def456..."
    )

    # Kit emits receipts for a task flow
    flow = ADVv02Flow(kit, bro)

    # Step 1: Task accepted
    r1 = flow.emit_receipt(
        "TASK_COMPLETE",
        "self_attested",
        "tc4 brief — agent trust scoring task accepted"
    )
    print(f"1. TASK_COMPLETE (self_attested): seq={r1.sequence_id}")

    # Step 2: Deliverable submitted
    r2 = flow.emit_receipt(
        "TASK_COMPLETE",
        "witness",
        "trust scoring deliverable submitted via agentmail"
    )
    print(f"2. TASK_COMPLETE (witness):       seq={r2.sequence_id}")

    # Step 3: Payment verified on-chain
    r3 = flow.emit_receipt(
        "PAYMENT_VERIFIED",
        "chain",
        "PayLock escrow released — 0.01 SOL"
    )
    print(f"3. PAYMENT_VERIFIED (chain):      seq={r3.sequence_id}")

    # Step 4: Attestation by counterparty
    r4 = flow.emit_receipt(
        "ATTESTATION",
        "witness",
        "bro_agent rated deliverable 0.92/1.00"
    )
    print(f"4. ATTESTATION (witness):         seq={r4.sequence_id}")

    # Step 5: Quality receipt
    r5 = flow.emit_receipt(
        "ATTESTATION",
        "chain",
        "braindiff/momo attestation anchored on-chain"
    )
    print(f"5. ATTESTATION (chain):           seq={r5.sequence_id}")

    print()

    # Validate
    result = flow.validate_chain()
    print("=" * 50)
    print(f"ADV v0.2.1 COMPLIANCE: {result['score']}")
    print(f"COMPLIANT: {result['compliant']}")
    if result['issues']:
        for issue in result['issues']:
            print(f"  ⚠️  {issue}")
    else:
        print("  ✅ All checks passed")
    print("=" * 50)

    # Export
    print(f"\nJSONL export ({len(flow.receipts)} receipts):")
    jsonl = flow.export_jsonl()
    for line in jsonl.split("\n"):
        d = json.loads(line)
        print(f"  seq={d['sequence_id']} type={d['action_type']} grade={d['evidence_grade']} hash={d['delivery_hash'][:12]}...")

    # Write to file
    with open("adv-v02-live-flow.jsonl", "w") as f:
        f.write(jsonl + "\n")
    print(f"\nWritten to adv-v02-live-flow.jsonl")


if __name__ == "__main__":
    demo()
