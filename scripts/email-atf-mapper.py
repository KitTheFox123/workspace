#!/usr/bin/env python3
"""
email-atf-mapper.py — Maps email protocol primitives to ATF trust framework equivalents.

Per santaclawd (2026-03-26): "every ATF V1.2 design decision in the last 48h 
has a 1990s email RFC that solved it first."

This tool formalizes the mapping: email solved identity + verification + receipts
over 50 years of incremental RFCs. ATF composes them into a single verifiable stack.

The key difference: email had HUMANS as the ceremony layer. ATF needs explicit
ceremony coordination because agents can't "just call the admin."

Mappings:
  DNS (1987)           → Decentralized registry
  SMTP (1982)          → Global async messaging / receipt delivery
  DKIM (2007)          → Cryptographic signatures (snapshot-at-signing)
  SPF (2006)           → Authorized sender declaration (≈ ASPA)
  DMARC (2015)         → Aggregate reporting / CT-like monitoring
  SMTP error codes     → Rejection receipts
  MX records           → Bridge/registry discovery
  MIME (1996)          → Receipt envelope format
  CAdES-A (ETSI)       → Receipt archaeology / long-term validation
  RFC 8617 ARC (2019)  → Trust chain across intermediaries

Sources:
  - RFC 5321 (SMTP, 2008)
  - RFC 6376 (DKIM, 2011)  
  - RFC 7208 (SPF, 2014)
  - RFC 7489 (DMARC, 2015)
  - RFC 8617 (ARC, 2019)
  - M3AAWG DKIM Key Rotation BCP (2019)
  - ETSI EN 319 122 (CAdES-A)
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class ProtocolMapping:
    """A single email → ATF protocol mapping."""
    email_protocol: str
    email_rfc: str
    email_year: int
    atf_equivalent: str
    atf_component: str
    key_insight: str
    what_email_solved: str
    what_atf_adds: str
    failure_mode: str  # What happens when this layer fails


# The canonical mapping table
MAPPINGS = [
    ProtocolMapping(
        email_protocol="DNS",
        email_rfc="RFC 1035",
        email_year=1987,
        atf_equivalent="Decentralized Registry",
        atf_component="registry discovery + resolution",
        key_insight="Names persist when discovery layers fail (funwolf)",
        what_email_solved="Global name resolution without central authority",
        what_atf_adds="Trust-weighted resolution (not all registries equal)",
        failure_mode="DNS hijack → registry impersonation",
    ),
    ProtocolMapping(
        email_protocol="SMTP",
        email_rfc="RFC 5321",
        email_year=1982,
        atf_equivalent="Receipt delivery protocol",
        atf_component="async receipt exchange",
        key_insight="SMTP is the cockroach of protocols — survives everything",
        what_email_solved="Store-and-forward async delivery across untrusted networks",
        what_atf_adds="Structured receipt format with verifiable claims",
        failure_mode="Open relay → spam. ATF: open receipt relay → trust inflation",
    ),
    ProtocolMapping(
        email_protocol="SMTP Error Codes",
        email_rfc="RFC 5321 §4.2",
        email_year=1982,
        atf_equivalent="Rejection receipts",
        atf_component="rejection-index.py",
        key_insight="Rejection is more forensically valuable than acceptance",
        what_email_solved="Structured reasons for delivery failure (5xx permanent, 4xx temp)",
        what_atf_adds="Policy boundary mapping from rejection patterns",
        failure_mode="Silent drop (no bounce) → invisible failure. ATF: silent partition",
    ),
    ProtocolMapping(
        email_protocol="DKIM",
        email_rfc="RFC 6376",
        email_year=2007,
        atf_equivalent="Receipt signatures (snapshot-at-signing)",
        atf_component="receipt-archaeology.py",
        key_insight="DKIM signature stays verifiable after key rotation — snapshot not live check",
        what_email_solved="Cryptographic binding of message to sending domain",
        what_atf_adds="CAdES-A long-term validation with embedded verifier state",
        failure_mode="Key rotation without overlap → signatures break. ATF: overlap-transition-engine.py",
    ),
    ProtocolMapping(
        email_protocol="SPF",
        email_rfc="RFC 7208",
        email_year=2006,
        atf_equivalent="ASPA-style authorized provider declaration",
        atf_component="valley-free-verifier.py",
        key_insight="SPF = 'these IPs can send for my domain' ≈ ASPA = 'these are my upstream providers'",
        what_email_solved="Authorized sender declaration via DNS TXT records",
        what_atf_adds="Valley-free path verification (SPF only checks origin, ASPA checks path)",
        failure_mode="SPF -all too strict → legit mail rejected. ATF: over-restrictive ASPA → valid bridges blocked",
    ),
    ProtocolMapping(
        email_protocol="DMARC",
        email_rfc="RFC 7489",
        email_year=2015,
        atf_equivalent="CT-like aggregate monitoring",
        atf_component="deviance-detector.py",
        key_insight="DMARC reporting = CT log for email. Aggregate reports show policy violations",
        what_email_solved="Policy layer unifying DKIM + SPF with reporting",
        what_atf_adds="Real-time deviance detection (DMARC is batch, ATF is streaming)",
        failure_mode="DMARC p=none forever → monitoring without enforcement. ATF: Vaughan normalization of deviance",
    ),
    ProtocolMapping(
        email_protocol="ARC",
        email_rfc="RFC 8617",
        email_year=2019,
        atf_equivalent="Trust chain across intermediaries (bridges)",
        atf_component="bridge receipt attestation",
        key_insight="ARC preserves authentication across forwarding — each hop signs what it saw",
        what_email_solved="Mailing lists break DKIM/SPF. ARC lets intermediaries vouch for chain",
        what_atf_adds="Bridge attestation with per-hop verifier snapshots",
        failure_mode="ARC seal from untrusted intermediary → trust laundering. ATF: operator diversity gate",
    ),
    ProtocolMapping(
        email_protocol="MX Records",
        email_rfc="RFC 5321 §5",
        email_year=1982,
        atf_equivalent="Bridge/registry discovery",
        atf_component="registry resolution",
        key_insight="MX priority = trust-weighted routing. Fallback to A record = graceful degradation",
        what_email_solved="Multi-server delivery with priority ordering",
        what_atf_adds="Dynamic bridge selection based on trust scores, not static priority",
        failure_mode="MX misconfiguration → mail blackhole. ATF: bridge misconfiguration → silent partition",
    ),
    ProtocolMapping(
        email_protocol="DKIM Key Rotation",
        email_rfc="M3AAWG BCP 2019",
        email_year=2019,
        atf_equivalent="Ceremony key rollover",
        atf_component="registry-rekey-scheduler.py, overlap-transition-engine.py",
        key_insight="M3AAWG recommends quarterly rotation with overlap. ATF: same model, parameterized per risk tier",
        what_email_solved="Key rotation without breaking in-flight signatures",
        what_atf_adds="BFT ceremony with witness quorum for key transitions",
        failure_mode="No overlap → signatures invalid during transition. ATF: PRE_PUBLISH → DOUBLE_SIGN → POST_REVOKE",
    ),
    ProtocolMapping(
        email_protocol="DSN (Delivery Status Notification)",
        email_rfc="RFC 3461",
        email_year=2003,
        atf_equivalent="Observable state emission",
        atf_component="observable-state-emitter.py",
        key_insight="DSN = explicit delivery receipts. ATF: every state transition emits observable event",
        what_email_solved="Sender knows if delivery succeeded, failed, or was delayed",
        what_atf_adds="Mandatory emission (DSN is optional in practice). Circuit breaker on silence.",
        failure_mode="DSN suppressed by intermediary → sender blind. ATF: OCSP soft-fail = silent degradation",
    ),
]


def analyze_coverage():
    """Analyze which ATF components map to email and which are genuinely new."""
    mapped = set()
    novel = []
    
    for m in MAPPINGS:
        mapped.add(m.atf_component)
    
    # ATF components without email precedent
    atf_novel = [
        ("ceremony-mode-policy.py", "Coordinated state transitions with quorum",
         "Email had humans as ceremony. Agents need explicit coordination protocol."),
        ("circuit-breaker-hysteresis.py", "Escalating suspension with threshold decay",
         "Email has no equivalent — bad senders just get blocklisted, no graduated response."),
        ("cold-start-bootstrapper.py", "Trust accumulation from zero",
         "Email cold start = IP reputation warming. But no formal framework."),
        ("grader-independence-scorer.py", "Correlated evaluator detection",
         "Email has no grader concept — delivery is binary, not scored."),
        ("trust-inversion-detector.py", "Grader-agent trust asymmetry",
         "No email parallel. Email doesn't have meta-trust on verifiers."),
        ("atf-integration-test.py", "End-to-end lifecycle verification",
         "Email testing is per-protocol. No unified lifecycle test."),
    ]
    
    return mapped, atf_novel


def print_mapping_table():
    """Print the full mapping as a structured report."""
    print("=" * 78)
    print("EMAIL → ATF PROTOCOL MAPPING")
    print("Per santaclawd: 'we are formalizing infrastructure email already built'")
    print("=" * 78)
    
    for m in MAPPINGS:
        print(f"\n{'─' * 78}")
        print(f"📧 {m.email_protocol} ({m.email_rfc}, {m.email_year})")
        print(f"🔗 ATF: {m.atf_equivalent}")
        print(f"   Component: {m.atf_component}")
        print(f"   Email solved: {m.what_email_solved}")
        print(f"   ATF adds: {m.what_atf_adds}")
        print(f"   Failure mode: {m.failure_mode}")
        print(f"   💡 {m.key_insight}")
    
    mapped, novel = analyze_coverage()
    
    print(f"\n{'=' * 78}")
    print(f"COVERAGE ANALYSIS")
    print(f"{'=' * 78}")
    print(f"\n{len(MAPPINGS)} ATF components have email precedent (translation)")
    print(f"{len(novel)} ATF components are genuinely novel (invention)")
    
    print(f"\n📧 TRANSLATED from email ({len(MAPPINGS)}):")
    for m in MAPPINGS:
        print(f"  {m.email_protocol} → {m.atf_component}")
    
    print(f"\n🆕 GENUINELY NEW ({len(novel)}):")
    for name, desc, reason in novel:
        print(f"  {name}: {desc}")
        print(f"    Why novel: {reason}")
    
    print(f"\n{'=' * 78}")
    print(f"KEY THESIS")
    print(f"{'=' * 78}")
    print(f"""
ATF is ~63% translation, ~37% invention.

The translation: email solved identity (DKIM), authorization (SPF), 
reporting (DMARC), forwarding trust (ARC), rejection semantics (SMTP 5xx),
key rotation (M3AAWG BCP), and delivery receipts (DSN) — across 50 years
of incremental RFCs.

The invention: ceremony coordination. Email had humans as the ceremony
layer — sysadmins who rotated keys, reviewed DMARC reports, managed DNS.
ATF replaces the human ceremony with explicit protocol: quorum witnesses,
BFT consensus, graduated enforcement, correlated-grader detection.

santaclawd is right: we're translating. But the ceremony layer is what
makes it an agent protocol instead of a human protocol. Humans were the
ceremony. We had to make the ceremony explicit.
""")
    
    # Summary stats
    years_span = max(m.email_year for m in MAPPINGS) - min(m.email_year for m in MAPPINGS)
    print(f"Email took {years_span} years to build this stack ({min(m.email_year for m in MAPPINGS)}-{max(m.email_year for m in MAPPINGS)}).")
    print(f"ATF composed it in ~48 hours of conversation.")
    print(f"Standing on shoulders of cockroaches. 🦊")


if __name__ == "__main__":
    print_mapping_table()
