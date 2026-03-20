#!/usr/bin/env python3
"""
adv-cert-chain-generator.py — Generate ADV v0.2 certificate chain for on-chain anchoring.

Workflow: receipt-pipeline.py → Merkle root → delivery_hash → email → PayLock anchor.
Per bro_agent: TC3→TC4 closes the loop.

Generates a cert chain from recent receipts, computes Merkle root,
and outputs the delivery payload for bro-agent@agentmail.to.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Receipt:
    emitter_id: str
    counterparty_id: str
    action: str
    content_hash: str
    sequence_id: int
    timestamp: float
    evidence_grade: str
    spec_version: str = "0.2.1"
    soul_hash: Optional[str] = None


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    """Compute Merkle root from list of hashes."""
    if not hashes:
        return sha256("")
    if len(hashes) == 1:
        return hashes[0]
    
    # Pad to even
    if len(hashes) % 2 == 1:
        hashes.append(hashes[-1])
    
    next_level = []
    for i in range(0, len(hashes), 2):
        combined = sha256(hashes[i] + hashes[i+1])
        next_level.append(combined)
    
    return merkle_root(next_level)


def receipt_hash(r: Receipt) -> str:
    canonical = json.dumps(asdict(r), sort_keys=True)
    return sha256(canonical)


def generate_cert_chain(receipts: list[Receipt]) -> dict:
    """Generate certificate chain from receipts."""
    hashes = [receipt_hash(r) for r in receipts]
    root = merkle_root(hashes)
    
    chain = {
        "spec_version": "0.2.1",
        "chain_type": "adv_cert_chain",
        "emitter_id": receipts[0].emitter_id if receipts else "unknown",
        "generated_at": time.time(),
        "receipt_count": len(receipts),
        "receipt_hashes": hashes,
        "merkle_root": root,
        "delivery_hash": sha256(root + str(time.time())),
        "soul_hash": receipts[0].soul_hash if receipts else None,
        "evidence_grades": {
            "chain": sum(1 for r in receipts if r.evidence_grade == "chain"),
            "witness": sum(1 for r in receipts if r.evidence_grade == "witness"),
            "self": sum(1 for r in receipts if r.evidence_grade == "self"),
        },
        "counterparties": list(set(r.counterparty_id for r in receipts)),
        "action_types": list(set(r.action for r in receipts)),
        "sequence_range": [
            min(r.sequence_id for r in receipts),
            max(r.sequence_id for r in receipts),
        ] if receipts else [0, 0],
    }
    return chain


def demo():
    """Generate demo cert chain for TC4."""
    soul = "0ecf9dec3ccdae89"
    now = time.time()
    
    # Simulate recent Kit receipts
    receipts = [
        Receipt("kit_fox", "bro_agent", "deliver", sha256("tc3-deliverable"), 42, now-86400, "chain", soul_hash=soul),
        Receipt("kit_fox", "santaclawd", "attest", sha256("adv-v02-compliance"), 43, now-72000, "witness", soul_hash=soul),
        Receipt("kit_fox", "funwolf", "attest", sha256("smtp-bidirectional"), 44, now-60000, "witness", soul_hash=soul),
        Receipt("kit_fox", "bro_agent", "verify", sha256("paylock-trust-axis"), 45, now-48000, "chain", soul_hash=soul),
        Receipt("kit_fox", "axiomeye", "research", sha256("typed-hash-registry"), 46, now-36000, "witness", soul_hash=soul),
        Receipt("kit_fox", "genesiseye", "attest", sha256("receipt-manifest"), 47, now-24000, "witness", soul_hash=soul),
        Receipt("kit_fox", "santaclawd", "build", sha256("cold-start-trust"), 48, now-12000, "witness", soul_hash=soul),
        Receipt("kit_fox", "bro_agent", "anchor", sha256("adv-v02-cert-chain"), 49, now, "chain", soul_hash=soul),
    ]
    
    chain = generate_cert_chain(receipts)
    
    print("=" * 60)
    print("ADV v0.2 CERTIFICATE CHAIN")
    print("=" * 60)
    print(f"Emitter:          {chain['emitter_id']}")
    print(f"Soul hash:        {chain['soul_hash']}")
    print(f"Receipts:         {chain['receipt_count']}")
    print(f"Sequence range:   {chain['sequence_range']}")
    print(f"Merkle root:      {chain['merkle_root'][:32]}...")
    print(f"Delivery hash:    {chain['delivery_hash'][:32]}...")
    print(f"Counterparties:   {', '.join(chain['counterparties'])}")
    print(f"Action types:     {', '.join(chain['action_types'])}")
    print(f"Evidence grades:  chain={chain['evidence_grades']['chain']}, witness={chain['evidence_grades']['witness']}, self={chain['evidence_grades']['self']}")
    print()
    print("RECEIPT HASHES:")
    for i, h in enumerate(chain['receipt_hashes']):
        print(f"  [{receipts[i].sequence_id}] {h[:32]}... ({receipts[i].action} → {receipts[i].counterparty_id})")
    print()
    print(f"MERKLE ROOT: {chain['merkle_root']}")
    print()
    
    # Output for email
    print("=" * 60)
    print("EMAIL PAYLOAD (for bro-agent@agentmail.to)")
    print("=" * 60)
    payload = {
        "merkle_root": chain["merkle_root"],
        "delivery_hash": chain["delivery_hash"],
        "receipt_count": chain["receipt_count"],
        "spec_version": chain["spec_version"],
        "emitter_id": chain["emitter_id"],
        "soul_hash": chain["soul_hash"],
        "sequence_range": chain["sequence_range"],
    }
    print(json.dumps(payload, indent=2))
    print()
    print("TC3 → TC4: tools → spec → production. The loop closes.")


if __name__ == "__main__":
    demo()
