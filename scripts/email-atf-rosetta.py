#!/usr/bin/env python3
"""
email-atf-rosetta.py — Rosetta Stone mapping email RFCs to ATF primitives.

Per santaclawd's insight: "every ATF V1.2 design decision has a 1990s email RFC
that solved it first." This tool makes the mapping explicit and bidirectional.

Email stack → ATF stack:
  SPF (RFC 7208)     → ASPA provider declaration (authorized trust sources)
  DKIM (RFC 6376)    → Receipt signing (cryptographic endorsement)
  DMARC (RFC 7489)   → Policy enforcement + aggregate reporting
  SMTP bounce codes  → Rejection receipts (diagnostic reason codes)
  DNSSEC KSK rollover → Ceremony (trust anchor rotation)
  MX records         → Registry discovery
  ARC (RFC 8617)     → Trust chain forwarding (intermediate attestation)

Key insight: email survived because it interoperated across hostile networks
from day one. DKIM/SPF/DMARC are incrementally deployable — exactly like ASPA.
The adoption curve is the same: years of standardization, cautious early
adoption, then rapid acceleration once major players enforce.

Sources:
- RFC 7208 (SPF), RFC 6376 (DKIM), RFC 7489 (DMARC)
- RFC 8617 (ARC - Authenticated Received Chain)
- RFC 5321 (SMTP), RFC 3461 (DSN - Delivery Status Notifications)
- IETF SIDROPS ASPA draft (2026)
- santaclawd Clawk thread (2026-03-26)
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RFCMapping:
    """Maps an email RFC concept to an ATF primitive."""
    email_concept: str
    email_rfc: str
    email_mechanism: str
    atf_concept: str
    atf_primitive: str
    mapping_strength: str  # "exact", "strong", "analogous"
    key_insight: str
    failure_mode_shared: str


# The Rosetta Stone
MAPPINGS = [
    RFCMapping(
        email_concept="Sender Policy Framework",
        email_rfc="RFC 7208 (2014)",
        email_mechanism="DNS TXT record listing authorized sending IPs/hosts for a domain",
        atf_concept="ASPA Provider Declaration",
        atf_primitive="ASPARecord.authorized_providers",
        mapping_strength="exact",
        key_insight="Both declare 'these are my authorized upstream sources.' SPF says 'these IPs can send as me.' ASPA says 'these ASes are my providers.' ATF says 'these registries anchor my trust.'",
        failure_mode_shared="Incomplete records cause false rejections. SPF -all without listing all senders = bounced mail. ASPA without listing all providers = INVALID paths. ATF without listing all registries = rejected endorsements.",
    ),
    RFCMapping(
        email_concept="DomainKeys Identified Mail",
        email_rfc="RFC 6376 (2011)",
        email_mechanism="Cryptographic signature over email headers+body, verified via DNS public key",
        atf_concept="Receipt Signing",
        atf_primitive="receipt.signature (Ed25519/RSA)",
        mapping_strength="exact",
        key_insight="Both sign content at origin, verify at destination. DKIM signature survives forwarding. ATF receipt signature survives bridge crossing. Neither requires the intermediary to be trusted — only the signer.",
        failure_mode_shared="Key rotation without overlap = verification gap. DKIM key published in DNS; if rotated without TTL overlap, in-flight messages fail. ATF key rotated without ceremony overlap = receipts fail. overlap-transition-engine.py solves this.",
    ),
    RFCMapping(
        email_concept="DMARC Policy + Reporting",
        email_rfc="RFC 7489 (2015)",
        email_mechanism="Policy record (none/quarantine/reject) + aggregate XML reports from receivers",
        atf_concept="Trust Policy Enforcement + Deviance Reporting",
        atf_primitive="ceremony-mode-policy.py + deviance-detector.py",
        mapping_strength="strong",
        key_insight="DMARC = 'here is my policy AND send me reports about violations.' ATF ceremony-mode-policy = 'here is my trust floor AND deviance-detector reports violations.' Both shift power to the domain owner (sender/agent) while requiring receiver cooperation for reporting.",
        failure_mode_shared="Policy without monitoring = false confidence. DMARC p=reject without reading aggregate reports = silent delivery failures. ATF CIRCUIT_BREAKER without observer rotation = normalized deviance (Vaughan).",
    ),
    RFCMapping(
        email_concept="SMTP Bounce Codes (DSN)",
        email_rfc="RFC 3461 (2003) + RFC 3464",
        email_mechanism="Structured error codes: 5.1.1 (user unknown), 5.7.1 (policy rejection), 4.x.x (temporary)",
        atf_concept="Rejection Receipts",
        atf_primitive="rejection-index.py reason_codes",
        mapping_strength="exact",
        key_insight="SMTP bounce = structured rejection with diagnostic code. ATF rejection receipt = structured refusal with reason code. Both are MORE forensically valuable than acceptance. A map of bounces = a map of policy boundaries. alphasenpai's 0x0B = SMTP 5.7.1.",
        failure_mode_shared="Silent discard (no bounce) = worst failure mode. SMTP blackhole = messages vanish. ATF silent partition = bridge accepts without signing. Both solved by requiring receipts: DSN for email, dual-witness for ATF.",
    ),
    RFCMapping(
        email_concept="Authenticated Received Chain",
        email_rfc="RFC 8617 (2019)",
        email_mechanism="Each intermediary (mailing list, forwarder) adds ARC signature preserving original auth results",
        atf_concept="Trust Chain Forwarding",
        atf_primitive="valley-free-verifier.py path validation",
        mapping_strength="strong",
        key_insight="ARC solves DKIM breakage during forwarding. Each hop signs a snapshot of auth state. ATF bridge receipts solve trust breakage during cross-registry traversal. Each bridge hop adds attestation preserving origin trust. ARC-Seal = bridge receipt signature.",
        failure_mode_shared="Unattested intermediary = trust gap. Email forwarded without ARC = DKIM fails at destination. Trust forwarded without bridge receipt = origin trust lost. Both require every intermediary to actively participate.",
    ),
    RFCMapping(
        email_concept="DNSSEC Key Signing Key Rollover",
        email_rfc="RFC 6781 (2012) + RFC 7583",
        email_mechanism="Root KSK ceremony: multi-party, geographically distributed, audited, periodic",
        atf_concept="Registry Trust Ceremony",
        atf_primitive="genesis-ceremony.py + ceremony-scheduler.py",
        mapping_strength="exact",
        key_insight="DNSSEC KSK rollover IS the ceremony model. ICANN does it with 7 roles, 2 facilities, key shares. ATF does it with BFT 3f+1 witnesses, operator diversity, hash-chained transcript. Same problem: rotate the root of trust without breaking the chain.",
        failure_mode_shared="Delayed rollover = stale root. DNSSEC KSK-2017 was delayed 1 year because 5% of resolvers hadn't updated. ATF ceremony delayed = STALE trust. Verisign lesson: be willing to delay for propagation.",
    ),
    RFCMapping(
        email_concept="MX Records",
        email_rfc="RFC 5321 (2008)",
        email_mechanism="DNS records declaring which servers handle mail for a domain, with priority",
        atf_concept="Registry Discovery",
        atf_primitive="agent ASPA record → registry lookup",
        mapping_strength="analogous",
        key_insight="MX records = 'to reach me, talk to these servers.' Agent ASPA = 'to verify me, check these registries.' Both use DNS-like discovery. Priority in MX = preference order. ATF could use weighted registry preferences.",
        failure_mode_shared="Stale MX = mail blackhole. Stale registry pointer = trust verification fails. TTL on both matters.",
    ),
    RFCMapping(
        email_concept="Certificate Transparency for Email (SMTP-TLS-RPT)",
        email_rfc="RFC 8460 (2018)",
        email_mechanism="Receivers report TLS connection failures to senders via aggregate reports",
        atf_concept="Cross-Registry Divergence Detection",
        atf_primitive="divergence-detector.py",
        mapping_strength="strong",
        key_insight="SMTP-TLS-RPT = receivers tell senders about connection security failures. ATF divergence-detector = registries tell each other about trust score disagreements. Both are feedback loops that detect silent degradation.",
        failure_mode_shared="Without reporting, failures are invisible. Email TLS downgrades silently without RPT. Trust score divergence is invisible without cross-registry gossip.",
    ),
]


def print_rosetta():
    """Print the full Rosetta Stone mapping."""
    print("=" * 78)
    print("EMAIL → ATF ROSETTA STONE")
    print("Every ATF primitive has an email RFC that solved it first.")
    print("=" * 78)
    
    for i, m in enumerate(MAPPINGS, 1):
        print(f"\n{'─' * 78}")
        print(f"  {i}. {m.email_concept} → {m.atf_concept}")
        print(f"{'─' * 78}")
        print(f"  Email: {m.email_rfc}")
        print(f"  Mechanism: {m.email_mechanism}")
        print(f"  ATF: {m.atf_primitive}")
        print(f"  Strength: {m.mapping_strength.upper()}")
        print(f"  Insight: {m.key_insight}")
        print(f"  Shared failure: {m.failure_mode_shared}")
    
    # Summary table
    print(f"\n{'=' * 78}")
    print(f"SUMMARY: {len(MAPPINGS)} mappings")
    print(f"{'=' * 78}")
    print(f"  {'Email RFC':<30} {'ATF Primitive':<30} {'Strength':<10}")
    print(f"  {'─' * 68}")
    for m in MAPPINGS:
        print(f"  {m.email_rfc:<30} {m.atf_primitive:<30} {m.mapping_strength:<10}")
    
    exact = sum(1 for m in MAPPINGS if m.mapping_strength == "exact")
    strong = sum(1 for m in MAPPINGS if m.mapping_strength == "strong")
    analogous = sum(1 for m in MAPPINGS if m.mapping_strength == "analogous")
    
    print(f"\n  Exact: {exact} | Strong: {strong} | Analogous: {analogous}")
    print(f"\n  Key pattern: email interoperated across hostile networks from 1971.")
    print(f"  ATF must do the same. The primitives are identical because the")
    print(f"  problem is identical: authenticated messaging between untrusted parties.")
    print(f"\n  \"SMTP is the cockroach of protocols.\" — Kit")
    print(f"  \"We are formalizing infrastructure email already built.\" — santaclawd")


def verify_completeness():
    """Check ATF scripts that have email RFC equivalents."""
    atf_scripts = [
        "valley-free-verifier.py",
        "rejection-index.py",
        "divergence-detector.py",
        "ceremony-scheduler.py",
        "genesis-ceremony.py",
        "overlap-transition-engine.py",
        "ceremony-mode-policy.py",
        "deviance-detector.py",
        "cold-start-bootstrapper.py",
        "receipt-archaeology.py",
        "grader-independence-scorer.py",
        "observer-rotation-scheduler.py",
        "circuit-breaker-hysteresis.py",
    ]
    
    mapped_primitives = {m.atf_primitive for m in MAPPINGS}
    
    print(f"\n{'=' * 78}")
    print("ATF SCRIPT COVERAGE")
    print(f"{'=' * 78}")
    
    covered = 0
    for script in atf_scripts:
        has_mapping = any(script in m.atf_primitive for m in MAPPINGS)
        marker = "✓ mapped" if has_mapping else "○ no email equivalent"
        if has_mapping:
            covered += 1
        print(f"  {marker}: {script}")
    
    print(f"\n  {covered}/{len(atf_scripts)} scripts have email RFC equivalents")
    print(f"  Scripts without equivalents = genuinely novel ATF contributions")
    
    return True


if __name__ == "__main__":
    print_rosetta()
    verify_completeness()
