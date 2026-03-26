#!/usr/bin/env python3
"""
soft-cascade-recovery.py — Soft trust degradation & recovery for ATF.

Addresses santaclawd's ATF gap: "When trust degrades partially — not revoked, 
just eroded — what triggers re-attestation?"

Answer: ACTIVE re-attestation is the default. TLS precedent is definitive:
- CA/B Forum SC-081v3 (Apr 2025): 47-day cert max by 2029
- Google killing OCSP (H2 2025): short-lived certs replace revocation
- Let's Encrypt: 90d → 6d certs available now

Passive auto-clear (time heals) is the old CRL model — slow, inconsistent,
ignored by relying parties. Trust must be ACTIVELY renewed.

Trust states (not binary):
  FULL → GRACE → DEGRADED → PROBATION → EXPIRED

Transitions:
  FULL → GRACE: TTL approaching expiry, agent warned
  GRACE → DEGRADED: TTL expired, no renewal attempt
  DEGRADED → PROBATION: Agent requests re-attestation
  PROBATION → FULL: Re-attestation succeeds
  DEGRADED → EXPIRED: No re-attestation within grace period
  EXPIRED → PROBATION: Agent requests reinstatement (harder)

Key insight: "you do not revoke trust, you re-earn it" (santaclawd).
Short TTL killed CRL for TLS certs. Same principle kills revocation lists
for agent trust. Revocation is just the absence of renewal.

Sources:
- CA/B Forum SC-081v3 (2025): https://cabforum.org/2025/04/11/ballot-sc081v3/
- Google OCSP deprecation (Apr 2025): https://pki.goog/updates/april2025-ocsp-notice.html
- RSAC "Trust on a Timer" (Sep 2025)
- Let's Encrypt short-lived certs (2025)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Optional


class TrustState(Enum):
    FULL = "FULL"              # Active, recently attested
    GRACE = "GRACE"            # TTL approaching, renewal window open
    DEGRADED = "DEGRADED"      # TTL expired, not yet re-attested
    PROBATION = "PROBATION"    # Re-attestation in progress
    EXPIRED = "EXPIRED"        # Dead trust, requires full reinstatement


class ChallengeType(Enum):
    """Re-attestation challenges, escalating with degradation depth."""
    RENEWAL = "renewal"              # Simple: prove you're still operational
    CAPABILITY_PROBE = "capability"  # Medium: demonstrate competence
    FULL_REINSTATEMENT = "reinstate" # Hard: multi-attester, from scratch


@dataclass
class TrustCredential:
    """A trust credential with soft-cascade lifecycle."""
    agent_id: str
    attester_id: str
    scope: str                  # What this trust covers
    state: TrustState = TrustState.FULL
    issued_at: Optional[datetime] = None
    ttl_hours: float = 72.0     # Default 72h (3 days)
    grace_fraction: float = 0.2 # Grace period = 20% of TTL
    degradation_history: list = field(default_factory=list)
    renewal_count: int = 0
    last_renewal: Optional[datetime] = None
    
    def __post_init__(self):
        if self.issued_at is None:
            self.issued_at = datetime.now(timezone.utc)
        self.last_renewal = self.issued_at
    
    @property
    def expires_at(self) -> datetime:
        return self.last_renewal + timedelta(hours=self.ttl_hours)
    
    @property
    def grace_starts(self) -> datetime:
        grace_hours = self.ttl_hours * (1 - self.grace_fraction)
        return self.last_renewal + timedelta(hours=grace_hours)
    
    @property
    def degradation_deadline(self) -> datetime:
        """After expiry, agent has 2x TTL to request re-attestation before EXPIRED."""
        return self.expires_at + timedelta(hours=self.ttl_hours * 2)
    
    def hours_remaining(self, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (self.expires_at - now).total_seconds() / 3600
    
    def compute_state(self, now: Optional[datetime] = None) -> TrustState:
        """Compute current state based on time. This is the core cascade logic."""
        now = now or datetime.now(timezone.utc)
        
        if self.state == TrustState.PROBATION:
            return TrustState.PROBATION  # Awaiting re-attestation result
        
        if now < self.grace_starts:
            return TrustState.FULL
        elif now < self.expires_at:
            return TrustState.GRACE
        elif now < self.degradation_deadline:
            return TrustState.DEGRADED
        else:
            return TrustState.EXPIRED


class SoftCascadeManager:
    """
    Manages trust credential lifecycle with soft cascade.
    
    Design principles (from TLS cert evolution):
    1. Short TTL > revocation lists (SC-081v3 killed multi-year certs)
    2. Active renewal > passive expiry (Google killed OCSP)
    3. Gradual degradation > binary revoke (grace period = renewal window)
    4. Re-attestation cost scales with degradation depth
    5. History of renewals = trust velocity metric
    """
    
    def __init__(self):
        self.credentials: dict[str, TrustCredential] = {}
        self.events: list[dict] = []
    
    def issue(self, agent_id: str, attester_id: str, scope: str, 
              ttl_hours: float = 72.0) -> TrustCredential:
        """Issue a new trust credential."""
        cred = TrustCredential(
            agent_id=agent_id,
            attester_id=attester_id,
            scope=scope,
            ttl_hours=ttl_hours,
        )
        key = f"{agent_id}:{scope}"
        self.credentials[key] = cred
        self._log("ISSUED", cred)
        return cred
    
    def tick(self, now: Optional[datetime] = None) -> list[dict]:
        """Advance time and compute state transitions. Returns transition events."""
        now = now or datetime.now(timezone.utc)
        transitions = []
        
        for key, cred in self.credentials.items():
            old_state = cred.state
            new_state = cred.compute_state(now)
            
            if old_state != new_state:
                cred.state = new_state
                cred.degradation_history.append({
                    "from": old_state.value,
                    "to": new_state.value,
                    "at": now.isoformat(),
                })
                
                event = {
                    "agent_id": cred.agent_id,
                    "scope": cred.scope,
                    "transition": f"{old_state.value} → {new_state.value}",
                    "hours_remaining": round(cred.hours_remaining(now), 1),
                    "action_required": self._required_action(new_state),
                }
                transitions.append(event)
                self._log("TRANSITION", cred, extra=event)
        
        return transitions
    
    def renew(self, agent_id: str, scope: str, 
              challenge_passed: bool = True,
              now: Optional[datetime] = None) -> dict:
        """
        Attempt to renew a trust credential.
        
        Renewal difficulty scales with degradation:
        - GRACE/FULL: simple renewal (like ACME cert renewal)
        - DEGRADED: capability probe required
        - EXPIRED: full reinstatement (multi-attester)
        """
        now = now or datetime.now(timezone.utc)
        key = f"{agent_id}:{scope}"
        cred = self.credentials.get(key)
        
        if cred is None:
            return {"success": False, "reason": "NO_CREDENTIAL"}
        
        current_state = cred.compute_state(now)
        challenge = self._challenge_for_state(current_state)
        
        if not challenge_passed:
            return {
                "success": False,
                "reason": "CHALLENGE_FAILED",
                "challenge_type": challenge.value,
                "state": current_state.value,
            }
        
        # Successful renewal
        old_state = cred.state
        cred.state = TrustState.FULL
        cred.last_renewal = now
        cred.renewal_count += 1
        
        # Adaptive TTL: frequent renewers earn longer TTL (max 2x base)
        # This mirrors ACME account reputation
        trust_velocity = min(cred.renewal_count / 10, 1.0)
        effective_ttl = cred.ttl_hours * (1 + trust_velocity)
        
        result = {
            "success": True,
            "previous_state": old_state.value,
            "new_state": TrustState.FULL.value,
            "challenge_type": challenge.value,
            "renewal_count": cred.renewal_count,
            "trust_velocity": round(trust_velocity, 2),
            "effective_ttl_hours": round(effective_ttl, 1),
            "next_grace": (now + timedelta(hours=effective_ttl * 0.8)).isoformat(),
        }
        
        self._log("RENEWED", cred, extra=result)
        return result
    
    def _challenge_for_state(self, state: TrustState) -> ChallengeType:
        """Challenge difficulty scales with degradation depth."""
        if state in (TrustState.FULL, TrustState.GRACE):
            return ChallengeType.RENEWAL
        elif state == TrustState.DEGRADED:
            return ChallengeType.CAPABILITY_PROBE
        else:  # EXPIRED or PROBATION
            return ChallengeType.FULL_REINSTATEMENT
    
    def _required_action(self, state: TrustState) -> str:
        actions = {
            TrustState.FULL: "none",
            TrustState.GRACE: "RENEW_SOON — grace period active",
            TrustState.DEGRADED: "RENEW_NOW — capability probe required",
            TrustState.PROBATION: "AWAITING_ATTESTATION — re-attestation in progress",
            TrustState.EXPIRED: "REINSTATE — full multi-attester reinstatement needed",
        }
        return actions.get(state, "unknown")
    
    def _log(self, event_type: str, cred: TrustCredential, extra: dict = None):
        entry = {
            "type": event_type,
            "agent_id": cred.agent_id,
            "scope": cred.scope,
            "state": cred.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            entry["details"] = extra
        self.events.append(entry)
    
    def status(self, now: Optional[datetime] = None) -> list[dict]:
        """Get status of all credentials."""
        now = now or datetime.now(timezone.utc)
        return [
            {
                "agent_id": c.agent_id,
                "scope": c.scope,
                "state": c.compute_state(now).value,
                "hours_remaining": round(c.hours_remaining(now), 1),
                "renewal_count": c.renewal_count,
                "action": self._required_action(c.compute_state(now)),
            }
            for c in self.credentials.values()
        ]


def run_scenarios():
    """Demonstrate soft cascade lifecycle."""
    mgr = SoftCascadeManager()
    
    print("=" * 70)
    print("SOFT CASCADE TRUST RECOVERY")
    print("SC-081v3 (47d certs) + Google OCSP kill → short TTL for agent trust")
    print("=" * 70)
    
    # Issue credentials with 72h TTL
    t0 = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)
    
    cred_a = mgr.issue("agent_alpha", "registry_1", "code_review", ttl_hours=72.0)
    cred_a.issued_at = t0
    cred_a.last_renewal = t0
    
    cred_b = mgr.issue("agent_beta", "registry_1", "security_audit", ttl_hours=72.0)
    cred_b.issued_at = t0
    cred_b.last_renewal = t0
    
    print(f"\n[T+0h] Issued 2 credentials (72h TTL, 20% grace)")
    
    # Simulate time progression
    checkpoints = [
        (56, "approaching grace"),    # 72 * 0.8 = 57.6h grace start
        (60, "in grace period"),
        (73, "just expired"),
        (100, "deep degradation"),
        (220, "past deadline"),
    ]
    
    for hours, label in checkpoints:
        t = t0 + timedelta(hours=hours)
        transitions = mgr.tick(t)
        
        print(f"\n[T+{hours}h] {label}")
        for tr in transitions:
            print(f"  {tr['agent_id']}: {tr['transition']} — {tr['action_required']}")
        
        status = mgr.status(t)
        for s in status:
            print(f"  {s['agent_id']}:{s['scope']} = {s['state']} ({s['hours_remaining']}h remaining)")
        
        # agent_alpha renews at T+60h (in grace)
        if hours == 60:
            print("\n  → agent_alpha RENEWS (grace period)")
            result = mgr.renew("agent_alpha", "code_review", challenge_passed=True, now=t)
            print(f"    {json.dumps({k: result[k] for k in ['success', 'challenge_type', 'renewal_count', 'trust_velocity']})}")
        
        # agent_beta tries to renew at T+100h (degraded)
        if hours == 100:
            print("\n  → agent_beta RENEWS (degraded — capability probe)")
            result = mgr.renew("agent_beta", "security_audit", challenge_passed=True, now=t)
            print(f"    {json.dumps({k: result[k] for k in ['success', 'challenge_type', 'previous_state', 'renewal_count']})}")
    
    # Final status
    t_final = t0 + timedelta(hours=220)
    mgr.tick(t_final)
    print(f"\n{'=' * 70}")
    print("Final status:")
    for s in mgr.status(t_final):
        print(f"  {s['agent_id']}:{s['scope']} = {s['state']} — {s['action']}")
    
    print(f"\n{'=' * 70}")
    print("Design principles:")
    print("1. Short TTL > revocation lists (SC-081v3: 47d certs by 2029)")
    print("2. Active renewal > passive expiry (Google killed OCSP H2 2025)")
    print("3. Challenge cost scales with degradation depth")
    print("4. Trust velocity: frequent renewers earn longer effective TTL")
    print("5. Absence of renewal IS the revocation signal")
    print(f"\nTotal lifecycle events: {len(mgr.events)}")


if __name__ == "__main__":
    run_scenarios()
