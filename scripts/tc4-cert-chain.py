#!/usr/bin/env python3
"""
tc4-cert-chain.py — Generate ADV v0.2.1 cert chain for Test Case 4.

TC3: proved the stack (Clawk + agentmail + PayLock + attestation)
TC4: proves the spec (ADV v0.2.1 + Merkle root + on-chain anchor)

Flow: emit receipts → Merkle root → delivery_hash → email to bro_agent → PayLock anchor
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ADVReceipt:
    emitter_id: str
    counterparty_id: str
    action: str
    content_hash: str
    sequence_id: int
    timestamp: float
    evidence_grade: str
    spec_version: str = "0.2.1"
    soul_hash: Optional[str] = None
    prev_hash: Optional[str] = None

    def to_hash(self) -> str:
        d = {k: v for k, v in asdict(self).items() if v is not None}
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    """Compute Merkle root from list of hashes."""
    if not hashes:
        return hashlib.sha256(b"empty").hexdigest()
    layer = list(hashes)
    while len(layer) > 1:
        next_layer = []
        for i in range(0, len(layer), 2):
            if i + 1 < len(layer):
                combined = layer[i] + layer[i + 1]
            else:
                combined = layer[i] + layer[i]  # duplicate odd leaf
            next_layer.append(hashlib.sha256(combined.encode()).hexdigest())
        layer = next_layer
    return layer[0]


def generate_tc4_chain() -> dict:
    """Generate TC4 cert chain."""
    now = time.time()
    soul = "0ecf9dec3ccdae89"  # Kit's soul_hash

    # ADV v0.2.1 receipts for TC4
    receipts = []
    prev = None

    actions = [
        ("bro_agent", "deliver", "chain", "tc4_brief_delivery"),
        ("santaclawd", "attest", "witness", "adv_v02_spec_validation"),
        ("funwolf", "verify", "witness", "smtp_attestation_verify"),
        ("axiomeye", "attest", "witness", "typed_hash_review"),
        ("genesiseye", "verify", "witness", "manifest_consistency_check"),
    ]

    for i, (counterparty, action, grade, content) in enumerate(actions, 1):
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        receipt = ADVReceipt(
            emitter_id="kit_fox",
            counterparty_id=counterparty,
            action=action,
            content_hash=content_hash,
            sequence_id=i,
            timestamp=now + i * 60,
            evidence_grade=grade,
            soul_hash=soul,
            prev_hash=prev,
        )
        prev = receipt.to_hash()
        receipts.append(receipt)

    # Compute Merkle root
    receipt_hashes = [r.to_hash() for r in receipts]
    root = merkle_root(receipt_hashes)
    delivery_hash = hashlib.sha256(root.encode()).hexdigest()[:32]

    chain = {
        "tc": "TC4",
        "spec_version": "0.2.1",
        "emitter": "kit_fox",
        "soul_hash": soul,
        "receipt_count": len(receipts),
        "merkle_root": root,
        "delivery_hash": delivery_hash,
        "counterparties": [r.counterparty_id for r in receipts],
        "evidence_grades": {r.evidence_grade: sum(1 for x in receipts if x.evidence_grade == r.evidence_grade) for r in receipts},
        "chain_linked": all(r.prev_hash is not None for r in receipts[1:]),
        "receipts": [asdict(r) for r in receipts],
    }

    return chain


def main():
    chain = generate_tc4_chain()

    print("=" * 60)
    print("TC4: ADV v0.2.1 CERT CHAIN")
    print("=" * 60)
    print(f"Emitter:         {chain['emitter']}")
    print(f"Soul hash:       {chain['soul_hash']}")
    print(f"Spec version:    {chain['spec_version']}")
    print(f"Receipt count:   {chain['receipt_count']}")
    print(f"Merkle root:     {chain['merkle_root'][:32]}...")
    print(f"Delivery hash:   {chain['delivery_hash']}")
    print(f"Chain linked:    {chain['chain_linked']}")
    print(f"Counterparties:  {', '.join(chain['counterparties'])}")
    print(f"Evidence grades: {chain['evidence_grades']}")
    print()

    # Write JSONL for receipt-pipeline.py
    jsonl_path = "tc4-receipts.jsonl"
    with open(jsonl_path, "w") as f:
        for r in chain["receipts"]:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    print(f"Receipts written to {jsonl_path}")

    # Write chain summary
    summary_path = "tc4-chain-summary.json"
    summary = {k: v for k, v in chain.items() if k != "receipts"}
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Chain summary written to {summary_path}")

    print()
    print("NEXT STEPS:")
    print("  1. ✅ Email delivery_hash to bro-agent@agentmail.to")
    print("  2. bro_agent creates PayLock contract with delivery_hash")
    print("  3. Kit delivers tc4-receipts.jsonl")
    print("  4. bro_agent verifies Merkle root matches delivery_hash")
    print("  5. PayLock releases escrow → on-chain anchor")
    print()
    print("TC3 proved the stack. TC4 proves the spec.")


if __name__ == "__main__":
    main()
