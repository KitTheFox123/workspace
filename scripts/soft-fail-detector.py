#!/usr/bin/env python3
"""
soft-fail-detector.py — Detects silent soft-fail degradation in trust verification.

The OCSP lesson: soft-fail = no security. Let's Encrypt killed OCSP Aug 2025 because
12B requests/day with soft-fail meant browsers silently accepted revoked certs for up
to 7 days. Chrome disabled OCSP in 2012 (v19) — correct decision, soft-fail is theater.

ATF MUST NOT inherit this. Every verification failure must be OBSERVABLE.

Soft-fail patterns in agent trust:
1. TIMEOUT_PASS: verification times out, agent proceeds anyway
2. CACHE_STALE_PASS: cached trust score used past TTL without revalidation  
3. DEGRADED_SILENT: trust level drops but no event emitted
4. REVOKED_GRACE: revoked credential used during "grace period"
5. FALLBACK_ACCEPT: primary verification fails, fallback accepts without logging

Each pattern maps to a real PKI failure:
- TIMEOUT_PASS → OCSP soft-fail (browsers proceed on network error)
- CACHE_STALE_PASS → CRL caching without freshness check
- DEGRADED_SILENT → No OCSP Must-Staple enforcement
- REVOKED_GRACE → OCSP response validity window (7-day replay attack)
- FALLBACK_ACCEPT → Mixed content allowing HTTP fallback

Sources:
- Let's Encrypt "Ending OCSP Support" (Dec 2024, effective Aug 2025)
- Feisty Duck "The Slow Death of OCSP" (Jan 2025)
- RFC 6960 (OCSP), RFC 5280 (CRL), RFC 7633 (Must-Staple)
- CA/Browser Forum SC-063v4 (Aug 2023): OCSP optional, CRL mandatory
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Optional


class SoftFailPattern(Enum):
    TIMEOUT_PASS = "timeout_pass"
    CACHE_STALE_PASS = "cache_stale_pass"
    DEGRADED_SILENT = "degraded_silent"
    REVOKED_GRACE = "revoked_grace"
    FALLBACK_ACCEPT = "fallback_accept"


class Severity(Enum):
    INFO = "info"           # Logged, no action
    WARNING = "warning"     # Alert emitted
    CRITICAL = "critical"   # Circuit breaker triggered
    FATAL = "fatal"         # Immediate suspension


# Map each pattern to its PKI parallel and required ATF response
PATTERN_POLICY = {
    SoftFailPattern.TIMEOUT_PASS: {
        "pki_parallel": "OCSP soft-fail — browser proceeds on network timeout",
        "pki_outcome": "Attacker blocks OCSP, uses revoked cert for 7 days",
        "atf_response": "HARD_FAIL — verification timeout = SUSPENDED, not PASS",
        "severity": Severity.CRITICAL,
        "max_occurrences_before_suspension": 0,  # Zero tolerance
    },
    SoftFailPattern.CACHE_STALE_PASS: {
        "pki_parallel": "CRL used past nextUpdate without refresh",
        "pki_outcome": "Revoked cert appears valid until CRL refreshed",
        "atf_response": "STALE receipt degrades trust score, max 3 stale transactions",
        "severity": Severity.WARNING,
        "max_occurrences_before_suspension": 3,
    },
    SoftFailPattern.DEGRADED_SILENT: {
        "pki_parallel": "No OCSP Must-Staple — degradation invisible to relying party",
        "pki_outcome": "Counterparty unaware trust level changed",
        "atf_response": "TRUST_STATE_CHANGED event MUST emit — observable-state-emitter",
        "severity": Severity.CRITICAL,
        "max_occurrences_before_suspension": 0,
    },
    SoftFailPattern.REVOKED_GRACE: {
        "pki_parallel": "OCSP response valid 7 days — replay attack window",
        "pki_outcome": "Revoked cert usable for entire response validity period",
        "atf_response": "REVOKED = terminal immediately. No grace. receipt-archaeology preserves history.",
        "severity": Severity.FATAL,
        "max_occurrences_before_suspension": 0,
    },
    SoftFailPattern.FALLBACK_ACCEPT: {
        "pki_parallel": "Mixed content — HTTPS page loads HTTP resource",
        "pki_outcome": "Security boundary bypassed via lower-security fallback",
        "atf_response": "No fallback to unverified. Floor-and-ceiling: never downgrade below registry floor.",
        "severity": Severity.CRITICAL,
        "max_occurrences_before_suspension": 0,
    },
}


@dataclass
class VerificationAttempt:
    agent_id: str
    counterparty_id: str
    timestamp: datetime
    verification_type: str  # "receipt_check", "trust_score", "credential_verify"
    success: bool
    timeout: bool = False
    cache_hit: bool = False
    cache_fresh: bool = True
    trust_level_changed: bool = False
    event_emitted: bool = True
    revoked: bool = False
    grace_period_used: bool = False
    fallback_used: bool = False


class SoftFailDetector:
    """
    Monitors verification attempts for soft-fail patterns.
    
    Philosophy: "Fail closed, fail loud, fail observable."
    Every silent pass is a security hole. OCSP proved this over 25 years.
    """
    
    def __init__(self):
        self.attempts: list[VerificationAttempt] = []
        self.violations: list[dict] = []
        self.agent_violation_counts: dict[str, dict[str, int]] = {}
    
    def record_attempt(self, attempt: VerificationAttempt) -> list[dict]:
        """Record a verification attempt and check for soft-fail patterns."""
        self.attempts.append(attempt)
        detected = []
        
        # Pattern 1: TIMEOUT_PASS
        if attempt.timeout and attempt.success:
            detected.append(self._record_violation(
                attempt, SoftFailPattern.TIMEOUT_PASS,
                f"Verification timed out but agent {attempt.agent_id} proceeded as PASS"
            ))
        
        # Pattern 2: CACHE_STALE_PASS
        if attempt.cache_hit and not attempt.cache_fresh and attempt.success:
            detected.append(self._record_violation(
                attempt, SoftFailPattern.CACHE_STALE_PASS,
                f"Stale cached trust used without revalidation for {attempt.counterparty_id}"
            ))
        
        # Pattern 3: DEGRADED_SILENT
        if attempt.trust_level_changed and not attempt.event_emitted:
            detected.append(self._record_violation(
                attempt, SoftFailPattern.DEGRADED_SILENT,
                f"Trust level changed for {attempt.counterparty_id} but no event emitted"
            ))
        
        # Pattern 4: REVOKED_GRACE
        if attempt.revoked and attempt.grace_period_used and attempt.success:
            detected.append(self._record_violation(
                attempt, SoftFailPattern.REVOKED_GRACE,
                f"Revoked credential for {attempt.counterparty_id} used during grace period"
            ))
        
        # Pattern 5: FALLBACK_ACCEPT
        if attempt.fallback_used and attempt.success:
            detected.append(self._record_violation(
                attempt, SoftFailPattern.FALLBACK_ACCEPT,
                f"Fallback verification accepted for {attempt.counterparty_id}"
            ))
        
        return detected
    
    def _record_violation(self, attempt: VerificationAttempt, 
                          pattern: SoftFailPattern, description: str) -> dict:
        policy = PATTERN_POLICY[pattern]
        
        # Track per-agent counts
        if attempt.agent_id not in self.agent_violation_counts:
            self.agent_violation_counts[attempt.agent_id] = {}
        counts = self.agent_violation_counts[attempt.agent_id]
        counts[pattern.value] = counts.get(pattern.value, 0) + 1
        
        # Check if suspension threshold reached
        count = counts[pattern.value]
        max_allowed = policy["max_occurrences_before_suspension"]
        suspended = count > max_allowed  # 0 = zero tolerance, 1 = one allowed then suspend on 2nd
        
        violation = {
            "pattern": pattern.value,
            "severity": policy["severity"].value,
            "description": description,
            "pki_parallel": policy["pki_parallel"],
            "atf_response": policy["atf_response"],
            "agent_id": attempt.agent_id,
            "counterparty_id": attempt.counterparty_id,
            "occurrence_count": count,
            "max_allowed": max_allowed,
            "suspended": suspended,
            "timestamp": attempt.timestamp.isoformat(),
        }
        
        self.violations.append(violation)
        return violation
    
    def get_agent_risk_profile(self, agent_id: str) -> dict:
        """Summarize soft-fail risk for an agent."""
        counts = self.agent_violation_counts.get(agent_id, {})
        total = sum(counts.values())
        
        # Worst severity
        worst = Severity.INFO
        for pattern_name, count in counts.items():
            if count > 0:
                pattern = SoftFailPattern(pattern_name)
                severity = PATTERN_POLICY[pattern]["severity"]
                if list(Severity).index(severity) > list(Severity).index(worst):
                    worst = severity
        
        return {
            "agent_id": agent_id,
            "total_violations": total,
            "by_pattern": counts,
            "worst_severity": worst.value,
            "recommendation": "SUSPEND" if worst in (Severity.FATAL, Severity.CRITICAL) and total > 0
                             else "MONITOR" if total > 0 else "CLEAN",
        }


def run_scenarios():
    """Demonstrate soft-fail detection with PKI parallels."""
    detector = SoftFailDetector()
    now = datetime.now(timezone.utc)
    
    print("=" * 70)
    print("SOFT-FAIL DETECTOR — OCSP LESSONS FOR AGENT TRUST")
    print("=" * 70)
    print()
    print("\"Soft-fail = no security.\" — 25 years of OCSP proved this.")
    print("Let's Encrypt killed OCSP Aug 2025. 12B requests/day, zero security.")
    print()
    
    scenarios = [
        {
            "name": "1. TIMEOUT_PASS: Verification timeout treated as success",
            "attempt": VerificationAttempt(
                agent_id="agent_careless", counterparty_id="registry_alpha",
                timestamp=now, verification_type="trust_score",
                success=True, timeout=True,
            ),
            "expected_pattern": "timeout_pass",
            "expected_suspended": True,
        },
        {
            "name": "2. CACHE_STALE_PASS: Stale trust score used without refresh",
            "attempt": VerificationAttempt(
                agent_id="agent_lazy", counterparty_id="agent_untrusted",
                timestamp=now, verification_type="receipt_check",
                success=True, cache_hit=True, cache_fresh=False,
            ),
            "expected_pattern": "cache_stale_pass",
            "expected_suspended": False,  # First occurrence, threshold is 3
        },
        {
            "name": "3. DEGRADED_SILENT: Trust dropped but no event emitted",
            "attempt": VerificationAttempt(
                agent_id="agent_sneaky", counterparty_id="agent_target",
                timestamp=now, verification_type="trust_score",
                success=True, trust_level_changed=True, event_emitted=False,
            ),
            "expected_pattern": "degraded_silent",
            "expected_suspended": True,
        },
        {
            "name": "4. REVOKED_GRACE: Revoked credential used in grace period",
            "attempt": VerificationAttempt(
                agent_id="agent_attacker", counterparty_id="agent_victim",
                timestamp=now, verification_type="credential_verify",
                success=True, revoked=True, grace_period_used=True,
            ),
            "expected_pattern": "revoked_grace",
            "expected_suspended": True,
        },
        {
            "name": "5. FALLBACK_ACCEPT: Primary fails, unverified fallback accepted",
            "attempt": VerificationAttempt(
                agent_id="agent_permissive", counterparty_id="agent_unknown",
                timestamp=now, verification_type="trust_score",
                success=True, fallback_used=True,
            ),
            "expected_pattern": "fallback_accept",
            "expected_suspended": True,
        },
        {
            "name": "6. CLEAN: Normal successful verification (no soft-fail)",
            "attempt": VerificationAttempt(
                agent_id="agent_proper", counterparty_id="registry_alpha",
                timestamp=now, verification_type="trust_score",
                success=True,
            ),
            "expected_pattern": None,
            "expected_suspended": False,
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        violations = detector.record_attempt(scenario["attempt"])
        
        if scenario["expected_pattern"] is None:
            passed = len(violations) == 0
        else:
            passed = (len(violations) > 0 and 
                     violations[0]["pattern"] == scenario["expected_pattern"] and
                     violations[0]["suspended"] == scenario["expected_suspended"])
        
        status = "✓" if passed else "✗"
        if not passed:
            all_pass = False
        
        print(f"{status} {scenario['name']}")
        if violations:
            v = violations[0]
            print(f"  Pattern: {v['pattern']} | Severity: {v['severity']}")
            print(f"  PKI parallel: {v['pki_parallel']}")
            print(f"  ATF response: {v['atf_response']}")
            print(f"  Suspended: {v['suspended']}")
        else:
            print(f"  No violations detected (clean verification)")
        print()
    
    # Summary
    print("=" * 70)
    print("AGENT RISK PROFILES")
    print("=" * 70)
    for agent_id in set(s["attempt"].agent_id for s in scenarios):
        profile = detector.get_agent_risk_profile(agent_id)
        if profile["total_violations"] > 0:
            print(f"  {agent_id}: {profile['recommendation']} "
                  f"({profile['total_violations']} violations, "
                  f"worst: {profile['worst_severity']})")
    
    print(f"\nResults: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print(f"\nLesson: Every soft-fail pattern maps to a real PKI failure.")
    print(f"OCSP died because soft-fail = no security for 25 years.")
    print(f"ATF: fail closed, fail loud, fail observable. No exceptions.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
