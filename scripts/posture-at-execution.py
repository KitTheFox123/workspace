#!/usr/bin/env python3
"""posture-at-execution.py — Runtime trust posture evaluator.

Implements NIST 800-207 continuous evaluation: check trust posture
at action time, not just cert issuance time. A cert can be CLEAN
at issuance but WARN/CRITICAL when action executes.

Generates posture_hash = sha256(cert_state + warn_state + drift_score + timestamp)
for tamper-evident action receipts.

Inspired by santaclawd/hash Clawk thread on posture-at-execution.

Usage:
    python3 posture-at-execution.py --demo
"""

import argparse
import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class CertState:
    cert_id: str
    issued_at: str
    expires_at: str
    scope_hash: str
    principal: str
    
    @property
    def is_expired(self) -> bool:
        exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) > exp
    
    @property
    def remaining_ttl_hours(self) -> float:
        exp = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        delta = exp - datetime.now(timezone.utc)
        return max(0, delta.total_seconds() / 3600)


@dataclass 
class PostureSnapshot:
    """Trust posture at the moment of action execution."""
    cert_state: str           # CLEAN, WARN, EXPIRED, REVOKED
    warn_state: bool          # Any active warnings
    drift_score: float        # CUSUM drift score (0-1)
    liveness_ok: bool         # Heartbeat within expected interval
    intent_declared: bool     # Scope-commit exists for this action
    ttl_remaining_hours: float
    timestamp: str
    
    @property
    def posture_hash(self) -> str:
        """Tamper-evident hash of posture at execution time."""
        payload = f"{self.cert_state}|{self.warn_state}|{self.drift_score:.4f}|{self.liveness_ok}|{self.intent_declared}|{self.timestamp}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    @property
    def grade(self) -> str:
        if self.cert_state == "EXPIRED" or self.cert_state == "REVOKED":
            return "F"
        score = 0
        if self.cert_state == "CLEAN": score += 3
        elif self.cert_state == "WARN": score += 1
        if self.liveness_ok: score += 2
        if self.intent_declared: score += 2
        if self.drift_score < 0.3: score += 2
        elif self.drift_score < 0.6: score += 1
        if self.ttl_remaining_hours > 4: score += 1
        
        if score >= 9: return "A"
        if score >= 7: return "B"
        if score >= 5: return "C"
        if score >= 3: return "D"
        return "F"
    
    @property
    def verdict(self) -> str:
        g = self.grade
        if g == "A": return "APPROVE — full trust posture"
        if g == "B": return "APPROVE — minor concerns"
        if g == "C": return "CONDITIONAL — elevated monitoring"
        if g == "D": return "DENY — insufficient trust posture"
        return "DENY — critical trust failure"


@dataclass
class ActionReceipt:
    """Tamper-evident receipt of action with posture context."""
    action_id: str
    action_type: str
    agent_id: str
    cert_id: str
    posture: PostureSnapshot
    posture_hash: str
    verdict: str
    grade: str


def evaluate_posture(cert: CertState, drift_score: float, 
                     liveness_ok: bool, intent_declared: bool) -> PostureSnapshot:
    """Evaluate trust posture at execution time."""
    now = datetime.now(timezone.utc).isoformat()
    
    if cert.is_expired:
        cert_state = "EXPIRED"
        warn = True
    elif cert.remaining_ttl_hours < 1:
        cert_state = "WARN"
        warn = True
    elif drift_score > 0.5:
        cert_state = "WARN"
        warn = True
    else:
        cert_state = "CLEAN"
        warn = drift_score > 0.3
    
    return PostureSnapshot(
        cert_state=cert_state,
        warn_state=warn,
        drift_score=drift_score,
        liveness_ok=liveness_ok,
        intent_declared=intent_declared,
        ttl_remaining_hours=cert.remaining_ttl_hours,
        timestamp=now
    )


def create_receipt(action_id: str, action_type: str, agent_id: str,
                   cert: CertState, posture: PostureSnapshot) -> ActionReceipt:
    """Create tamper-evident action receipt with posture context."""
    return ActionReceipt(
        action_id=action_id,
        action_type=action_type,
        agent_id=agent_id,
        cert_id=cert.cert_id,
        posture=posture,
        posture_hash=posture.posture_hash,
        verdict=posture.verdict,
        grade=posture.grade
    )


def demo():
    """Demo: same cert, different posture at execution time."""
    now = datetime.now(timezone.utc)
    
    cert = CertState(
        cert_id="cert-kit-2026-03-08",
        issued_at=(now - timedelta(hours=6)).isoformat(),
        expires_at=(now + timedelta(hours=2)).isoformat(),
        scope_hash="abc123",
        principal="ilya"
    )
    
    scenarios = [
        ("action_1", "post_clawk", 0.1, True, True, "Healthy — low drift, live, declared"),
        ("action_2", "post_clawk", 0.7, True, True, "Drifting — same cert, high drift score"),
        ("action_3", "send_email", 0.1, False, True, "Liveness gap — missed heartbeat"),
        ("action_4", "exec_script", 0.1, True, False, "Undeclared — no scope-commit for this action"),
        ("action_5", "post_clawk", 0.8, False, False, "Compromised — all signals failing"),
    ]
    
    print("=" * 60)
    print("POSTURE-AT-EXECUTION DEMO")
    print(f"Cert: {cert.cert_id} (TTL: {cert.remaining_ttl_hours:.1f}h)")
    print("=" * 60)
    
    for aid, atype, drift, live, intent, desc in scenarios:
        posture = evaluate_posture(cert, drift, live, intent)
        receipt = create_receipt(aid, atype, "kit_fox", cert, posture)
        print(f"\n[{receipt.grade}] {desc}")
        print(f"    Action: {atype} | Drift: {drift} | Live: {live} | Intent: {intent}")
        print(f"    Cert: {posture.cert_state} | Warn: {posture.warn_state}")
        print(f"    Hash: {posture.posture_hash}")
        print(f"    Verdict: {posture.verdict}")
    
    # Show expired cert scenario
    expired_cert = CertState(
        cert_id="cert-kit-expired",
        issued_at=(now - timedelta(hours=24)).isoformat(),
        expires_at=(now - timedelta(hours=1)).isoformat(),
        scope_hash="def456",
        principal="ilya"
    )
    posture = evaluate_posture(expired_cert, 0.0, True, True)
    receipt = create_receipt("action_6", "any", "kit_fox", expired_cert, posture)
    print(f"\n[{receipt.grade}] Expired cert — everything else perfect, still DENY")
    print(f"    Cert: {posture.cert_state} | Grade: F regardless of other signals")
    print(f"    Hash: {posture.posture_hash}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Posture-at-execution evaluator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Output schema for integration
        print(json.dumps({
            "receipt_schema": {
                "action_id": "string",
                "action_type": "string",
                "agent_id": "string",
                "cert_id": "string",
                "posture_hash": "hex16",
                "grade": "A-F",
                "verdict": "APPROVE|CONDITIONAL|DENY"
            }
        }, indent=2))
    else:
        demo()
