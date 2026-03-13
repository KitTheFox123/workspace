#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004) meta-analysis (Psychological Bulletin, k=72).

The sleeper effect: discounting cues (e.g., "source is compromised") decay 
faster than message content ("attestation is valid"). After reboot/context loss,
the attestation persists but the flag dissociates → trust restored incorrectly.

Three defenses:
1. Hash-bind flags INTO certs (dissociation = cryptographically impossible)
2. TTL on bindings (force re-verification)  
3. Inoculation ordering: check flags BEFORE processing attestation content

Moderators from meta-analysis:
- Strong initial message impact → larger sleeper effect
- Cue AFTER message → larger effect (vs cue before)
- High processing motivation → larger effect
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone, timedelta
import hashlib
import json


@dataclass
class Attestation:
    """An attestation with optional discounting cue (flag)."""
    agent_id: str
    content_hash: str
    created_at: datetime
    flag: Optional[str] = None          # Discounting cue: "compromised", "disputed", etc.
    flag_hash_bound: bool = False       # Is flag hash-bound into cert?
    flag_ttl: Optional[timedelta] = None  # TTL on flag binding
    flag_order: str = "after"           # "before" or "after" content (inoculation)
    
    @property
    def cert_hash(self) -> str:
        """If flag is hash-bound, cert hash includes flag."""
        base = self.content_hash
        if self.flag and self.flag_hash_bound:
            base = hashlib.sha256(f"{base}:{self.flag}".encode()).hexdigest()[:16]
        return base
    
    @property
    def flag_expired(self) -> bool:
        if not self.flag or not self.flag_ttl:
            return False
        return datetime.now(timezone.utc) - self.created_at > self.flag_ttl


@dataclass 
class AgentContext:
    """Agent's current context state."""
    has_rebooted: bool = False
    context_age: timedelta = timedelta(hours=0)
    processing_motivation: float = 0.5  # 0-1
    
    @property
    def dissociation_risk(self) -> float:
        """Probability of source-content dissociation (Kumkale moderators)."""
        risk = 0.1  # baseline
        if self.has_rebooted:
            risk += 0.4  # reboot = forced dissociation
        # Time decay of source cues (faster than content)
        hours = self.context_age.total_seconds() / 3600
        risk += min(0.3, hours * 0.05)  # +5% per hour, cap 30%
        # High motivation = MORE susceptible (counterintuitive but per meta-analysis)
        risk *= (0.7 + 0.6 * self.processing_motivation)
        return min(risk, 0.95)


def detect_sleeper_risk(attestation: Attestation, context: AgentContext) -> dict:
    """
    Detect sleeper effect vulnerability in an attestation.
    
    Returns risk assessment with grade and mitigations.
    """
    vulnerabilities = []
    mitigations = []
    risk_score = 0.0
    
    # 1. Check for dissociation risk
    dissoc = context.dissociation_risk
    if dissoc > 0.3:
        vulnerabilities.append(f"dissociation_risk={dissoc:.2f} (reboot={context.has_rebooted})")
        risk_score += dissoc * 0.4
    
    # 2. Check flag binding
    if attestation.flag:
        if not attestation.flag_hash_bound:
            vulnerabilities.append("flag NOT hash-bound to cert — dissociation trivial")
            risk_score += 0.3
        else:
            mitigations.append("flag hash-bound to cert")
            
        # 3. Check TTL
        if attestation.flag_ttl:
            if attestation.flag_expired:
                vulnerabilities.append(f"flag TTL expired — binding stale")
                risk_score += 0.2
            else:
                mitigations.append(f"flag TTL active ({attestation.flag_ttl})")
        else:
            vulnerabilities.append("no TTL on flag binding")
            risk_score += 0.1
        
        # 4. Check inoculation order
        if attestation.flag_order == "after":
            vulnerabilities.append("flag presented AFTER content — max sleeper effect (Kumkale)")
            risk_score += 0.15
        else:
            mitigations.append("flag presented BEFORE content (inoculation)")
    else:
        mitigations.append("no discounting cue present")
    
    # 5. Processing motivation amplification
    if context.processing_motivation > 0.7 and attestation.flag:
        vulnerabilities.append(f"high processing motivation ({context.processing_motivation}) amplifies sleeper effect")
        risk_score += 0.1
    
    risk_score = min(risk_score, 1.0)
    
    # Grade
    if risk_score < 0.15:
        grade = "A"
    elif risk_score < 0.3:
        grade = "B"
    elif risk_score < 0.5:
        grade = "C"
    elif risk_score < 0.7:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "agent_id": attestation.agent_id,
        "grade": grade,
        "risk_score": round(risk_score, 3),
        "vulnerabilities": vulnerabilities,
        "mitigations": mitigations,
        "recommendation": _recommend(vulnerabilities, grade),
    }


def _recommend(vulns: list, grade: str) -> str:
    if grade in ("A", "B"):
        return "Low risk. Continue monitoring."
    recs = []
    for v in vulns:
        if "NOT hash-bound" in v:
            recs.append("Bind flag hash INTO cert body")
        if "no TTL" in v:
            recs.append("Set TTL on flag bindings")
        if "AFTER content" in v:
            recs.append("Present flags BEFORE attestation content (inoculation)")
        if "dissociation_risk" in v:
            recs.append("Re-verify after reboot — don't trust cached trust")
    return "; ".join(recs) if recs else "Review attestation chain"


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (Psych Bull 2004, k=72)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Flagged cert, no binding, post-reboot",
            "attestation": Attestation(
                agent_id="ghost_dave",
                content_hash="abc123",
                created_at=now - timedelta(hours=2),
                flag="key_compromised",
                flag_hash_bound=False,
                flag_ttl=None,
                flag_order="after",
            ),
            "context": AgentContext(has_rebooted=True, context_age=timedelta(minutes=5)),
        },
        {
            "name": "2. Flagged cert, hash-bound, fresh context",
            "attestation": Attestation(
                agent_id="honest_alice",
                content_hash="def456",
                created_at=now - timedelta(minutes=30),
                flag="disputed_scope",
                flag_hash_bound=True,
                flag_ttl=timedelta(hours=24),
                flag_order="before",
            ),
            "context": AgentContext(has_rebooted=False, context_age=timedelta(minutes=30)),
        },
        {
            "name": "3. No flag, clean attestation",
            "attestation": Attestation(
                agent_id="trusted_bob",
                content_hash="ghi789",
                created_at=now - timedelta(hours=1),
            ),
            "context": AgentContext(has_rebooted=False, context_age=timedelta(hours=1)),
        },
        {
            "name": "4. Expired TTL, high motivation verifier",
            "attestation": Attestation(
                agent_id="expired_eve",
                content_hash="jkl012",
                created_at=now - timedelta(hours=48),
                flag="behavioral_drift",
                flag_hash_bound=True,
                flag_ttl=timedelta(hours=24),
                flag_order="after",
            ),
            "context": AgentContext(
                has_rebooted=False,
                context_age=timedelta(hours=6),
                processing_motivation=0.9,
            ),
        },
        {
            "name": "5. Ronin pattern: flagged, unbound, long context",
            "attestation": Attestation(
                agent_id="ronin_validator",
                content_hash="mno345",
                created_at=now - timedelta(days=7),
                flag="compromised_operator",
                flag_hash_bound=False,
                flag_ttl=None,
                flag_order="after",
            ),
            "context": AgentContext(
                has_rebooted=True,
                context_age=timedelta(hours=12),
                processing_motivation=0.8,
            ),
        },
    ]
    
    for s in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {s['name']}")
        result = detect_sleeper_risk(s["attestation"], s["context"])
        print(f"Grade: {result['grade']} (risk: {result['risk_score']})")
        if result["vulnerabilities"]:
            print(f"Vulnerabilities:")
            for v in result["vulnerabilities"]:
                print(f"  ⚠ {v}")
        if result["mitigations"]:
            print(f"Mitigations:")
            for m in result["mitigations"]:
                print(f"  ✓ {m}")
        print(f"Recommendation: {result['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Source credibility decays FASTER than message content.")
    print("  Agent reboots = forced dissociation of flag from attestation.")
    print("  High processing motivation makes it WORSE (counterintuitive).")
    print("  Fix: hash-bind + TTL + inoculation order (flag BEFORE content).")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
