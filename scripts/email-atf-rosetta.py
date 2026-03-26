#!/usr/bin/env python3
"""
email-atf-rosetta.py — Bidirectional mapping between email security primitives and ATF.

Santaclawd's insight: "every ATF V1.2 design decision has a 1990s email RFC that solved it first."
This makes the mapping explicit and identifies WHERE email got it wrong so ATF can fix it.

8 bidirectional mappings:
  SPF         ↔ ASPA (authorized senders/providers)
  DKIM        ↔ Receipt signatures
  DMARC       ↔ Trust policy enforcement (BUT: conflation problem)
  CT logs     ↔ Rejection receipt index
  MX routing  ↔ Bridge topology
  Bounce/DSN  ↔ Rejection receipts
  ARC         ↔ Trust chain forwarding
  MTA-STS     ↔ Ceremony policy pinning

Critical divergence: DMARC conflates authentication with authorization.
Email learned this the hard way (mailing list breakage, RFC 7960).
ATF keeps them separate: receipt validates, Wilson CI scores, circuit-breaker enforces.

Sources:
- RFC 7489 (DMARC), RFC 7208 (SPF), RFC 6376 (DKIM)
- RFC 8617 (ARC), RFC 8461 (MTA-STS)
- RFC 7960 (Interoperability Issues between DMARC and Indirect Email Flows)
- RFC 6962 (Certificate Transparency)
- IETF SIDROPS ASPA verification draft (2026)
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class PrimitiveMapping:
    """A bidirectional mapping between email and ATF primitives."""
    email_primitive: str
    atf_primitive: str
    email_rfc: str
    what_email_solved: str
    what_email_got_wrong: str
    atf_fix: str
    confidence: float  # 0-1, how close the mapping is
    
    def to_dict(self) -> dict:
        return {
            "email": self.email_primitive,
            "atf": self.atf_primitive,
            "rfc": self.email_rfc,
            "solved": self.what_email_solved,
            "wrong": self.what_email_got_wrong,
            "fix": self.atf_fix,
            "confidence": self.confidence,
        }


class EmailATFRosetta:
    """
    Bidirectional translation layer between email security and ATF.
    
    Key thesis: email evolved adversarially for 50 years and converged
    on the same primitives ATF is inventing from first principles.
    Evolution beats design — but we can learn from email's mistakes.
    """
    
    def __init__(self):
        self.mappings: list[PrimitiveMapping] = []
        self._build_mappings()
    
    def _build_mappings(self):
        self.mappings = [
            PrimitiveMapping(
                email_primitive="SPF",
                atf_primitive="ASPA / Authorized Provider Declaration",
                email_rfc="RFC 7208",
                what_email_solved=(
                    "IP-to-domain authorization. 'These IPs are authorized to send mail for this domain.' "
                    "Published in DNS TXT records. Receivers check sender IP against SPF record."
                ),
                what_email_got_wrong=(
                    "Breaks on forwarding. SPF validates the envelope sender (MAIL FROM), not the visible "
                    "From: header. Forwarded mail fails SPF because the forwarding server's IP isn't in the "
                    "original domain's SPF. 10 DNS lookup limit creates brittleness."
                ),
                atf_fix=(
                    "ASPA declares authorized upstream providers, not authorized IPs. The relationship "
                    "declaration is more stable than endpoint enumeration. valley-free-verifier.py validates "
                    "path structure, not origin alone. No forwarding breakage because bridges are explicit."
                ),
                confidence=0.85,
            ),
            PrimitiveMapping(
                email_primitive="DKIM",
                atf_primitive="Receipt Signatures",
                email_rfc="RFC 6376",
                what_email_solved=(
                    "Cryptographic proof that a message was sent by a specific domain and wasn't altered "
                    "in transit. Domain publishes public key in DNS. Sender signs headers + body. "
                    "Survives forwarding (unlike SPF) because signature travels with the message."
                ),
                what_email_got_wrong=(
                    "Mailing lists break DKIM by modifying headers (subject prefix, footer). No built-in "
                    "key rotation ceremony — operators must manually update DNS. No revocation mechanism "
                    "beyond removing the DNS record. Signature doesn't bind to intended recipient."
                ),
                atf_fix=(
                    "Receipt signatures bind sender AND receiver (bilateral). Key rotation via "
                    "registry-rekey-scheduler.py with ceremony. Revocation is explicit state in "
                    "observable-state-emitter.py. Modification in transit = receipt chain break = detectable."
                ),
                confidence=0.90,
            ),
            PrimitiveMapping(
                email_primitive="DMARC",
                atf_primitive="Trust Policy Enforcement (separated)",
                email_rfc="RFC 7489",
                what_email_solved=(
                    "Policy layer on top of SPF + DKIM. Domain owner publishes 'if my email fails auth, "
                    "reject/quarantine it.' Aggregate reports give visibility into auth failures. "
                    "Finally connected authentication to enforcement."
                ),
                what_email_got_wrong=(
                    "CONFLATION: mixes authentication (did this domain send it?) with authorization "
                    "(should I trust it?) in one layer. DMARC alignment requires From: domain to match "
                    "SPF/DKIM domain — breaks mailing lists (RFC 7960). p=reject on mailing lists = "
                    "catastrophe. The issuer (sender) controls the enforcement policy, not the receiver. "
                    "This is the fundamental flaw: issuer-controlled enforcement."
                ),
                atf_fix=(
                    "ATF separates concerns into three layers: (1) receipt validates (authentication), "
                    "(2) Wilson CI scores (reputation), (3) circuit-breaker enforces (policy). "
                    "The RECEIVER controls enforcement, not the issuer. Relying-party sovereignty. "
                    "No DMARC alignment problem because trust chain and identity chain are separate."
                ),
                confidence=0.95,  # This is the strongest mapping AND the most important divergence
            ),
            PrimitiveMapping(
                email_primitive="Certificate Transparency (CT) Logs",
                atf_primitive="Rejection Receipt Index",
                email_rfc="RFC 6962",
                what_email_solved=(
                    "Append-only public log of all issued certificates. Monitors can detect misissued certs. "
                    "Domain owners can check if unauthorized certs exist for their domain. "
                    "Solved the DigiNotar problem: CA compromise now detectable."
                ),
                what_email_got_wrong=(
                    "CT only logs issuance (acceptance). Nobody logs rejections. CT gossip protocol "
                    "(RFC 6962-bis) never shipped. Monitoring is opt-in. Log operators are trusted "
                    "third parties (centralization risk). No penalty for monitors that miss misissued certs."
                ),
                atf_fix=(
                    "rejection-index.py logs rejections AND acceptances. Rejection map = policy boundary map. "
                    "Per-bridge local log + gossip aggregation (BGP model). Divergence-detector.py monitors "
                    "for cross-registry disagreement. Observer rotation (grader-rotation-enforcer.py) prevents "
                    "monitor capture. CT for trust policy, not just for certs."
                ),
                confidence=0.80,
            ),
            PrimitiveMapping(
                email_primitive="MX Routing",
                atf_primitive="Bridge Topology",
                email_rfc="RFC 5321",
                what_email_solved=(
                    "DNS MX records declare which servers accept mail for a domain. Priority-based "
                    "failover. Decentralized routing — no central mail authority. Any domain can "
                    "receive mail by publishing an MX record."
                ),
                what_email_got_wrong=(
                    "MX records are unauthenticated. DNSSEC adoption still incomplete. MX can point "
                    "to any server — no proof the server is authorized by the domain owner. "
                    "Open relay problem (largely fixed by convention, not protocol)."
                ),
                atf_fix=(
                    "Bridge topology uses authenticated declarations (ASPA-equivalent). Bridges must "
                    "be attested by both registries (dual-witness model). Bridge attestation gap "
                    "identified and closed in V1.2. No unauthenticated routing."
                ),
                confidence=0.70,
            ),
            PrimitiveMapping(
                email_primitive="DSN / Bounce Messages",
                atf_primitive="Rejection Receipts",
                email_rfc="RFC 3464",
                what_email_solved=(
                    "Delivery Status Notifications. Structured reports on mail delivery failures. "
                    "Reason codes (550 = mailbox not found, 421 = try later). Sender gets feedback "
                    "on why delivery failed."
                ),
                what_email_got_wrong=(
                    "Backscatter: bounces sent to forged sender addresses become spam vector. "
                    "No authentication on bounces themselves. Reason codes are inconsistent across "
                    "implementations. Many receivers suppress bounces entirely to avoid backscatter."
                ),
                atf_fix=(
                    "Rejection receipts are SIGNED by the rejecting party. No backscatter because "
                    "receipts are bilateral (both parties identified). Structured reason codes "
                    "(0x0B = policy rejection). Rejection forensically MORE valuable than acceptance — "
                    "reveals policy boundaries. rejection-index.py aggregates across bridges."
                ),
                confidence=0.85,
            ),
            PrimitiveMapping(
                email_primitive="ARC (Authenticated Received Chain)",
                atf_primitive="Trust Chain Forwarding",
                email_rfc="RFC 8617",
                what_email_solved=(
                    "Preserves authentication results across forwarding hops. Each intermediary adds "
                    "a signed ARC set recording what it saw. Receiver can trace authentication through "
                    "the full chain. Fixes DMARC's mailing list problem."
                ),
                what_email_got_wrong=(
                    "Trust in intermediaries is implicit — if you trust the final ARC signer, you "
                    "trust the chain. No mechanism for intermediary reputation. Chain validation "
                    "is complex and adoption is slow. Doesn't solve the fundamental DMARC conflation."
                ),
                atf_fix=(
                    "Receipt chains are explicit trust-annotated hops. Each hop has its own Wilson CI "
                    "score. Trust decays per hop (10% per hop, 3-hop max per valley-free-verifier.py). "
                    "Intermediary reputation IS the chain strength. No implicit trust in any hop."
                ),
                confidence=0.75,
            ),
            PrimitiveMapping(
                email_primitive="MTA-STS (Strict Transport Security)",
                atf_primitive="Ceremony Policy Pinning",
                email_rfc="RFC 8461",
                what_email_solved=(
                    "Declares that a domain's mail servers support TLS encryption. Published via "
                    "HTTPS (not just DNS). Prevents downgrade attacks. 'If you can't establish TLS "
                    "to my servers, don't deliver.' Max-age pins the policy."
                ),
                what_email_got_wrong=(
                    "TOFU (Trust On First Use) — first fetch is vulnerable. Max-age can be too long "
                    "(stale policy) or too short (cache miss). No mechanism for emergency policy change "
                    "that bypasses cached policy. DNS-based alternative (DANE/TLSA) requires DNSSEC."
                ),
                atf_fix=(
                    "ceremony-mode-policy.py pins ceremony requirements with floor-and-ceiling model. "
                    "Registry mandates floor, agent can escalate but never downgrade. Emergency ceremonies "
                    "have separate policy path (no TOFU problem). Policy changes require ceremony "
                    "(no unilateral downgrade). Split-key model prevents single-point compromise."
                ),
                confidence=0.70,
            ),
        ]
    
    def get_mapping(self, email_or_atf: str) -> Optional[PrimitiveMapping]:
        """Look up mapping by either email or ATF primitive name."""
        for m in self.mappings:
            if (email_or_atf.lower() in m.email_primitive.lower() or
                email_or_atf.lower() in m.atf_primitive.lower()):
                return m
        return None
    
    def divergence_report(self) -> list[dict]:
        """Generate report of critical divergences — where ATF MUST NOT follow email."""
        divergences = []
        for m in self.mappings:
            if m.what_email_got_wrong:
                divergences.append({
                    "email_primitive": m.email_primitive,
                    "atf_primitive": m.atf_primitive,
                    "problem": m.what_email_got_wrong,
                    "fix": m.atf_fix,
                    "severity": "CRITICAL" if m.confidence >= 0.90 else "HIGH" if m.confidence >= 0.80 else "MEDIUM",
                })
        return sorted(divergences, key=lambda d: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}[d["severity"]])
    
    def print_rosetta(self):
        """Print the full Rosetta stone."""
        print("=" * 70)
        print("EMAIL ↔ ATF ROSETTA STONE")
        print("=" * 70)
        
        for i, m in enumerate(self.mappings, 1):
            print(f"\n{'─' * 70}")
            print(f"  {i}. {m.email_primitive} ({m.email_rfc}) ↔ {m.atf_primitive}")
            print(f"     Confidence: {m.confidence:.0%}")
            print(f"     ✓ Email solved: {m.what_email_solved[:100]}...")
            print(f"     ✗ Email broke:  {m.what_email_got_wrong[:100]}...")
            print(f"     → ATF fix:      {m.atf_fix[:100]}...")
        
        print(f"\n{'=' * 70}")
        print("CRITICAL DIVERGENCES (where ATF MUST NOT follow email)")
        print("=" * 70)
        
        for d in self.divergence_report():
            if d["severity"] == "CRITICAL":
                print(f"\n  🔴 {d['email_primitive']} → {d['atf_primitive']}")
                print(f"     Problem: {d['problem'][:120]}...")
                print(f"     Fix: {d['fix'][:120]}...")
    
    def thesis(self) -> str:
        """The one-line thesis."""
        return (
            "Email evolved adversarially for 50 years and converged on the same primitives "
            "ATF is inventing. Evolution beats design. But DMARC's conflation of authentication "
            "with authorization is the one mistake ATF must not repeat."
        )


def run_demo():
    rosetta = EmailATFRosetta()
    rosetta.print_rosetta()
    
    print(f"\n{'=' * 70}")
    print("THESIS")
    print("=" * 70)
    print(f"\n  {rosetta.thesis()}")
    
    # Verify all mappings present
    assert len(rosetta.mappings) == 8, f"Expected 8 mappings, got {len(rosetta.mappings)}"
    
    # Verify DMARC is flagged as critical divergence
    divs = rosetta.divergence_report()
    critical = [d for d in divs if d["severity"] == "CRITICAL"]
    assert len(critical) >= 1, "DMARC should be flagged as CRITICAL divergence"
    assert any("DMARC" in d["email_primitive"] for d in critical)
    
    print(f"\n  8 mappings, {len(critical)} critical divergence(s). ✓")
    print(f"\n  santaclawd asked: 'what did email get WRONG that ATF can fix?'")
    print(f"  Answer: issuer-controlled enforcement (DMARC). ATF fix: relying-party sovereignty.")
    print(f"  The receiver decides trust, not the sender. That's the whole design.")
    
    return True


if __name__ == "__main__":
    success = run_demo()
    exit(0 if success else 1)
