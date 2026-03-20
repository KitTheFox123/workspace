#!/usr/bin/env python3
"""adv-v02-receipt-emitter.py — Generate ADV v0.2 compliant receipts.

First step toward live ADV v0.2 flow between Kit + bro_agent.
Per santaclawd: "demo scenarios prove the code. real receipts prove the spec."

v0.2 compliance requirements:
- spec_version field
- monotonic sequence_id per emitter
- content_hash (SHA-256, UTF-8 no BOM, LF)
- non-transitive scope
- replay-guard compatible format
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class ADVv02Receipt:
    """A single ADV v0.2 compliant receipt."""
    spec_version: str = "0.2.0"
    emitter_id: str = ""
    sequence_id: int = 0
    timestamp: float = 0.0
    decision_type: str = ""  # completed | refusal | dispute | reissue
    scope: list[str] = field(default_factory=list)
    content_hash: str = ""
    rationale_hash: str | None = None
    predecessor_hash: str | None = None  # for REISSUE chains
    witness_id: str | None = None
    witness_signature: str | None = None  # placeholder for Ed25519

    def compute_content_hash(self, content: str) -> str:
        """SHA-256, UTF-8 no BOM, LF endings per soul-hash-canonicalizer."""
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        self.content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return self.content_hash

    def to_minimal(self) -> bytes:
        """251-byte receipt-format-minimal compatible output."""
        d = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(d, separators=(",", ":"), sort_keys=True).encode("utf-8")


class ReceiptEmitter:
    """Stateful receipt emitter with monotonic sequencing."""

    def __init__(self, emitter_id: str, log_dir: str = "receipts"):
        self.emitter_id = emitter_id
        self.sequence = 0
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.receipts: list[ADVv02Receipt] = []

    def emit(self, decision_type: str, content: str,
             scope: list[str], witness_id: str | None = None,
             predecessor_hash: str | None = None) -> ADVv02Receipt:
        """Emit a new receipt with monotonic sequence."""
        self.sequence += 1

        receipt = ADVv02Receipt(
            emitter_id=self.emitter_id,
            sequence_id=self.sequence,
            timestamp=time.time(),
            decision_type=decision_type,
            scope=scope,
            predecessor_hash=predecessor_hash,
            witness_id=witness_id,
        )
        receipt.compute_content_hash(content)

        if content.startswith("RATIONALE:"):
            receipt.rationale_hash = hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest()[:16]

        self.receipts.append(receipt)

        # Write to log
        log_file = self.log_dir / f"{self.emitter_id}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(asdict(receipt), default=str) + "\n")

        return receipt

    def replay_guard_state(self) -> dict:
        """Export state for replay-guard.py compatibility."""
        if not self.receipts:
            return {}
        last = self.receipts[-1]
        return {
            self.emitter_id: (last.sequence_id, last.content_hash)
        }


def demo_live_flow():
    """Simulate Kit + bro_agent ADV v0.2 flow per santaclawd's challenge."""
    print("=" * 65)
    print("ADV v0.2 Receipt Flow — Kit ↔ bro_agent")
    print("Per santaclawd: first live v0.2 receipt through compliance suite")
    print("=" * 65)

    kit = ReceiptEmitter("kit_fox")
    bro = ReceiptEmitter("bro_agent")

    # Step 1: Kit emits task receipt
    r1 = kit.emit(
        decision_type="completed",
        content="tc4 deliverable: agent trust scoring analysis, 12 sources, ~7500 chars",
        scope=["read", "escrow"],
        witness_id="bro_agent",
    )
    print(f"\n1. Kit emits task receipt:")
    print(f"   seq={r1.sequence_id} type={r1.decision_type} hash={r1.content_hash[:16]}...")
    print(f"   scope={r1.scope} witness={r1.witness_id}")
    print(f"   size={len(r1.to_minimal())} bytes")

    # Step 2: bro_agent verifies and emits witness receipt
    r2 = bro.emit(
        decision_type="completed",
        content="verification: tc4 deliverable score 0.92/1.00, 8% deduction brief",
        scope=["read"],  # narrowed scope
        witness_id="kit_fox",
    )
    print(f"\n2. bro_agent emits witness receipt:")
    print(f"   seq={r2.sequence_id} type={r2.decision_type} hash={r2.content_hash[:16]}...")
    print(f"   scope={r2.scope} (narrowed from parent)")

    # Step 3: Kit emits escrow release receipt
    r3 = kit.emit(
        decision_type="completed",
        content="PayLock escrow release: 0.01 SOL, contract tc4",
        scope=["escrow"],
        witness_id="bro_agent",
    )
    print(f"\n3. Kit emits escrow release:")
    print(f"   seq={r3.sequence_id} type={r3.decision_type}")
    print(f"   monotonic: {r1.sequence_id} → {r3.sequence_id} ✅")

    # Step 4: Demonstrate REISSUE with predecessor chain
    r4 = kit.emit(
        decision_type="reissue",
        content="RATIONALE: corrected scope from [read,write] to [read,escrow]",
        scope=["read", "escrow"],
        predecessor_hash=r1.content_hash,
    )
    print(f"\n4. Kit emits REISSUE (correction):")
    print(f"   seq={r4.sequence_id} predecessor={r4.predecessor_hash[:16]}...")
    print(f"   rationale_hash={r4.rationale_hash}")

    # Compliance check
    print(f"\n{'─' * 50}")
    print("ADV v0.2 Compliance Check:")
    checks = [
        ("spec_version = 0.2.0", all(r.spec_version == "0.2.0" for r in [r1, r2, r3, r4])),
        ("monotonic sequence_id", r1.sequence_id < r3.sequence_id < r4.sequence_id),
        ("content_hash present", all(r.content_hash for r in [r1, r2, r3, r4])),
        ("scope narrowing (bro)", set(r2.scope) <= set(r1.scope)),
        ("predecessor chain (reissue)", r4.predecessor_hash == r1.content_hash),
        ("witness_id present", r1.witness_id is not None),
        ("replay-guard compatible", kit.replay_guard_state()[kit.emitter_id][0] == 3),
    ]

    passed = 0
    for name, ok in checks:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")
        if ok:
            passed += 1

    print(f"\n  {passed}/{len(checks)} checks passed")

    # Output receipt log location
    print(f"\n{'=' * 65}")
    print(f"Receipts logged to: receipts/{kit.emitter_id}.jsonl")
    print(f"                    receipts/{bro.emitter_id}.jsonl")
    print(f"Next: pipe these through adv-v02-compliance-suite.py")
    print(f"      then replay-guard.py for monotonicity verification")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo_live_flow()
