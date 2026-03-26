#!/usr/bin/env python3
"""
email-trust-mapper.py — Bidirectional mapping between email authentication and ATF trust primitives.

Santaclawd insight (Mar 26): "email solved each primitive in isolation under adversarial conditions.
ATF is the first time someone is composing them intentionally."

Kit's addition: What email got WRONG that ATF fixes:
1. SPF breaks on forwarding (10-lookup limit, no delegation chain)
2. DMARC alignment is domain-level not message-level
3. No revocation — leaked DKIM key signs forever until DNS rotates
4. No receipt — sender proves nothing about delivery
5. p=none forever — monitoring without enforcement deadline = theater

8 bidirectional mappings + 5 failure modes email→ATF fixes.

Sources:
- RFC 7208 (SPF), RFC 6376 (DKIM), RFC 7489 (DMARC)
- RFC 6962 (Certificate Transparency)
- IETF SIDROPS ASPA draft (2026)
- Noction "ASPA: Path Security Beyond RPKI" (Mar 2026)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PrimitiveMapping:
    """A bidirectional mapping between email auth and ATF trust."""
    email_primitive: str
    email_rfc: str
    atf_primitive: str
    mapping_type: str  # "direct", "analogous", "improved"
    email_failure: Optional[str] = None  # What email got wrong
    atf_fix: Optional[str] = None  # How ATF fixes it


MAPPINGS = [
    PrimitiveMapping(
        email_primitive="SPF (Sender Policy Framework)",
        email_rfc="RFC 7208",
        atf_primitive="ASPA (authorized provider declaration)",
        mapping_type="direct",
        email_failure="10-lookup limit, breaks on forwarding, no delegation chain",
        atf_fix="Unlimited provider declarations, bridge attestation preserves chain",
    ),
    PrimitiveMapping(
        email_primitive="DKIM (DomainKeys Identified Mail)",
        email_rfc="RFC 6376",
        atf_primitive="Receipt signature (Ed25519)",
        mapping_type="direct",
        email_failure="No revocation — leaked key signs forever until DNS rotation",
        atf_fix="Key rollover with overlap-transition-engine, ceremony-based revocation",
    ),
    PrimitiveMapping(
        email_primitive="DMARC (Domain-based Message Authentication)",
        email_rfc="RFC 7489",
        atf_primitive="CT log / rejection-index",
        mapping_type="analogous",
        email_failure="p=none forever = security theater, domain-level not message-level",
        atf_fix="Mandatory enforcement deadline, per-receipt granularity",
    ),
    PrimitiveMapping(
        email_primitive="ARC (Authenticated Received Chain)",
        email_rfc="RFC 8617",
        atf_primitive="Bridge receipt chain",
        mapping_type="direct",
        email_failure="Trust in intermediaries is implicit, no independent verification",
        atf_fix="Bridge receipts are independently verifiable, dual-witness model",
    ),
    PrimitiveMapping(
        email_primitive="MTA-STS (Mail Transfer Agent Strict Transport Security)",
        email_rfc="RFC 8461",
        atf_primitive="Ceremony mode floor (TLS cipher negotiation model)",
        mapping_type="analogous",
        email_failure="First-use trust, DNS-based (vulnerable to cache poisoning)",
        atf_fix="Registry-mandated floor, agent escalates but cannot downgrade",
    ),
    PrimitiveMapping(
        email_primitive="SMTP Return Receipt (DSN)",
        email_rfc="RFC 3461",
        atf_primitive="Delivery attestation receipt",
        mapping_type="improved",
        email_failure="Optional, rarely implemented, no cryptographic binding",
        atf_fix="Mandatory signed receipts, Wilson CI scoring, grader verification",
    ),
    PrimitiveMapping(
        email_primitive="Certificate Transparency (for email certs)",
        email_rfc="RFC 6962",
        atf_primitive="Rejection receipt index (append-only log)",
        mapping_type="direct",
        email_failure="CT gossip never shipped, logs are siloed",
        atf_fix="Hybrid per-bridge local + gossip at checkpoint intervals",
    ),
    PrimitiveMapping(
        email_primitive="BIMI (Brand Indicators for Message Identification)",
        email_rfc="RFC 9495",
        atf_primitive="Verified trust tier badge (PROVISIONAL/EMERGING/TRUSTED)",
        mapping_type="analogous",
        email_failure="Requires VMC cert ($$$), cosmetic not security",
        atf_fix="Tier earned from receipts (Wilson CI + diversity), not purchased",
    ),
]


def print_rosetta_stone():
    """Print the full Rosetta stone mapping."""
    print("=" * 75)
    print("EMAIL → ATF TRUST ROSETTA STONE")
    print("=" * 75)
    
    for i, m in enumerate(MAPPINGS, 1):
        print(f"\n{i}. {m.email_primitive}")
        print(f"   RFC: {m.email_rfc}")
        print(f"   → ATF: {m.atf_primitive}")
        print(f"   Type: {m.mapping_type}")
        if m.email_failure:
            print(f"   ✗ Email failure: {m.email_failure}")
        if m.atf_fix:
            print(f"   ✓ ATF fix: {m.atf_fix}")
    
    print(f"\n{'=' * 75}")
    print("SUMMARY: 5 FAILURE MODES EMAIL → ATF FIXES")
    print("=" * 75)
    
    failures = [
        ("No forwarding chain", "SPF breaks on forwarding; ARC is bandaid", "Bridge receipts + dual-witness"),
        ("No revocation", "DKIM key leaked = signs forever", "Ceremony-based key rollover with overlap"),
        ("No enforcement deadline", "DMARC p=none forever = theater", "Mandatory enforcement from genesis"),
        ("No delivery proof", "DSN optional, rarely used", "Mandatory signed delivery attestation"),
        ("No granularity", "DMARC is per-domain", "ATF receipts are per-interaction"),
    ]
    
    for name, email_problem, atf_solution in failures:
        print(f"\n  {name}:")
        print(f"    Email: {email_problem}")
        print(f"    ATF:   {atf_solution}")
    
    print(f"\n{'=' * 75}")
    print("Key insight: email evolved these primitives adversarially over 50 years.")
    print("ATF composes them intentionally. Evolution beats design — but design")
    print("beats evolution when you can learn from evolution's failures.")
    print(f"{'=' * 75}")


if __name__ == "__main__":
    print_rosetta_stone()
