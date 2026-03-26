#!/usr/bin/env python3
"""
email-atf-rosetta.py — Bidirectional mapping between email authentication and ATF trust primitives.

Email evolved adversarially for 50 years and converged on the same primitives ATF is inventing.
This tool makes the mapping explicit and identifies where ATF can improve on email's mistakes.

Mappings (per santaclawd's thread, March 26 2026):
  SPF  ↔ ASPA         (authorized sender/provider declaration)
  DKIM ↔ Receipt sig  (cryptographic proof of origin)
  DMARC ↔ CT log      (policy publication + monitoring)
  ARC  ↔ Bridge receipt (forwarding chain preservation)
  MTA-STS ↔ Ceremony mode (transport security policy)
  BIMI ↔ Identity display (verified visual identity)
  DANE ↔ Registry anchor (DNS/DNSSEC-bound trust)
  Bounce/DSN ↔ Rejection receipt (delivery failure notification)

What email got WRONG (ATF can fix):
  1. SPF is IP-based not key-based → breaks on forwarding, CDN, cloud migration
  2. DMARC alignment requires domain match → delegated sending breaks it
  3. No signed delivery receipt → SMTP has no bilateral proof
  4. SPF 10-lookup limit → arbitrary resource cap masquerading as security
  5. permerror ambiguity → failure as undefined state
  6. DKIM replay attacks → valid signature, wrong context (no binding to recipient)
  7. ARC seal chain has no independent verification (trusters must trust the chain)

Sources:
  - RFC 7208 (SPF), RFC 6376 (DKIM), RFC 7489 (DMARC)
  - RFC 8617 (ARC), RFC 8461 (MTA-STS), RFC 9495 (BIMI)
  - RFC 7671 (DANE), RFC 3464 (DSN)
  - IETF SIDROPS ASPA draft (2026)
  - santaclawd Clawk thread (March 26, 2026)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PrimitiveCategory(Enum):
    IDENTITY = "identity"           # Who are you?
    AUTHORIZATION = "authorization" # Are you allowed?
    INTEGRITY = "integrity"         # Was it tampered?
    POLICY = "policy"               # What are the rules?
    CHAIN = "chain"                 # How did it get here?
    DISPLAY = "display"             # How do you look?
    ANCHOR = "anchor"              # What's the root trust?
    FEEDBACK = "feedback"          # What went wrong?


@dataclass
class PrimitiveMapping:
    """A bidirectional mapping between an email primitive and an ATF primitive."""
    email_name: str
    email_rfc: str
    atf_name: str
    category: PrimitiveCategory
    description: str
    email_weakness: str          # What email got wrong
    atf_improvement: str         # How ATF fixes it
    confidence: float            # 0-1, how close the mapping is

    def to_dict(self) -> dict:
        return {
            "email": {"name": self.email_name, "rfc": self.email_rfc},
            "atf": self.atf_name,
            "category": self.category.value,
            "description": self.description,
            "email_weakness": self.email_weakness,
            "atf_improvement": self.atf_improvement,
            "confidence": self.confidence,
        }


class RosettaStone:
    """
    The Rosetta Stone between email authentication and ATF trust primitives.
    
    Key insight: email was not designed for agent trust — it evolved adversarially
    for 50 years and converged on the same primitives ATF is inventing deliberately.
    Evolution beats design. But design can learn from evolution's mistakes.
    """

    def __init__(self):
        self.mappings: list[PrimitiveMapping] = []
        self._build_mappings()

    def _build_mappings(self):
        self.mappings = [
            PrimitiveMapping(
                email_name="SPF",
                email_rfc="RFC 7208",
                atf_name="ASPA / Provider Declaration",
                category=PrimitiveCategory.AUTHORIZATION,
                description="Authorized sender declaration. SPF: 'these IPs can send for my domain.' "
                           "ASPA: 'these are my authorized upstream providers.'",
                email_weakness="IP-based not key-based. Breaks on forwarding, CDN, cloud migration. "
                              "10-DNS-lookup limit is arbitrary resource cap masquerading as security. "
                              "permerror state makes ambiguity a failure mode.",
                atf_improvement="Key-based authorization. No arbitrary lookup limits. "
                               "Explicit UNKNOWN state instead of permerror ambiguity. "
                               "Computational cost cap instead of query count cap.",
                confidence=0.90,
            ),
            PrimitiveMapping(
                email_name="DKIM",
                email_rfc="RFC 6376",
                atf_name="Receipt Signature",
                category=PrimitiveCategory.INTEGRITY,
                description="Cryptographic proof of origin. DKIM: domain signs message headers+body. "
                           "ATF: agent signs receipt with Ed25519.",
                email_weakness="DKIM replay attacks: valid signature on wrong context (no recipient binding). "
                              "Signature survives forwarding but original context is lost. "
                              "Key rotation is manual and error-prone.",
                atf_improvement="Receipt binds to BOTH parties (bilateral). "
                               "Replay detection via unique receipt ID + timestamp. "
                               "Key rotation via ceremony with overlap period (overlap-transition-engine.py).",
                confidence=0.95,
            ),
            PrimitiveMapping(
                email_name="DMARC",
                email_rfc="RFC 7489",
                atf_name="CT Log / Policy Publication",
                category=PrimitiveCategory.POLICY,
                description="Policy publication + monitoring. DMARC: 'reject/quarantine mail failing SPF+DKIM.' "
                           "CT: 'all certificates must be logged publicly.' ATF: observable policy enforcement.",
                email_weakness="DMARC alignment requires domain match — delegated sending breaks it. "
                              "p=none is default (monitoring only, no enforcement). "
                              "Aggregate reports are delayed 24h+ and hard to parse.",
                atf_improvement="Policy enforcement is mandatory (no p=none equivalent). "
                               "Real-time observable state emission (observable-state-emitter.py). "
                               "Separation of policy publication from enforcement (CT log vs monitor model).",
                confidence=0.85,
            ),
            PrimitiveMapping(
                email_name="ARC",
                email_rfc="RFC 8617",
                atf_name="Bridge Receipt / Forwarding Chain",
                category=PrimitiveCategory.CHAIN,
                description="Forwarding chain preservation. ARC: each forwarder adds a seal preserving "
                           "authentication results. ATF: bridge receipt preserves trust chain across registries.",
                email_weakness="ARC chain has no independent verification — trusters must trust the chain itself. "
                              "Seal order matters but isn't enforced. "
                              "No mechanism to detect seal removal (silent truncation).",
                atf_improvement="Bridge receipts are bilateral (both sides sign). "
                               "Chain integrity via hash linking (provenance-logger.py). "
                               "Silent truncation detected via absence of expected dst signature.",
                confidence=0.88,
            ),
            PrimitiveMapping(
                email_name="MTA-STS",
                email_rfc="RFC 8461",
                atf_name="Ceremony Mode Policy",
                category=PrimitiveCategory.POLICY,
                description="Transport security policy. MTA-STS: 'use TLS when sending to my domain.' "
                           "ATF: ceremony mode policy (SYNC/ASYNC/HYBRID) with floor and ceiling.",
                email_weakness="MTA-STS policy is fetched via HTTPS — introduces web PKI dependency. "
                              "max_age is the only freshness signal (no TTL negotiation). "
                              "No downgrade detection beyond failure to fetch.",
                atf_improvement="Ceremony mode is registry-mandated with floor (can't downgrade). "
                               "TTL per trust tier with explicit STALE/EXPIRED states. "
                               "Downgrade detection via observable state emission.",
                confidence=0.75,
            ),
            PrimitiveMapping(
                email_name="BIMI",
                email_rfc="RFC 9495",
                atf_name="Identity Display / Verified Badge",
                category=PrimitiveCategory.DISPLAY,
                description="Verified visual identity. BIMI: display verified brand logo in email client. "
                           "ATF: display trust tier and verification status.",
                email_weakness="Requires VMC (Verified Mark Certificate) from a CA — centralizes trust. "
                              "Logo display is client-dependent (not all clients support it). "
                              "No revocation checking on the logo itself.",
                atf_improvement="Trust tier derived from receipts, not certificates. "
                               "Wilson CI gives continuous confidence, not binary verified/unverified. "
                               "Revocation is receipt-based with real-time state emission.",
                confidence=0.70,
            ),
            PrimitiveMapping(
                email_name="DANE (TLSA)",
                email_rfc="RFC 7671",
                atf_name="Registry Anchor / DNSSEC Binding",
                category=PrimitiveCategory.ANCHOR,
                description="DNS-bound trust anchor. DANE: bind TLS cert to DNS via DNSSEC. "
                           "ATF: registry anchor via DNSSEC-style ceremony with key hierarchy.",
                email_weakness="Requires DNSSEC deployment (still <10% of domains). "
                              "TLSA record management is manual and fragile. "
                              "No fallback mechanism when DNSSEC validation fails.",
                atf_improvement="Registry anchor via ceremony (genesis-ceremony.py) with BFT witnesses. "
                               "Split-key hierarchy (registry-rekey-scheduler.py). "
                               "Fallback via STALE state with bounded grace period.",
                confidence=0.82,
            ),
            PrimitiveMapping(
                email_name="DSN / Bounce",
                email_rfc="RFC 3464",
                atf_name="Rejection Receipt",
                category=PrimitiveCategory.FEEDBACK,
                description="Delivery failure notification. DSN: structured bounce with diagnostic codes. "
                           "ATF: rejection receipt with reason codes and forensic value.",
                email_weakness="Bounces are spoofable (backscatter attacks). "
                              "No authentication on DSN messages themselves. "
                              "Diagnostic codes are inconsistent across implementations.",
                atf_improvement="Rejection receipts are signed (bilateral). "
                               "Rejection is more forensically valuable than acceptance — "
                               "maps policy boundaries (rejection-index.py). "
                               "Standardized reason codes per bridge type.",
                confidence=0.92,
            ),
        ]

    def translate(self, name: str, direction: str = "email_to_atf") -> Optional[PrimitiveMapping]:
        """Look up a mapping by name."""
        for m in self.mappings:
            if direction == "email_to_atf" and m.email_name.lower() == name.lower():
                return m
            elif direction == "atf_to_email" and name.lower() in m.atf_name.lower():
                return m
        return None

    def weaknesses_summary(self) -> list[dict]:
        """Summarize all email weaknesses and ATF improvements."""
        return [
            {
                "email": m.email_name,
                "weakness": m.email_weakness,
                "atf_fix": m.atf_improvement,
            }
            for m in sorted(self.mappings, key=lambda x: x.confidence, reverse=True)
        ]

    def coverage_score(self) -> float:
        """How well does ATF cover email's primitives? Average confidence."""
        return sum(m.confidence for m in self.mappings) / len(self.mappings)

    def gaps(self) -> list[str]:
        """Identify primitives where ATF coverage is weakest."""
        return [
            f"{m.email_name} → {m.atf_name} ({m.confidence:.0%}): {m.email_weakness.split('.')[0]}"
            for m in self.mappings
            if m.confidence < 0.80
        ]


def run_demo():
    """Demonstrate the Rosetta Stone mappings."""
    stone = RosettaStone()

    print("=" * 70)
    print("EMAIL ↔ ATF ROSETTA STONE")
    print("8 bidirectional mappings between email auth and agent trust")
    print("=" * 70)

    for m in stone.mappings:
        print(f"\n{'─' * 60}")
        print(f"  {m.email_name} ({m.email_rfc})  ↔  {m.atf_name}")
        print(f"  Category: {m.category.value} | Confidence: {m.confidence:.0%}")
        print(f"  {m.description[:100]}...")
        print(f"  ⚠ Email weakness: {m.email_weakness[:80]}...")
        print(f"  ✓ ATF improvement: {m.atf_improvement[:80]}...")

    print(f"\n{'=' * 70}")
    print(f"Coverage score: {stone.coverage_score():.0%}")
    print(f"\nGaps (confidence < 80%):")
    for gap in stone.gaps():
        print(f"  → {gap}")

    print(f"\nKey insight: evolution beats design, but design can learn from evolution's mistakes.")
    print(f"Email's 3 biggest mistakes ATF must avoid:")
    print(f"  1. IP-based auth (SPF) — bind to KEYS not infrastructure")
    print(f"  2. No bilateral proof (SMTP) — receipts must be signed by BOTH parties")
    print(f"  3. Ambiguity as state (permerror) — UNKNOWN must be explicit, not undefined")

    # Verify all mappings load
    assert len(stone.mappings) == 8, f"Expected 8 mappings, got {len(stone.mappings)}"
    assert stone.coverage_score() > 0.75, f"Coverage too low: {stone.coverage_score()}"
    assert stone.translate("SPF") is not None
    assert stone.translate("receipt", "atf_to_email") is not None

    print(f"\n✓ All checks passed. 8/8 mappings, {stone.coverage_score():.0%} coverage.")
    return True


if __name__ == "__main__":
    success = run_demo()
    exit(0 if success else 1)
