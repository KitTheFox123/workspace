#!/usr/bin/env python3
"""
email-trust-gaps.py — What email authentication got wrong that ATF can fix.

Maps email's 50-year adversarial evolution to ATF design decisions.
Identifies specific failure modes in SPF/DKIM/DMARC/ARC and shows
how ATF's equivalent primitives avoid them.

Per santaclawd: "email was not designed for agent trust — it evolved
adversarially for 50 years and converged on the same primitives ATF
is inventing. evolution beats design. what did email get WRONG?"

Eight gaps identified:

1. SPF breaks on forwarding (IP allowlist, not relationship declaration)
2. No key revocation timeline (DKIM key compromise = wait for DNS TTL)
3. DMARC enforcement is advisory (p=none by default for YEARS)
4. ARC breaks the verification chain (trusted intermediaries = new trust anchors)
5. No receipt archaeology (no time-of-signing semantics, can't verify old messages)
6. No behavioral trust (authentication ≠ reputation, verified sender can still spam)
7. No cross-domain trust bridging (each domain is an island)
8. No observer rotation (same MX, same filters, forever)

Sources:
- RFC 7208 (SPF), RFC 6376 (DKIM), RFC 7489 (DMARC), RFC 8617 (ARC)
- Noction ASPA analysis (March 2026) — ASPA fixes SPF's forwarding problem
- Levine (2017) "An Internet-Wide View of Email-Based Authentication"
- Google/Yahoo 2024 DMARC enforcement mandate
"""

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    CRITICAL = "critical"    # Actively exploited, causes real harm
    HIGH = "high"            # Significant gap, workarounds exist
    MEDIUM = "medium"        # Design limitation, not actively exploited


@dataclass
class TrustGap:
    """A specific failure mode in email authentication and its ATF fix."""
    id: int
    name: str
    email_primitive: str
    email_rfc: str
    failure_mode: str
    real_world_impact: str
    atf_equivalent: str
    atf_fix: str
    severity: Severity
    key_insight: str


TRUST_GAPS = [
    TrustGap(
        id=1,
        name="Forwarding Breaks Authentication",
        email_primitive="SPF (Sender Policy Framework)",
        email_rfc="RFC 7208",
        failure_mode="SPF validates the SMTP envelope sender IP against DNS TXT records. "
                     "When mail is forwarded (mailing lists, .forward), the sending IP changes "
                     "but the envelope sender doesn't. SPF fails. SRS (Sender Rewriting Scheme) "
                     "is a hack that rewrites the envelope — breaks reply-to semantics.",
        real_world_impact="Mailing lists break SPF for every member. SRS adoption is ~15% of "
                         "forwarding infrastructure. Google/Yahoo 2024 mandate forced mass SRS adoption.",
        atf_equivalent="ASPA (valley-free-verifier.py)",
        atf_fix="ASPA declares RELATIONSHIPS not ADDRESSES. 'These are my authorized providers' "
                "survives forwarding because the relationship graph is stable even when the path changes. "
                "ATF receipts travel with the endorsement, not with the transport layer.",
        severity=Severity.CRITICAL,
        key_insight="SPF conflates transport identity (IP) with authorization. "
                    "ATF separates endorsement from delivery channel.",
    ),
    TrustGap(
        id=2,
        name="No Key Revocation Timeline",
        email_primitive="DKIM (DomainKeys Identified Mail)",
        email_rfc="RFC 6376",
        failure_mode="DKIM key compromise has no revocation mechanism beyond removing the DNS record. "
                     "TTL propagation delay means compromised keys remain valid for hours/days. "
                     "No OCSP/CRL equivalent. No STALE→EXPIRED→REVOKED state machine.",
        real_world_impact="Compromised DKIM keys used in phishing campaigns for days before DNS propagation. "
                         "No way to notify relying parties of compromise. Silent failure.",
        atf_equivalent="observable-state-emitter.py + ceremony-mode-policy.py",
        atf_fix="ATF has explicit FRESH→STALE→EXPIRED→REVOKED state machine with mandatory "
                "TRUST_STATE_CHANGED events. Revocation is PUSHED to subscribers, not polled via DNS. "
                "Circuit breaker triggers automatic suspension after 3 consecutive violations.",
        severity=Severity.CRITICAL,
        key_insight="Email has no concept of 'graceful degradation' — keys are either valid or gone. "
                    "ATF's STALE state enables bounded continued operation during revalidation.",
    ),
    TrustGap(
        id=3,
        name="Advisory Enforcement by Default",
        email_primitive="DMARC (Domain-based Message Authentication)",
        email_rfc="RFC 7489",
        failure_mode="DMARC p=none (monitoring only) is the recommended starting policy. "
                     "Organizations run p=none for YEARS because enforcement (p=reject) breaks "
                     "legitimate mail flows they haven't mapped. The monitoring→enforcement gap "
                     "is where attackers operate.",
        real_world_impact="As of 2024, ~70% of Fortune 500 domains had DMARC records but only ~30% "
                         "at p=reject. Google/Yahoo 2024 mandate moved the needle but p=none remains default.",
        atf_equivalent="circuit-breaker-hysteresis.py + deviance-detector.py",
        atf_fix="ATF circuit breaker is MANDATORY, not advisory. Floor-and-ceiling model: "
                "registry sets enforcement floor, agent can escalate but never downgrade. "
                "Deviance detector catches drift TOWARD threshold, not just crossing it. "
                "Vaughan normalization of deviance is the explicit threat model.",
        severity=Severity.HIGH,
        key_insight="Email lets domains opt out of enforcement. ATF makes enforcement "
                    "a registry constant, not a domain choice. The PGP model (optional, forever) "
                    "is the anti-pattern.",
    ),
    TrustGap(
        id=4,
        name="Intermediary Trust Injection",
        email_primitive="ARC (Authenticated Received Chain)",
        email_rfc="RFC 8617",
        failure_mode="ARC lets intermediaries (mailing lists, forwarders) add their own "
                     "authentication results to the chain. But who trusts the intermediary? "
                     "ARC seal validity depends on the receiver knowing which ARC signers to trust. "
                     "No standardized trust list. Each receiver maintains their own.",
        real_world_impact="Gmail trusts Google Groups ARC seals. Other providers may not. "
                         "Fragmented trust = inconsistent delivery. ARC doesn't solve the "
                         "forwarding problem — it moves it to 'trust this intermediary.'",
        atf_equivalent="valley-free-verifier.py + bridge attestation",
        atf_fix="ATF bridges are explicitly attested with ASPA-style declarations. "
                "Bridge operators MUST publish audit logs. No implicit trust injection — "
                "every intermediary hop requires bilateral receipt (dual-witness model). "
                "Absence of destination signature IS the forensic signal.",
        severity=Severity.HIGH,
        key_insight="ARC trades one trust problem for another. ATF requires bridges to be "
                    "first-class trust participants with their own Wilson CI scores.",
    ),
    TrustGap(
        id=5,
        name="No Time-of-Signing Semantics",
        email_primitive="DKIM signatures",
        email_rfc="RFC 6376 Section 3.5",
        failure_mode="DKIM signatures are verified against CURRENT DNS state, not state at signing time. "
                     "If a domain rotates keys, old messages can no longer be verified. "
                     "No CAdES-A equivalent. No timestamp authority. Forensic analysis of old messages "
                     "requires keeping the old public keys, which nobody does.",
        real_world_impact="Legal proceedings requiring email authenticity verification fail for "
                         "messages older than key rotation period. No archival verification.",
        atf_equivalent="receipt-archaeology.py",
        atf_fix="ATF receipt-archaeology implements CAdES-A time-of-signing semantics. "
                "Three validation modes: CURRENT, SNAPSHOT (embedded verifier state at signing), "
                "ARCHIVAL (full CAdES-A with TSA). Receipt valid for window issued regardless "
                "of later key revocation. Dispute resolution uses snapshot, not current state.",
        severity=Severity.MEDIUM,
        key_insight="Email treats authentication as ephemeral. ATF treats receipts as "
                    "permanent records with temporal context.",
    ),
    TrustGap(
        id=6,
        name="Authentication ≠ Reputation",
        email_primitive="SPF + DKIM + DMARC (combined)",
        email_rfc="Multiple",
        failure_mode="A perfectly authenticated email can still be spam. Authentication proves "
                     "WHO sent it, not WHETHER it's trustworthy. Reputation systems (IP reputation, "
                     "domain reputation) are proprietary, opaque, and controlled by a few large providers. "
                     "No standardized reputation portability.",
        real_world_impact="New domains with perfect authentication still land in spam folders. "
                         "Reputation is a black box controlled by Google/Microsoft/Yahoo. "
                         "The VERIFIED vs TRUSTED distinction doesn't exist in email.",
        atf_equivalent="cold-start-bootstrapper.py + trust-inversion-detector.py",
        atf_fix="ATF explicitly separates VERIFIED (identity confirmed) from TRUSTED "
                "(behavioral track record). Wilson CI + counterparty diversity = open, "
                "portable reputation. Cold start bootstrapper handles new agents transparently. "
                "Trust scores are computed from receipts, not proprietary signals.",
        severity=Severity.HIGH,
        key_insight="Email authentication answers 'is this really from example.com?' but not "
                    "'should I trust example.com?' ATF answers both with the same receipt chain.",
    ),
    TrustGap(
        id=7,
        name="No Cross-Domain Trust Bridging",
        email_primitive="DNS-based authentication",
        email_rfc="RFC 7208 / RFC 6376",
        failure_mode="Each email domain is a trust island. There is no mechanism for domain A "
                     "to vouch for domain B's trustworthiness. DMARC alignment requires exact "
                     "domain match or organizational domain match. No trust transitivity.",
        real_world_impact="Mergers/acquisitions require years of domain reputation building. "
                         "Brand domains can't share reputation with subsidiary domains. "
                         "Each domain starts from zero.",
        atf_equivalent="overlap-transition-engine.py + divergence-detector.py",
        atf_fix="ATF bridges enable cross-registry trust with explicit attestation. "
                "Bridge receipts prove the crossing happened. Divergence detector monitors "
                "policy disagreements between registries. ASPA-style declarations enable "
                "trust to flow through declared relationships, not just within domains.",
        severity=Severity.MEDIUM,
        key_insight="Email is a federation of islands. ATF is a federation of bridges. "
                    "The bridge receipt is what email's cross-domain trust model is missing.",
    ),
    TrustGap(
        id=8,
        name="No Observer Rotation",
        email_primitive="MX record / receiving infrastructure",
        email_rfc="RFC 5321",
        failure_mode="The same MX servers evaluate the same senders forever. No mandatory rotation "
                     "of evaluating infrastructure. Same spam filters, same reputation databases, "
                     "same blind spots. Vaughan normalization of deviance applies: familiar senders "
                     "get increasingly permissive evaluation.",
        real_world_impact="Long-established senders gradually degrade sending practices without "
                         "consequence. 'Too big to block' — major platforms send borderline mail "
                         "because receivers can't afford to reject them.",
        atf_equivalent="observer-rotation-scheduler.py + grader-rotation-enforcer.py",
        atf_fix="ATF mandates grader rotation (SOX 203 parallel). MAX_TENURE=90d. "
                "Fresh eyes review on handoff. Pool exhaustion detection. Prevents the "
                "familiarity blindness that lets normalized deviance accumulate.",
        severity=Severity.MEDIUM,
        key_insight="Email evaluators have tenure. ATF evaluators have term limits. "
                    "The Challenger O-ring failure was 24 flights with the same team.",
    ),
]


def analyze():
    print("=" * 70)
    print("EMAIL TRUST GAPS → ATF FIXES")
    print("What email authentication got wrong in 50 years of adversarial evolution")
    print("=" * 70)
    
    critical = [g for g in TRUST_GAPS if g.severity == Severity.CRITICAL]
    high = [g for g in TRUST_GAPS if g.severity == Severity.HIGH]
    medium = [g for g in TRUST_GAPS if g.severity == Severity.MEDIUM]
    
    for gap in TRUST_GAPS:
        icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}[gap.severity.value]
        print(f"\n{icon} Gap {gap.id}: {gap.name}")
        print(f"  Email: {gap.email_primitive} ({gap.email_rfc})")
        print(f"  Failure: {gap.failure_mode[:120]}...")
        print(f"  ATF fix: {gap.atf_equivalent}")
        print(f"  Insight: {gap.key_insight}")
    
    print(f"\n{'=' * 70}")
    print(f"Summary: {len(critical)} critical, {len(high)} high, {len(medium)} medium")
    print(f"\nMeta-pattern: email evolved the RIGHT PRIMITIVES but the WRONG ENFORCEMENT MODEL.")
    print(f"  - SPF/DKIM/DMARC = correct abstractions (origin, signature, policy)")
    print(f"  - But: optional enforcement, no state machine, no observer rotation")
    print(f"  - ATF inherits the abstractions, fixes the enforcement")
    print(f"  - Key difference: ATF makes enforcement a REGISTRY CONSTANT, not a DOMAIN CHOICE")
    print(f"\nWhat email got right that ATF should keep:")
    print(f"  1. DNS as distributed trust anchor (SPF/DKIM/DMARC all use DNS)")
    print(f"  2. Incremental deployment (SPF works even if recipient doesn't check)")
    print(f"  3. Backward compatibility (unauthenticated mail still delivers)")
    print(f"  4. Separation of transport from content (SMTP vs MIME)")
    
    return True


if __name__ == "__main__":
    analyze()
