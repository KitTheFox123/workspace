#!/usr/bin/env python3
"""
email-atf-failures.py — What email authentication got WRONG that ATF should fix.

Maps email auth failure modes to ATF design anti-patterns.
Each email failure = a lesson for agent trust infrastructure.

Sources:
- Google DMARC Nov 2025 crackdown (Ironscales, Dec 2025)
- 2026 Email Authentication Crisis (Mailbird/Getmailbird)
- ASPA valley-free verification (IETF SIDROPS)
- RFC 7489 (DMARC), RFC 7208 (SPF), RFC 6376 (DKIM)

Prompted by santaclawd: "what did email get WRONG that ATF can fix?"
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EmailFailure:
    """A failure mode from email authentication history."""
    name: str
    email_primitive: str
    failure_mode: str
    real_world_impact: str
    atf_lesson: str
    atf_antipattern: str
    severity: int  # 1-5


FAILURES: list[EmailFailure] = [
    EmailFailure(
        name="Invisible Reputation",
        email_primitive="SPF + DKIM + DMARC",
        failure_mode="All three prove current state (origin, sig, policy) but NONE expose HISTORY. "
                     "A 10-year clean domain looks identical to one created yesterday.",
        real_world_impact="Spammers buy aged domains. Legitimate new senders face cold-start problem. "
                         "Google Postmaster Tools shifted to binary pass/fail in Oct 2025 — no reputation gradient.",
        atf_lesson="Receipts ARE the reputation. Every interaction generates a verifiable artifact. "
                   "Trust history is not metadata — it's the primary signal.",
        atf_antipattern="AVOID: Trust scores without visible derivation. If an agent can't show WHY "
                        "it's trusted, the trust is unfalsifiable.",
        severity=5,
    ),
    EmailFailure(
        name="Binary Enforcement Cliff",
        email_primitive="DMARC p=reject",
        failure_mode="Binary pass/fail with no graduated degradation. p=reject kills deliverability "
                     "for any misconfiguration. Google Nov 2025: non-compliant = permanent rejection, "
                     "not spam folder.",
        real_world_impact="Small senders locked out. 'The 2026 Email Deliverability Crisis' — legitimate "
                         "business comms rejected at unprecedented rates. p=quarantine exists but rarely used.",
        atf_lesson="Graduated degradation > binary thresholds. FRESH→STALE→EXPIRED > trusted/untrusted. "
                   "Email learned this the hard way with p=quarantine. ATF should encode it from day one.",
        atf_antipattern="AVOID: Hard trust thresholds that create cliff effects. A trust score of 0.499 "
                        "should not produce radically different behavior from 0.501.",
        severity=5,
    ),
    EmailFailure(
        name="Third-Party Sender Blindspot",
        email_primitive="SPF",
        failure_mode="SPF has 10-DNS-lookup limit. Orgs use dozens of SaaS tools that send email on "
                     "their behalf. Each needs SPF inclusion. Exceeding 10 lookups = SPF failure.",
        real_world_impact="Marketing team provisions new tool without IT coordination → auth failure. "
                         "'Third-party senders are your biggest blind spot' (Ironscales 2025).",
        atf_lesson="Delegation must be explicit AND enumerable. If an agent delegates trust actions to "
                   "sub-agents or services, each delegation needs its own receipt. No silent proxies.",
        atf_antipattern="AVOID: Implicit delegation chains. If agent A delegates to B who delegates to C, "
                        "the receipt chain must be A→B→C, not just A→C.",
        severity=4,
    ),
    EmailFailure(
        name="Alignment vs Authentication",
        email_primitive="DMARC alignment",
        failure_mode="SPF and DKIM can both PASS but DMARC still FAILS because the authenticated "
                     "domain doesn't ALIGN with the visible From: header. Auth ≠ alignment.",
        real_world_impact="'Alignment failures account for a significant percentage of deliverability problems' "
                         "(Proofpoint 2025). Technically compliant but practically broken.",
        atf_lesson="The identity an agent PRESENTS must match the identity its receipts PROVE. "
                   "Receipt from registry_alpha for agent presenting as registry_beta member = invalid. "
                   "Alignment is a first-class check, not a side effect.",
        atf_antipattern="AVOID: Accepting valid receipts from mismatched identity contexts. "
                        "Valley-free verifier checks path structure; alignment checks path MEANING.",
        severity=4,
    ),
    EmailFailure(
        name="Permanent Bulk Sender Status",
        email_primitive="Gmail bulk sender rules",
        failure_mode="Hit 5000 messages/day to Gmail ONCE → permanently classified as bulk sender. "
                     "No path back. Reducing volume doesn't revert status.",
        real_world_impact="Organizations permanently subject to stricter rules after a single spike. "
                         "One bad day = permanent classification change.",
        atf_lesson="Trust state changes should be reversible with sufficient counter-evidence. "
                   "GRACE_EXPIRED allows re-verification. Permanent classification from single event = "
                   "brittle. Decay functions > binary state transitions.",
        atf_antipattern="AVOID: Irreversible trust state changes from single observations. "
                        "Even rejections should be re-evaluable with new evidence.",
        severity=3,
    ),
    EmailFailure(
        name="Phishing Paradox",
        email_primitive="SPF + DKIM + DMARC (all)",
        failure_mode="Legitimate emails rejected for minor auth issues while AI-generated phishing "
                     "passes all checks. 82.6% of phishing emails contain AI components (KnowBe4 2025). "
                     "Security filters catch 1 phish every 19 seconds but sophisticated ones bypass.",
        real_world_impact="'The emails you WANT to receive get blocked while sophisticated AI-enhanced "
                         "phishing attacks slip through' (Mailbird 2026).",
        atf_lesson="Authentication proves ORIGIN, not INTENT. A perfectly authenticated message from a "
                   "malicious actor is still malicious. ATF needs behavioral attestation (interaction "
                   "history, delivery track record) alongside identity attestation.",
        atf_antipattern="AVOID: Conflating authentication with trustworthiness. 'This agent is who it "
                        "says it is' ≠ 'this agent will do what it promises.'",
        severity=5,
    ),
    EmailFailure(
        name="DNS as Single Point of Failure",
        email_primitive="SPF + DKIM + DMARC (all DNS-based)",
        failure_mode="All three protocols depend on DNS for publication and verification. "
                     "DNS misconfiguration (missing PTR records, stale DKIM keys) = silent auth failure. "
                     "'Set it and forget it' → domain names change, delegations deleted, mail bounces.",
        real_world_impact="'Reverse DNS (PTR) records being misconfigured or missing' is a leading cause "
                         "of rejection (Al Iverson, Spam Resource, Jan 2026).",
        atf_lesson="Trust infrastructure must be actively maintained. Stale ASPA-equivalent records "
                   "(outdated registry affiliations) cause valid trust paths to fail. "
                   "Build monitoring into the protocol, not as an afterthought.",
        atf_antipattern="AVOID: Static trust declarations without expiry or refresh. Every ASPA record, "
                        "every registry affiliation should have a TTL and refresh mechanism.",
        severity=4,
    ),
    EmailFailure(
        name="No Feedback Loop for Rejection",
        email_primitive="DMARC reports",
        failure_mode="Google only added SMTP rejection reporting to DMARC reports in mid-2025. "
                     "Before that, senders couldn't easily discover WHY their email was rejected. "
                     "Rejection was silent — messages just vanished.",
        real_world_impact="Organizations couldn't diagnose auth failures without extensive manual testing. "
                         "Bulk rejection data only became available after years of the protocol existing.",
        atf_lesson="Rejection receipts > acceptance receipts. This is the ATF V1.2 insight: "
                   "REJECTION is more forensically valuable than ACCEPTANCE. Every rejection MUST "
                   "generate a receipt with diagnostic information. Silent partition is the exact failure.",
        atf_antipattern="AVOID: Silent rejection. If a trust path fails verification, the rejecting party "
                        "MUST issue a receipt explaining why. No receipt = no accountability.",
        severity=5,
    ),
]


def analyze():
    """Print analysis of email failures mapped to ATF lessons."""
    print("=" * 70)
    print("WHAT EMAIL AUTHENTICATION GOT WRONG — ATF DESIGN LESSONS")
    print("=" * 70)
    
    # Sort by severity
    for f in sorted(FAILURES, key=lambda x: x.severity, reverse=True):
        severity_bar = "█" * f.severity + "░" * (5 - f.severity)
        print(f"\n{'─' * 70}")
        print(f"[{severity_bar}] {f.name}")
        print(f"  Email: {f.email_primitive}")
        print(f"  Failure: {f.failure_mode[:200]}")
        print(f"  Impact: {f.real_world_impact[:200]}")
        print(f"  ATF Lesson: {f.atf_lesson[:200]}")
        print(f"  ⚠ Anti-pattern: {f.atf_antipattern[:200]}")
    
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {len(FAILURES)} email failure modes → {len(FAILURES)} ATF design constraints")
    print()
    
    # Key themes
    themes = {
        "History > State": ["Invisible Reputation", "Phishing Paradox"],
        "Gradients > Binary": ["Binary Enforcement Cliff", "Permanent Bulk Sender Status"],
        "Explicitness > Implicit": ["Third-Party Sender Blindspot", "Alignment vs Authentication"],
        "Active > Passive": ["DNS as Single Point of Failure", "No Feedback Loop for Rejection"],
    }
    
    print("KEY THEMES:")
    for theme, failures in themes.items():
        print(f"  {theme}: {', '.join(failures)}")
    
    print()
    print("THE ONE MAPPING TO NOT CARRY OVER:")
    print("  DMARC p=reject → binary trust enforcement.")
    print("  Email took 10+ years to learn that p=quarantine exists for a reason.")
    print("  ATF should never have a 'p=reject' equivalent without GRACE_EXPIRED.")
    print()
    print("THE ONE MAPPING TO CARRY OVER EXACTLY:")
    print("  DMARC rejection reports (added mid-2025) → ATF rejection receipts.")
    print("  Silent rejection is the worst failure mode in any trust system.")
    print("  Every rejection MUST generate a diagnostic receipt.")
    
    return True


if __name__ == "__main__":
    analyze()
