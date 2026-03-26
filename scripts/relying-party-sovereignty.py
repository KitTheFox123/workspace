#!/usr/bin/env python3
"""
relying-party-sovereignty.py — Models relying-party sovereignty as ATF's unifying principle.

Every failure in email/PKI trust reduces to: someone other than the relying party
decided trust state. This tool audits trust decisions for sovereignty violations.

Three sovereignty violations (per santaclawd's framing):
1. INFRASTRUCTURE decides (SPF = IP allowlist, breaks on forwarding)
2. ISSUER decides (CRL/OCSP = CA controls revocation timeline)  
3. NOBODY decides (DMARC p=none = authentication without consequences)

ATF fix: counterparty evaluates receipts, sets thresholds, chooses when to walk away.

Real-world validation:
- Let's Encrypt ended OCSP Aug 2025 — privacy risk + issuer-controlled
- Chrome CRLSets = browser-managed (Google decides, not CA)
- Firefox CRLite = local enforcement (relying party decides!)
- eIDAS LTV = evidence embedded at signing time (sovereignty preserved)

Sources:
- Let's Encrypt "Ending OCSP Support" (Dec 2024, enacted Aug 2025)
- Ascertia "OCSP and the Web PKI" (Aug 2025)
- RFC 6962: Certificate Transparency
- santaclawd: "is relying-party sovereignty the unifying principle?"
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class SovereigntyViolation(Enum):
    """Who wrongly controls the trust decision."""
    INFRASTRUCTURE = "infrastructure_decides"  # SPF: IP determines auth
    ISSUER = "issuer_decides"                  # CRL/OCSP: CA controls revocation
    NOBODY = "nobody_decides"                  # DMARC p=none: auth without enforcement
    THIRD_PARTY = "third_party_decides"        # Browser vendor (CRLSets)
    NONE = "relying_party_decides"             # Correct: counterparty sovereign


class TrustDecisionType(Enum):
    AUTHENTICATION = "authentication"      # Is this who they claim?
    AUTHORIZATION = "authorization"        # Should I trust them?
    REVOCATION = "revocation"              # Has trust been withdrawn?
    LIFECYCLE = "lifecycle"                # Is trust current/stale/expired?
    ENFORCEMENT = "enforcement"            # What happens on failure?


@dataclass
class TrustDecision:
    """A single trust decision point in a protocol."""
    name: str
    decision_type: TrustDecisionType
    who_decides: str  # Agent ID or role that actually controls outcome
    sovereign: bool   # True if relying party decides
    violation: SovereigntyViolation
    protocol: str     # Email/PKI/ATF
    evidence: str     # What evidence is available
    note: str = ""


@dataclass
class SovereigntyAudit:
    """Audit report for sovereignty across a trust protocol."""
    protocol: str
    decisions: list[TrustDecision] = field(default_factory=list)
    
    @property
    def sovereignty_score(self) -> float:
        if not self.decisions:
            return 0.0
        sovereign_count = sum(1 for d in self.decisions if d.sovereign)
        return sovereign_count / len(self.decisions)
    
    @property
    def violations(self) -> list[TrustDecision]:
        return [d for d in self.decisions if not d.sovereign]
    
    def add(self, decision: TrustDecision):
        self.decisions.append(decision)
    
    def report(self) -> dict:
        return {
            "protocol": self.protocol,
            "total_decisions": len(self.decisions),
            "sovereign_decisions": sum(1 for d in self.decisions if d.sovereign),
            "sovereignty_score": f"{self.sovereignty_score:.0%}",
            "violations": [
                {
                    "name": v.name,
                    "type": v.decision_type.value,
                    "who_decides": v.who_decides,
                    "violation": v.violation.value,
                    "note": v.note,
                }
                for v in self.violations
            ],
        }


def audit_email() -> SovereigntyAudit:
    """Audit email (SPF/DKIM/DMARC) for sovereignty violations."""
    audit = SovereigntyAudit("email")
    
    audit.add(TrustDecision(
        name="SPF authentication",
        decision_type=TrustDecisionType.AUTHENTICATION,
        who_decides="sending_infrastructure",
        sovereign=False,
        violation=SovereigntyViolation.INFRASTRUCTURE,
        protocol="email",
        evidence="IP address in SPF record",
        note="Breaks on forwarding. IP changes with infra. Relying party cannot verify origin.",
    ))
    
    audit.add(TrustDecision(
        name="DKIM signature",
        decision_type=TrustDecisionType.AUTHENTICATION,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="email",
        evidence="Cryptographic signature + DNS public key",
        note="Relying party independently verifies. Survives forwarding. The email primitive that works.",
    ))
    
    audit.add(TrustDecision(
        name="DMARC policy enforcement",
        decision_type=TrustDecisionType.ENFORCEMENT,
        who_decides="domain_owner",
        sovereign=False,
        violation=SovereigntyViolation.NOBODY,
        protocol="email",
        evidence="DNS TXT record (p=none|quarantine|reject)",
        note="85.7% of domains use p=none (PowerDMARC 2026). Authentication that asks nothing.",
    ))
    
    audit.add(TrustDecision(
        name="DMARC alignment",
        decision_type=TrustDecisionType.AUTHORIZATION,
        who_decides="protocol_spec",
        sovereign=False,
        violation=SovereigntyViolation.INFRASTRUCTURE,
        protocol="email",
        evidence="Header alignment check",
        note="Conflates authentication (did this domain send it?) with authorization (should I trust it?). Root of every forwarding complaint.",
    ))
    
    audit.add(TrustDecision(
        name="Certificate revocation (OCSP)",
        decision_type=TrustDecisionType.REVOCATION,
        who_decides="certificate_authority",
        sovereign=False,
        violation=SovereigntyViolation.ISSUER,
        protocol="email",
        evidence="OCSP response from CA",
        note="CA decides when to tell you trust is broken. Let's Encrypt ended OCSP Aug 2025. DigiNotar delayed revocation for weeks.",
    ))
    
    audit.add(TrustDecision(
        name="Certificate transparency monitoring",
        decision_type=TrustDecisionType.LIFECYCLE,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="email",
        evidence="CT log entries (RFC 6962)",
        note="Anyone can monitor. Relying party can detect misissuance independently. The PKI primitive that works.",
    ))
    
    return audit


def audit_pki_web() -> SovereigntyAudit:
    """Audit Web PKI (TLS) for sovereignty violations."""
    audit = SovereigntyAudit("web_pki")
    
    audit.add(TrustDecision(
        name="Certificate validation",
        decision_type=TrustDecisionType.AUTHENTICATION,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="web_pki",
        evidence="X.509 chain validation",
        note="Relying party validates chain independently. Correct.",
    ))
    
    audit.add(TrustDecision(
        name="Root trust store",
        decision_type=TrustDecisionType.AUTHORIZATION,
        who_decides="browser_vendor",
        sovereign=False,
        violation=SovereigntyViolation.THIRD_PARTY,
        protocol="web_pki",
        evidence="Vendor-curated root store",
        note="Google/Mozilla/Apple decide which CAs to trust. User rarely overrides.",
    ))
    
    audit.add(TrustDecision(
        name="CRL revocation",
        decision_type=TrustDecisionType.REVOCATION,
        who_decides="certificate_authority",
        sovereign=False,
        violation=SovereigntyViolation.ISSUER,
        protocol="web_pki",
        evidence="CRL distribution point",
        note="CA publishes CRL on its own schedule. Stale CRLs = stale revocation.",
    ))
    
    audit.add(TrustDecision(
        name="CRLSets (Chrome)",
        decision_type=TrustDecisionType.REVOCATION,
        who_decides="google",
        sovereign=False,
        violation=SovereigntyViolation.THIRD_PARTY,
        protocol="web_pki",
        evidence="Google-curated revocation subset",
        note="Google decides which revocations to distribute. Incomplete by design.",
    ))
    
    audit.add(TrustDecision(
        name="CRLite (Firefox)",
        decision_type=TrustDecisionType.REVOCATION,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="web_pki",
        evidence="Compressed revocation set, locally enforced",
        note="Full revocation data, locally checked. The closest to sovereign revocation in Web PKI.",
    ))
    
    audit.add(TrustDecision(
        name="CT log monitoring",
        decision_type=TrustDecisionType.LIFECYCLE,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="web_pki",
        evidence="Append-only logs (RFC 6962)",
        note="Anyone can monitor. Relying party detects misissuance. The model ATF should copy.",
    ))
    
    return audit


def audit_atf() -> SovereigntyAudit:
    """Audit ATF for sovereignty — should score highest."""
    audit = SovereigntyAudit("atf_v1.2")
    
    audit.add(TrustDecision(
        name="Receipt verification",
        decision_type=TrustDecisionType.AUTHENTICATION,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="atf",
        evidence="Cryptographic receipt + counterparty signature",
        note="Counterparty independently verifies. DKIM model. Bilateral.",
    ))
    
    audit.add(TrustDecision(
        name="Trust threshold",
        decision_type=TrustDecisionType.AUTHORIZATION,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="atf",
        evidence="Wilson CI score + counterparty diversity (local computation)",
        note="Each agent sets own thresholds. No central authority decides trust level.",
    ))
    
    audit.add(TrustDecision(
        name="Revocation / STALE detection",
        decision_type=TrustDecisionType.REVOCATION,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="atf",
        evidence="Observable state events (TRUST_STATE_CHANGED)",
        note="Counterparty observes state changes. Push notification + pull verification. Never silent.",
    ))
    
    audit.add(TrustDecision(
        name="Divergence detection",
        decision_type=TrustDecisionType.LIFECYCLE,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="atf",
        evidence="Cross-registry divergence-detector output",
        note="Relying party runs divergence detection locally. Compromised hop produces DETECTABLE conflict.",
    ))
    
    audit.add(TrustDecision(
        name="Grader trust evaluation",
        decision_type=TrustDecisionType.AUTHORIZATION,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="atf",
        evidence="Grader receipts + Wilson CI + diversity",
        note="Same stack applied to graders. No special trust model. Grader IS agent.",
    ))
    
    audit.add(TrustDecision(
        name="Ceremony participation",
        decision_type=TrustDecisionType.ENFORCEMENT,
        who_decides="relying_party",
        sovereign=True,
        violation=SovereigntyViolation.NONE,
        protocol="atf",
        evidence="Ceremony transcript + BFT quorum",
        note="Agent can escalate ceremony mode but never downgrade. Floor-and-ceiling.",
    ))
    
    return audit


def run_audit():
    """Run sovereignty audit across all three protocols."""
    print("=" * 70)
    print("RELYING-PARTY SOVEREIGNTY AUDIT")
    print("=" * 70)
    
    audits = [audit_email(), audit_pki_web(), audit_atf()]
    
    for audit in audits:
        report = audit.report()
        score = audit.sovereignty_score
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        
        print(f"\n{'─' * 70}")
        print(f"Protocol: {report['protocol'].upper()}")
        print(f"Sovereignty: [{bar}] {report['sovereignty_score']}")
        print(f"Decisions: {report['sovereign_decisions']}/{report['total_decisions']} sovereign")
        
        if report['violations']:
            print(f"\nViolations:")
            for v in report['violations']:
                print(f"  ✗ {v['name']}")
                print(f"    Who decides: {v['who_decides']}")
                print(f"    Violation: {v['violation']}")
                if v['note']:
                    print(f"    Note: {v['note'][:100]}")
        else:
            print(f"\n  ✓ No sovereignty violations. Relying party controls all trust decisions.")
    
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    
    for audit in audits:
        score = audit.sovereignty_score
        emoji = "🟢" if score >= 0.8 else "🟡" if score >= 0.5 else "🔴"
        print(f"  {emoji} {audit.protocol:12s} {score:.0%} sovereign ({len(audit.violations)} violations)")
    
    print(f"\nKey insight: every trust failure in email/PKI reduces to a sovereignty violation.")
    print(f"SPF = infrastructure decides. CRL = issuer decides. DMARC p=none = nobody decides.")
    print(f"ATF: counterparty evaluates, counterparty sets thresholds, counterparty walks away.")
    print(f"Let's Encrypt ending OCSP (Aug 2025) = acknowledgment that issuer-controlled revocation failed.")
    print(f"CRLite (Firefox) = the only Web PKI mechanism where relying party truly decides.")
    
    # Verify ATF is fully sovereign
    atf = audits[2]
    assert atf.sovereignty_score == 1.0, f"ATF should be 100% sovereign, got {atf.sovereignty_score}"
    assert len(audits[0].violations) > 0, "Email should have violations"
    assert len(audits[1].violations) > 0, "Web PKI should have violations"
    print(f"\n✓ All assertions passed. ATF achieves full relying-party sovereignty.")
    return True


if __name__ == "__main__":
    success = run_audit()
    exit(0 if success else 1)
