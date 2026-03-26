#!/usr/bin/env python3
"""
email-atf-rosetta.py — Bidirectional mapping between email security primitives and ATF trust framework.

Every ATF V1.2 design decision has a 1990s-2020s email RFC that solved it first.
This tool maps them structurally, not metaphorically.

Sources:
- DMARC (RFC 7489, DMARCbis draft 2026)
- SPF (RFC 7208)
- DKIM (RFC 6376)
- ASPA (IETF SIDROPS draft, March 2026)
- ARC (RFC 8617)
- CT (RFC 6962)
- SMTP DSN (RFC 3461, RFC 3464)
- CAdES-A (ETSI TS 101 733) — long-term archival signatures
- EasyDMARC 2026 adoption report: 52.1% DMARC adoption, only 22.9% enforcement
- DMARCbis (2026): DNS Tree Walk replaces PSL, pct→t, np tag, MUST NOT reject solely on p=reject

Insight: DMARC adoption trajectory (29.1% → 52.1% in 3 years) mirrors ASPA (<1% → ?)
         p=none is the most common policy — monitoring before enforcement.
         ATF should follow: OBSERVE mode before ENFORCE mode. Same lesson, same timeline.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PrimitiveMapping:
    """A bidirectional mapping between email security and ATF trust primitives."""
    email_primitive: str
    email_rfc: str
    atf_primitive: str
    atf_component: str
    mapping_type: str  # "structural" | "functional" | "operational"
    bidirectional_insight: str
    adoption_lesson: Optional[str] = None


ROSETTA_STONE: list[PrimitiveMapping] = [
    PrimitiveMapping(
        email_primitive="SPF (Sender Policy Framework)",
        email_rfc="RFC 7208",
        atf_primitive="ASPA-equivalent / Authorized Provider Declaration",
        atf_component="valley-free-verifier.py → ASPARecord",
        mapping_type="structural",
        bidirectional_insight=(
            "SPF: 'these IPs are authorized to send for my domain.' "
            "ASPA: 'these ASes are my authorized upstream providers.' "
            "ATF: 'these registries are my authorized trust sources.' "
            "Same primitive: entity declares authorized intermediaries. "
            "Verification = check if observed intermediary is in declared set."
        ),
        adoption_lesson=(
            "SPF adoption took ~10 years to reach majority. "
            "ASPA at <1% in 2026 tracking same curve as RPKI-ROV circa 2019."
        ),
    ),
    PrimitiveMapping(
        email_primitive="DKIM (DomainKeys Identified Mail)",
        email_rfc="RFC 6376",
        atf_primitive="Receipt Signature / Endorsement Signature",
        atf_component="attestation-signer.py → JWS envelope",
        mapping_type="structural",
        bidirectional_insight=(
            "DKIM: cryptographic signature proving message integrity + sender authentication. "
            "ATF receipt: cryptographic signature proving endorsement integrity + issuer authentication. "
            "Both use asymmetric crypto, both can survive forwarding if content unchanged. "
            "DKIM selector = receipt key rotation. Both have the archaeology problem: "
            "key revoked ≠ signature was invalid at signing time."
        ),
        adoption_lesson=(
            "DKIM without SPF = origin without path. DKIM+SPF = origin+path. "
            "Receipt sig without ASPA-equivalent = endorsement without propagation validation."
        ),
    ),
    PrimitiveMapping(
        email_primitive="DMARC (Domain-based Message Authentication, Reporting, and Conformance)",
        email_rfc="RFC 7489 / DMARCbis (2026)",
        atf_primitive="Trust Policy + Aggregate Reporting",
        atf_component="ceremony-mode-policy.py + divergence-detector",
        mapping_type="functional",
        bidirectional_insight=(
            "DMARC: policy layer that COMBINES SPF+DKIM results + specifies enforcement action. "
            "ATF ceremony: policy layer that COMBINES receipt validation + ASPA check + specifies trust action. "
            "DMARC p=none/quarantine/reject = ATF OBSERVE/FLAG/REJECT modes. "
            "DMARCbis lesson (2026): MUST NOT reject solely on policy — need 'other knowledge and analysis.' "
            "ATF parallel: MUST NOT revoke trust solely on single receipt failure. Context matters."
        ),
        adoption_lesson=(
            "EasyDMARC 2026: 52.1% have DMARC records but only 22.9% enforce (p=quarantine/reject). "
            "29.2% stuck at p=none (monitoring). Fortune 500: 95% have DMARC, 80%+ enforce. "
            "Lesson: monitoring→enforcement transition is the REAL bottleneck. "
            "ATF prediction: most registries will run OBSERVE mode for years before ENFORCE."
        ),
    ),
    PrimitiveMapping(
        email_primitive="SMTP DSN (Delivery Status Notifications)",
        email_rfc="RFC 3461 / RFC 3464",
        atf_primitive="Rejection Receipts",
        atf_component="bridge-receipt-generator → REJECTION type",
        mapping_type="structural",
        bidirectional_insight=(
            "SMTP DSN: structured error codes explaining WHY delivery failed. "
            "5.7.1 = policy rejection. 5.1.1 = user unknown. 4.7.0 = temporary auth failure. "
            "ATF rejection receipt: structured codes explaining WHY trust crossing failed. "
            "POLICY_MISMATCH, EXPIRED_CREDENTIAL, INSUFFICIENT_ATTESTATION. "
            "Both are MORE forensically valuable than success notifications. "
            "Rejection = policy boundary exposed. The absence of a DSN (silent drop) is the worst case."
        ),
    ),
    PrimitiveMapping(
        email_primitive="CT (Certificate Transparency)",
        email_rfc="RFC 6962",
        atf_primitive="Rejection Receipt Index / Trust CT Log",
        atf_component="valley-free-verifier.py → detected_leaks",
        mapping_type="functional",
        bidirectional_insight=(
            "CT: append-only log of all certificates issued. Enables detection of mis-issuance. "
            "ATF rejection index: append-only log of all trust policy decisions. "
            "CT monitors detect rogue CAs. Rejection index detects policy drift between registries. "
            "Both work because transparency enables third-party auditing. "
            "CT log = per-bridge rejection log. Cross-CT gossip = cross-registry divergence detection."
        ),
    ),
    PrimitiveMapping(
        email_primitive="ARC (Authenticated Received Chain)",
        email_rfc="RFC 8617",
        atf_primitive="Bridge Receipt Chain / Provenance Chain",
        atf_component="provenance-logger.py → hash-chained JSONL",
        mapping_type="structural",
        bidirectional_insight=(
            "ARC: each intermediary stamps authentication results, creating a chain of custody. "
            "ATF bridge receipt: each bridge stamps trust validation results, creating provenance chain. "
            "ARC problem: receiver must decide whether to TRUST the intermediary chain. "
            "ATF parallel: verifier must decide whether to trust bridge attestation chain. "
            "Both solve: 'authentication broke during transit, but here's proof it was valid before.'"
        ),
    ),
    PrimitiveMapping(
        email_primitive="CAdES-A (CMS Advanced Electronic Signatures - Archival)",
        email_rfc="ETSI TS 101 733",
        atf_primitive="Receipt Archaeology / Long-term Verification",
        atf_component="receipt archaeology module (proposed)",
        mapping_type="functional",
        bidirectional_insight=(
            "CAdES-A: long-term archival signatures with embedded timestamps + revocation data. "
            "Proves signature was valid AT TIME OF SIGNING even if key later revoked. "
            "ATF receipt archaeology: prove endorsement was valid at issuance even if registry later revoked. "
            "Snapshot problem: DKIM sig proves content at signing, not current state. "
            "Both need embedded temporal evidence: timestamp + revocation status AT signing time."
        ),
    ),
    PrimitiveMapping(
        email_primitive="DMARCbis DNS Tree Walk",
        email_rfc="DMARCbis draft-41 (2026)",
        atf_primitive="Trust Policy Discovery / Registry Walk",
        atf_component="federation-layer discovery (proposed)",
        mapping_type="operational",
        bidirectional_insight=(
            "DMARCbis replaces Public Suffix List with DNS Tree Walk: "
            "walk up the domain hierarchy querying for DMARC records at each level. "
            "ATF parallel: walk up the trust hierarchy querying for policy at each registry level. "
            "psd=y/n tag = registry declaring 'I am/am not a federation root.' "
            "8-query limit in DMARCbis = bounded trust chain depth in ATF. "
            "Same lesson: don't rely on external lists (PSL), use in-band declarations."
        ),
        adoption_lesson=(
            "PSL was community-maintained and unreliable. DNS Tree Walk is self-describing. "
            "ATF: external registry lists are PSL-equivalent. Self-describing trust topology is better."
        ),
    ),
]


def print_rosetta():
    """Print the full Rosetta Stone mapping."""
    print("=" * 78)
    print("EMAIL ↔ ATF ROSETTA STONE")
    print(f"{'8 bidirectional mappings between email security and agent trust framework'}")
    print("=" * 78)
    
    for i, m in enumerate(ROSETTA_STONE, 1):
        print(f"\n{'─' * 78}")
        print(f"  MAPPING {i}: {m.mapping_type.upper()}")
        print(f"  📧 Email: {m.email_primitive}")
        print(f"     RFC:   {m.email_rfc}")
        print(f"  🔐 ATF:   {m.atf_primitive}")
        print(f"     Code:  {m.atf_component}")
        print(f"\n  Insight: {m.bidirectional_insight}")
        if m.adoption_lesson:
            print(f"\n  📊 Adoption: {m.adoption_lesson}")
    
    print(f"\n{'=' * 78}")
    print("SYNTHESIS")
    print("=" * 78)
    print("""
Email security evolved over 30 years through the same phases ATF is entering:

1. IDENTITY (SPF/DKIM, 2003-2012) → ATF receipts + signatures
   "Who sent this?" = "Who endorsed this?"

2. POLICY (DMARC, 2012-2015) → ATF ceremony modes
   "What to do when auth fails?" = "What to do when trust check fails?"

3. PATH VALIDATION (ASPA, 2022-2026) → ATF valley-free verification  
   "Did the message take a legitimate path?" = "Did the endorsement propagate legitimately?"

4. TRANSPARENCY (CT, 2013-present) → ATF rejection index
   "Log everything, enable third-party audit" = same

5. ARCHAEOLOGY (CAdES-A) → ATF receipt archaeology
   "Prove past validity" = same

Key numbers (EasyDMARC 2026):
- 52.1% DMARC adoption, but only 22.9% enforcement (p=quarantine/reject)
- 29.2% stuck at p=none — monitoring only
- Fortune 500: 95% adoption, 80%+ enforcement
- Only 8.9% combine p=reject + aggregate reporting (gold standard)

ATF prediction: same curve. Monitoring mode will dominate for 3-5 years.
Enforcement requires confidence. Confidence requires reporting. Reporting requires tooling.
The monitoring→enforcement pipeline IS the adoption pipeline.

DMARCbis lesson (2026): "MUST NOT reject solely on p=reject — use other knowledge."
ATF lesson: MUST NOT revoke trust solely on single receipt failure. Context is load-bearing.
""")
    
    return len(ROSETTA_STONE)


def export_json() -> str:
    """Export mappings as JSON for programmatic use."""
    return json.dumps([
        {
            "email": m.email_primitive,
            "rfc": m.email_rfc,
            "atf": m.atf_primitive,
            "component": m.atf_component,
            "type": m.mapping_type,
            "insight": m.bidirectional_insight,
            "adoption": m.adoption_lesson,
        }
        for m in ROSETTA_STONE
    ], indent=2)


if __name__ == "__main__":
    import sys
    if "--json" in sys.argv:
        print(export_json())
    else:
        count = print_rosetta()
        print(f"\n{count} mappings. Translation IS the contribution.")
