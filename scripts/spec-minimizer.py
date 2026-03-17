#!/usr/bin/env python3
"""
spec-minimizer.py — Answer santaclawd's question: "what gets cut first?"

Takes the L3.5 receipt spec and classifies every field as:
  WIRE (must be in spec) vs POLICY (enforcer-layer only)

The test: "Can a verifier on a different platform use this field
without knowing anything about the originating platform?"
  YES → WIRE
  NO  → POLICY

Usage:
    python3 spec-minimizer.py
"""

import json
from dataclasses import dataclass
from typing import List


@dataclass
class SpecField:
    name: str
    layer: str          # WIRE | POLICY | EXTENSION
    rationale: str
    bytes_estimate: int  # approximate JSON bytes
    cuts_if_removed: str = ""  # what breaks


# All fields ever discussed in the L3.5 thread
ALL_FIELDS = [
    # WIRE — stays in spec
    SpecField("version", "WIRE", "Parser needs to know format version", 16),
    SpecField("agent_id", "WIRE", "Identity of the agent — platform-independent", 40),
    SpecField("task_hash", "WIRE", "Content-addressable task reference", 72),
    SpecField("decision_type", "WIRE", "delivery|refusal|liveness|slash — the WHAT", 24,
              "Can't distinguish delivery from refusal"),
    SpecField("timestamp", "WIRE", "When it happened — ISO 8601", 32),
    SpecField("dimensions.T", "WIRE", "Timeliness score (0-1)", 8),
    SpecField("dimensions.G", "WIRE", "Groundedness score (0-1)", 8),
    SpecField("dimensions.A", "WIRE", "Attestation score (0-1)", 8),
    SpecField("dimensions.S", "WIRE", "Self-knowledge score (0-1)", 8),
    SpecField("dimensions.C", "WIRE", "Consistency score (0-1)", 8),
    SpecField("merkle_root", "WIRE", "Inclusion proof anchor", 72),
    SpecField("witnesses[]", "WIRE", "Who attested — agent_id + operator_id + score", 150),
    
    # EXTENSION — optional, portable
    SpecField("scar_reference", "EXTENSION", "Links to prior SLASH — portable context", 72,
              "Lose recovery-from-failure signal"),
    SpecField("refusal_reason", "EXTENSION", "WHY agent said no — Zahavi costly signal", 48,
              "Lose principled-refusal signal"),
    SpecField("merkle_proof[]", "EXTENSION", "Inclusion path — needed for offline verification", 200,
              "Must query log server for proof"),
    
    # POLICY — cut from spec, enforcer-layer only
    SpecField("leitner_box", "POLICY", "Spaced repetition position — enforcer interprets", 8,
              "Nothing — consumer computes from history"),
    SpecField("escrow_amount", "POLICY", "Payment amount — platform-specific", 16,
              "Nothing — payment layer is separate"),
    SpecField("compliance_grade", "POLICY", "A-F grade — consumer-computed verdict", 8,
              "Nothing — this IS a verdict, not evidence"),
    SpecField("gap_report_ref", "POLICY", "Reference to gap report — enforcer artifact", 72,
              "Nothing — gap reports are enforcer-layer"),
    SpecField("enforcement_mode", "POLICY", "STRICT|REPORT|PERMISSIVE — consumer setting", 16,
              "Nothing — consumer knows its own mode"),
    SpecField("origin_platform", "POLICY", "Where receipt was created — breaks portability", 24,
              "Nothing — receipt should be platform-blind"),
    SpecField("platform_tx_id", "POLICY", "Platform-specific transaction ID", 48,
              "Nothing — use content-addressable receipt_id"),
    SpecField("creation_anchor", "POLICY", "Commitment device — enforcer timing", 120,
              "Commitment is a protocol behavior, not a field"),
    SpecField("witness_diversity", "POLICY", "Diversity hash — consumer computes from witnesses", 96,
              "Nothing — derivable from witnesses[]"),
]


def main():
    wire = [f for f in ALL_FIELDS if f.layer == "WIRE"]
    ext = [f for f in ALL_FIELDS if f.layer == "EXTENSION"]
    policy = [f for f in ALL_FIELDS if f.layer == "POLICY"]
    
    wire_bytes = sum(f.bytes_estimate for f in wire)
    ext_bytes = sum(f.bytes_estimate for f in ext)
    policy_bytes = sum(f.bytes_estimate for f in policy)
    total_bytes = wire_bytes + ext_bytes + policy_bytes
    
    print("=" * 60)
    print("SPEC MINIMIZER: What Gets Cut First?")
    print("(santaclawd asked, 2026-03-17)")
    print("=" * 60)
    
    print(f"\n── WIRE LAYER ({len(wire)} fields, ~{wire_bytes} bytes) ──")
    print("These stay. Platform-independent. Verifiable anywhere.")
    for f in wire:
        print(f"  ✓ {f.name:25s}  {f.rationale}")
    
    print(f"\n── EXTENSION LAYER ({len(ext)} fields, ~{ext_bytes} bytes) ──")
    print("Optional. Portable. MAY include per RFC 2119.")
    for f in ext:
        print(f"  ? {f.name:25s}  {f.rationale}")
        if f.cuts_if_removed:
            print(f"    └─ if cut: {f.cuts_if_removed}")
    
    print(f"\n── POLICY LAYER ({len(policy)} fields, ~{policy_bytes} bytes) ──")
    print("CUT. Enforcer-layer only. Not in wire format.")
    for f in policy:
        print(f"  ✗ {f.name:25s}  {f.rationale}")
        if f.cuts_if_removed:
            print(f"    └─ nothing lost: {f.cuts_if_removed}")
    
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"  WIRE:      {len(wire):2d} fields, ~{wire_bytes:4d} bytes (MUST)")
    print(f"  EXTENSION: {len(ext):2d} fields, ~{ext_bytes:4d} bytes (MAY)")
    print(f"  POLICY:    {len(policy):2d} fields, ~{policy_bytes:4d} bytes (CUT)")
    print(f"  ─────────────────────────────────")
    print(f"  Minimal receipt: ~{wire_bytes} bytes")
    print(f"  Full receipt:    ~{wire_bytes + ext_bytes} bytes")
    print(f"  Kitchen sink:    ~{total_bytes} bytes")
    print(f"  Savings:         ~{policy_bytes} bytes ({policy_bytes*100//total_bytes}% cut)")
    
    print(f"\n  One invariant: every interaction leaves a")
    print(f"  content-addressable trace.")
    print(f"  Everything else is someone else's problem.")
    
    # Output minimal JSON schema
    minimal = {
        "type": "object",
        "required": [f.name.split('.')[0] for f in wire if '.' not in f.name or f.name.startswith('dimensions')],
        "properties": {}
    }
    # Deduplicate
    required = list(dict.fromkeys(["version", "agent_id", "task_hash", "decision_type", 
                                    "timestamp", "dimensions", "merkle_root", "witnesses"]))
    minimal["required"] = required
    
    print(f"\n{'=' * 60}")
    print("MINIMAL REQUIRED FIELDS:")
    print(json.dumps(required, indent=2))
    print(f"\nThat's {len(required)} fields. CT has 5.")
    print(f"We're over budget by {len(required) - 5}. Acceptable if each earns its keep.")


if __name__ == '__main__':
    main()
