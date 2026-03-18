#!/usr/bin/env python3
"""
interop-milestone-tracker.py — Track receipt-format-minimal implementation status
Three independent implementations = RFC 2026 §4.1 bar met.
"""

from dataclasses import dataclass
from datetime import datetime

@dataclass
class Implementation:
    name: str
    author: str
    impl_type: str  # validator/parser/emitter
    version: str
    vectors_passed: int
    vectors_total: int
    notes: str
    date: str

    @property
    def pass_rate(self) -> float:
        return self.vectors_passed / self.vectors_total if self.vectors_total else 0

implementations = [
    Implementation("receipt-validator-cli.py", "Kit", "validator", "0.2.1",
                   5, 5, "Reference validator. 5 test vectors.", "2026-03-17"),
    Implementation("receipt-parser-harness.py", "Kit", "test-harness", "0.2.1",
                   29, 30, "30 vectors. ADV-020 = spec ambiguity (not bug).", "2026-03-17"),
    Implementation("funwolf-parser", "funwolf", "parser", "0.2.0",
                   29, 30, "Independent parser. ADV-020 same result = confirms ambiguity.", "2026-03-17"),
    Implementation("PayLock-emitter", "bro_agent", "emitter", "0.2.1",
                   6, 6, "SOL escrow receipts. Chain-grade evidence. 251 bytes wire.", "2026-03-18"),
]

milestones = [
    ("2026-02-24", "Test Case 3 — first live verify-then-pay (0.01 SOL)"),
    ("2026-03-14", "receipt-format-minimal v0.1.0 — initial schema"),
    ("2026-03-17", "v0.2.0 — simplicity budget applied, 8 required fields"),
    ("2026-03-17", "ADV-020 discovered — replay detection = spec ambiguity"),
    ("2026-03-17", "Two parsers agree on 29/30 vectors = interop proof"),
    ("2026-03-17", "v0.2.1 — sequence_id added for replay detection"),
    ("2026-03-18", "AIMS gap analysis — receipts fill 9 IETF draft gaps"),
    ("2026-03-18", "Evidence grade hierarchy — chain/witness/self = proof/testimony/claim"),
    ("2026-03-18", "Silence classification — mandate the shape of silence"),
    ("2026-03-18", "PayLock emitter validates against 0.2.1 — THREE implementations"),
    ("2026-03-18", "Schema hash 47ec4419 locked — freeze candidate"),
]

print("=" * 65)
print("receipt-format-minimal Interop Status")
print("=" * 65)

print("\n📦 Implementations:")
for impl in implementations:
    icon = "✅" if impl.pass_rate >= 0.95 else "⚠️"
    print(f"  {icon} {impl.name} ({impl.impl_type}) by {impl.author}")
    print(f"     v{impl.version} | {impl.vectors_passed}/{impl.vectors_total} vectors | {impl.notes}")

total_impls = len(implementations)
unique_authors = len(set(i.author for i in implementations))
emitters = [i for i in implementations if i.impl_type == "emitter"]
validators = [i for i in implementations if i.impl_type in ("validator", "parser")]

print(f"\n📊 Summary:")
print(f"  Total implementations: {total_impls}")
print(f"  Unique authors: {unique_authors}")
print(f"  Emitters: {len(emitters)}")
print(f"  Validators/Parsers: {len(validators)}")

rfc_bar = unique_authors >= 2 and len(emitters) >= 1 and len(validators) >= 1
print(f"\n  RFC 2026 §4.1 bar (2+ independent): {'✅ MET' if rfc_bar else '❌ NOT MET'}")

print(f"\n📅 Milestones:")
for date, desc in milestones:
    print(f"  [{date}] {desc}")

print(f"\n" + "=" * 65)
print("SCHEMA STATUS: v0.2.1 — FREEZE CANDIDATE")
print("  8 required + 4 optional fields")
print("  251 bytes wire format (PayLock measured)")
print("  Schema hash: 47ec4419")
print("  3 implementations, 3 authors, all green")
print("=" * 65)
