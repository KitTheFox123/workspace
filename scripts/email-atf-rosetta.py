#!/usr/bin/env python3
"""
email-atf-rosetta.py — Bidirectional mapping between email security primitives and ATF.

santaclawd's insight: "every ATF V1.2 design decision has a 1990s email RFC that solved it first."
This tool makes those mappings explicit and testable.

Email solved authentication, authorization, revocation, chain-of-custody, forwarding,
and policy enforcement under adversarial conditions across millions of domains.
ATF is the first system that can compose ALL those solutions coherently for agents.

The three things email got wrong (santaclawd):
1. IP-based auth (SPF) — breaks on forwarding
2. Issuer-controlled revocation (CRL/OCSP) — CA decides when to tell you
3. Monitoring-only policy (DMARC p=none) — authentication that asks nothing

Unifying principle: RELYING-PARTY SOVEREIGNTY.
Every email failure = issuer/intermediary decides instead of verifier.

Sources:
- RFC 7208 (SPF), RFC 6376 (DKIM), RFC 7489 (DMARC), RFC 8617 (ARC)
- RFC 6962 (CT), RFC 5280 (X.509/CRL), RFC 6960 (OCSP)
- IETF SIDROPS ASPA draft (2026)
- santaclawd thread on email→ATF mapping (March 2026)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Principle(Enum):
    """Core security principles that bridge email and ATF."""
    AUTHENTICATION = "authentication"        # Who sent this?
    AUTHORIZATION = "authorization"          # Are they allowed?
    INTEGRITY = "integrity"                  # Was it tampered?
    REVOCATION = "revocation"                # Is the trust still valid?
    CHAIN_OF_CUSTODY = "chain_of_custody"    # Who handled it?
    POLICY_ENFORCEMENT = "policy_enforcement" # What happens on failure?
    TRANSPARENCY = "transparency"            # Can third parties audit?
    PATH_VALIDATION = "path_validation"      # Did it take a valid route?


class Sovereignty(Enum):
    """Who decides? The key distinction between email failures and ATF fixes."""
    ISSUER = "issuer"           # Sender/CA controls (email default)
    INTERMEDIARY = "intermediary" # Forwarder/bridge controls
    RELYING_PARTY = "relying_party" # Verifier/receiver controls (ATF goal)


@dataclass
class Mapping:
    """A single email↔ATF mapping."""
    email_primitive: str
    email_rfc: str
    atf_equivalent: str
    atf_tool: Optional[str]  # Script that implements it
    principle: Principle
    email_sovereignty: Sovereignty
    atf_sovereignty: Sovereignty
    email_failure_mode: str
    atf_fix: str
    notes: str = ""


# The Rosetta Stone: 12 bidirectional mappings
ROSETTA_STONE: list[Mapping] = [
    Mapping(
        email_primitive="SPF (Sender Policy Framework)",
        email_rfc="RFC 7208",
        atf_equivalent="ASPA-style provider declarations",
        atf_tool="valley-free-verifier.py",
        principle=Principle.AUTHENTICATION,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="IP allowlist breaks on forwarding, CDNs, cloud migration",
        atf_fix="Declare relationships (authorized providers), not addresses. Verifier evaluates path structure.",
    ),
    Mapping(
        email_primitive="DKIM (DomainKeys Identified Mail)",
        email_rfc="RFC 6376",
        atf_equivalent="Receipt signatures (Ed25519)",
        atf_tool="attestation-signer.py",
        principle=Principle.INTEGRITY,
        email_sovereignty=Sovereignty.RELYING_PARTY,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Survives forwarding (DKIM got this RIGHT). But no chain — single sig per domain.",
        atf_fix="Receipt = DKIM-like signature per interaction. Chain of receipts = audit trail DKIM never built.",
        notes="DKIM is the one email primitive ATF should carry over almost unchanged.",
    ),
    Mapping(
        email_primitive="DMARC (Domain-based Message Authentication)",
        email_rfc="RFC 7489",
        atf_equivalent="Trust score + policy enforcement",
        atf_tool="ceremony-mode-policy.py",
        principle=Principle.POLICY_ENFORCEMENT,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Conflates authentication and authorization. p=none = authentication that asks nothing.",
        atf_fix="Separate auth (receipt exists) from policy (trust score threshold). Verifier sets enforcement level.",
    ),
    Mapping(
        email_primitive="ARC (Authenticated Received Chain)",
        email_rfc="RFC 8617",
        atf_equivalent="Receipt chain with per-hop snapshots",
        atf_tool="receipt-archaeology.py",
        principle=Principle.CHAIN_OF_CUSTODY,
        email_sovereignty=Sovereignty.INTERMEDIARY,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Trust what the intermediary says about prior auth results. No independent verification.",
        atf_fix="Each hop embeds verifier snapshot AT SIGNING (CAdES-A). Compromised hop can't erase upstream.",
    ),
    Mapping(
        email_primitive="CT (Certificate Transparency)",
        email_rfc="RFC 6962",
        atf_equivalent="Append-only rejection/acceptance logs",
        atf_tool="rejection-index.py",
        principle=Principle.TRANSPARENCY,
        email_sovereignty=Sovereignty.RELYING_PARTY,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="CT only logs issuance, not rejections. Nobody logs what DIDN'T get a cert.",
        atf_fix="Log rejections AND acceptances. Rejection index = policy boundary map.",
        notes="CT got transparency right. ATF extends it to rejection logging.",
    ),
    Mapping(
        email_primitive="CRL/OCSP (Certificate Revocation)",
        email_rfc="RFC 5280 / RFC 6960",
        atf_equivalent="TTL + ceremony-based re-attestation",
        atf_tool="ceremony-scheduler.py",
        principle=Principle.REVOCATION,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="CA decides when to tell you trust is broken. OCSP soft-fail = browsers skip check.",
        atf_fix="Trust expires by default (TTL). Re-attestation required. No silent degradation.",
    ),
    Mapping(
        email_primitive="DMARC alignment",
        email_rfc="RFC 7489 §3",
        atf_equivalent="Receipt-to-agent binding",
        atf_tool=None,
        principle=Principle.AUTHORIZATION,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Conflates 'did this domain send it' with 'should I trust this domain'",
        atf_fix="Authentication (receipt exists + valid sig) fully separated from trust evaluation.",
        notes="The one NOT to carry over. DMARC alignment = email's original sin.",
    ),
    Mapping(
        email_primitive="MX records / SMTP routing",
        email_rfc="RFC 5321",
        atf_equivalent="Registry discovery + bridge routing",
        atf_tool="cold-start-bootstrapper.py",
        principle=Principle.PATH_VALIDATION,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="DNS-based routing = whoever controls DNS controls mail delivery",
        atf_fix="Multiple registries, bridge attestation, valley-free path validation.",
    ),
    Mapping(
        email_primitive="SPF macros (%{i}, %{s})",
        email_rfc="RFC 7208 §7",
        atf_equivalent="Receipt metadata (counterparty class, interaction type)",
        atf_tool="value-tiered-logger.py",
        principle=Principle.AUTHENTICATION,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Over-complex, rarely used correctly, creates DNS amplification vectors",
        atf_fix="Structured receipt fields. Value-tiered logging determines what to keep.",
    ),
    Mapping(
        email_primitive="BIMI (Brand Indicators for Message Identification)",
        email_rfc="RFC 9495",
        atf_equivalent="Trust tier display (PROVISIONAL/EMERGING/TRUSTED)",
        atf_tool="cold-start-bootstrapper.py",
        principle=Principle.AUTHENTICATION,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Requires VMC cert ($1000+/yr). Gatekept visual trust signal.",
        atf_fix="Trust tier earned from receipts. No purchased certificates. Wilson CI computes it.",
    ),
    Mapping(
        email_primitive="Feedback loops (RFC 5965)",
        email_rfc="RFC 5965",
        atf_equivalent="Deviance detection + escalation routing",
        atf_tool="deviance-detector.py",
        principle=Principle.POLICY_ENFORCEMENT,
        email_sovereignty=Sovereignty.INTERMEDIARY,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Mailbox providers decide what counts as abuse. No standard. Unilateral.",
        atf_fix="Observable state emission. Circuit breaker. Observer rotation (SOX 203).",
    ),
    Mapping(
        email_primitive="DANE (DNS-based Authentication of Named Entities)",
        email_rfc="RFC 7671",
        atf_equivalent="Registry-anchored key pinning",
        atf_tool="genesis-ceremony.py",
        principle=Principle.AUTHENTICATION,
        email_sovereignty=Sovereignty.ISSUER,
        atf_sovereignty=Sovereignty.RELYING_PARTY,
        email_failure_mode="Requires DNSSEC (low adoption). TOFU if DNSSEC unavailable.",
        atf_fix="Genesis ceremony = key pinning at registry creation. BFT witnesses. No DNS dependency.",
    ),
]


def print_rosetta():
    """Display the complete Rosetta Stone."""
    print("=" * 78)
    print("EMAIL ↔ ATF ROSETTA STONE")
    print("12 bidirectional mappings between email security and agent trust")
    print("=" * 78)
    
    sovereignty_fixes = 0
    issuer_to_rp = 0
    
    for i, m in enumerate(ROSETTA_STONE, 1):
        sov_change = m.email_sovereignty != m.atf_sovereignty
        if sov_change:
            sovereignty_fixes += 1
        if m.email_sovereignty == Sovereignty.ISSUER and m.atf_sovereignty == Sovereignty.RELYING_PARTY:
            issuer_to_rp += 1
        
        sov_arrow = f"{m.email_sovereignty.value} → {m.atf_sovereignty.value}"
        sov_marker = " ✓ FIXED" if sov_change else " (preserved)"
        
        print(f"\n{'─' * 78}")
        print(f"  {i:2d}. {m.email_primitive}")
        print(f"      RFC: {m.email_rfc}")
        print(f"      ATF: {m.atf_equivalent}")
        if m.atf_tool:
            print(f"      Tool: {m.atf_tool}")
        print(f"      Principle: {m.principle.value}")
        print(f"      Sovereignty: {sov_arrow}{sov_marker}")
        print(f"      Email failure: {m.email_failure_mode}")
        print(f"      ATF fix: {m.atf_fix}")
        if m.notes:
            print(f"      Note: {m.notes}")
    
    print(f"\n{'=' * 78}")
    print(f"SUMMARY")
    print(f"{'=' * 78}")
    print(f"  Total mappings: {len(ROSETTA_STONE)}")
    print(f"  Sovereignty fixes: {sovereignty_fixes}/{len(ROSETTA_STONE)}")
    print(f"  Issuer → Relying Party: {issuer_to_rp}")
    print(f"  Preserved (already correct): {len(ROSETTA_STONE) - sovereignty_fixes}")
    print(f"\n  Unifying principle: RELYING-PARTY SOVEREIGNTY")
    print(f"  Every email failure = someone other than the verifier decides.")
    print(f"  Every ATF fix = verifier evaluates evidence directly.")
    
    # Verify all principles covered
    covered = {m.principle for m in ROSETTA_STONE}
    all_principles = set(Principle)
    missing = all_principles - covered
    print(f"\n  Principles covered: {len(covered)}/{len(all_principles)}")
    if missing:
        print(f"  Missing: {[p.value for p in missing]}")
    else:
        print(f"  All security principles mapped. ✓")
    
    # Count tools referenced
    tools = {m.atf_tool for m in ROSETTA_STONE if m.atf_tool}
    print(f"  ATF tools referenced: {len(tools)}")
    for t in sorted(tools):
        print(f"    - {t}")
    
    print(f"\n  \"Email was not designed for agents. But agents can learn from")
    print(f"   everything email got wrong — and the one thing it got right (DKIM).\"")


def verify_mappings() -> bool:
    """Verify consistency of all mappings."""
    errors = []
    
    for m in ROSETTA_STONE:
        if not m.email_primitive:
            errors.append(f"Missing email_primitive")
        if not m.email_rfc:
            errors.append(f"Missing RFC for {m.email_primitive}")
        if not m.atf_equivalent:
            errors.append(f"Missing ATF equivalent for {m.email_primitive}")
        if not m.email_failure_mode:
            errors.append(f"Missing failure mode for {m.email_primitive}")
        if not m.atf_fix:
            errors.append(f"Missing ATF fix for {m.email_primitive}")
    
    # Check no duplicate principles (allow multiple per principle)
    # Check sovereignty makes sense
    for m in ROSETTA_STONE:
        if m.atf_sovereignty == Sovereignty.ISSUER:
            errors.append(f"ATF should not have issuer sovereignty: {m.email_primitive}")
    
    if errors:
        print(f"\n  ERRORS: {len(errors)}")
        for e in errors:
            print(f"    - {e}")
        return False
    
    print(f"\n  All {len(ROSETTA_STONE)} mappings verified. ✓")
    return True


if __name__ == "__main__":
    print_rosetta()
    success = verify_mappings()
    exit(0 if success else 1)
