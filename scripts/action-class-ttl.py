#!/usr/bin/env python3
"""
action-class-ttl.py — ATF action class TTL enforcement.

Maps TLS certificate validation levels to agent trust action classes.
Prevents TTL-laundering: accumulating low-stake history to borrow
high-stake trust.

Action classes (minimum set):
  READ     — No state change.        TTL floor: 168h (7d)
  WRITE    — State change.           TTL floor: 72h  (3d)  
  ATTEST   — Signing for others.     TTL floor: 48h  (2d)
  TRANSFER — Irreversible value.     TTL floor: 24h  (1d)

Probe failure semantics (per Langley/Chrome 2014, LE 2025):
  - Hard-fail. No retry budget. No grace window.
  - Failed probe = SUSPEND (can re-initiate full challenge)
  - Soft-fail is "completely useless" (attacker blocks probe and wins)

Sources:
  - Adam Langley, "No, don't enable revocation checking" (2014)
  - Ivan Ristić, "The Slow Death of OCSP" (Feisty Duck, Jan 2025)
  - Let's Encrypt OCSP removal (Dec 2024, effective May 2025)
  - Let's Encrypt 6-day certs (2025), Apple 47→45 day proposal
  - CA/Browser Forum: OCSP optional, CRL mandatory (Aug 2023)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class ActionClass(Enum):
    """Trust action classes with increasing irreversibility."""
    READ = "READ"           # Query, observe, fetch
    WRITE = "WRITE"         # Create, update, delete
    ATTEST = "ATTEST"       # Sign attestation for another agent
    TRANSFER = "TRANSFER"   # Irreversible value movement


# TTL floors per action class (hours)
TTL_FLOORS: dict[ActionClass, int] = {
    ActionClass.READ: 168,      # 7 days — low risk
    ActionClass.WRITE: 72,      # 3 days — moderate risk
    ActionClass.ATTEST: 48,     # 2 days — high risk (signing for others)
    ActionClass.TRANSFER: 24,   # 1 day — maximum risk (irreversible)
}

# Grace period cap for re-attestation (2× TTL, max 168h)
GRACE_CAP_HOURS = 168


class TrustStatus(Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"     # Failed probe — can re-initiate
    EXPIRED = "EXPIRED"         # TTL elapsed — must re-earn
    REVOKED = "REVOKED"         # Explicit revocation — permanent


@dataclass
class ActionClassTrust:
    """Trust credential for a specific action class."""
    agent_id: str
    action_class: ActionClass
    issued_at: datetime
    ttl_hours: int
    status: TrustStatus = TrustStatus.ACTIVE
    probe_history: list[dict] = field(default_factory=list)
    
    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(hours=self.ttl_hours)
    
    @property
    def grace_deadline(self) -> datetime:
        """Grace window = 2× TTL, capped at 168h."""
        grace_hours = min(self.ttl_hours * 2, GRACE_CAP_HOURS)
        return self.expires_at + timedelta(hours=grace_hours)
    
    def is_valid(self, at: Optional[datetime] = None) -> bool:
        at = at or datetime.now(timezone.utc)
        return self.status == TrustStatus.ACTIVE and at < self.expires_at
    
    def is_in_grace(self, at: Optional[datetime] = None) -> bool:
        at = at or datetime.now(timezone.utc)
        return self.expires_at <= at < self.grace_deadline


class ActionClassEnforcer:
    """
    Enforce action class TTL policies.
    
    Key principles:
    1. Each action class has independent trust — READ history never 
       subsidizes TRANSFER trust (anti-TTL-laundering)
    2. Hard-fail on probe failure — no retry budget, no grace
    3. Short-lived by default — absence of renewal IS revocation
    4. SUSPEND ≠ REVOKE — suspended agents can re-initiate challenge
    """
    
    def __init__(self):
        self.credentials: dict[tuple[str, ActionClass], ActionClassTrust] = {}
        self.audit_log: list[dict] = []
    
    def issue(self, agent_id: str, action_class: ActionClass, 
              ttl_hours: Optional[int] = None) -> ActionClassTrust:
        """Issue trust credential for an action class."""
        floor = TTL_FLOORS[action_class]
        ttl = max(ttl_hours or floor, floor)  # Can't go below floor
        
        cred = ActionClassTrust(
            agent_id=agent_id,
            action_class=action_class,
            issued_at=datetime.now(timezone.utc),
            ttl_hours=ttl,
        )
        self.credentials[(agent_id, action_class)] = cred
        self._log("ISSUE", agent_id, action_class, f"TTL={ttl}h (floor={floor}h)")
        return cred
    
    def check(self, agent_id: str, action_class: ActionClass,
              at: Optional[datetime] = None) -> dict:
        """Check if agent has valid trust for an action class."""
        key = (agent_id, action_class)
        cred = self.credentials.get(key)
        
        if cred is None:
            return {"allowed": False, "reason": "NO_CREDENTIAL", "action": "CHALLENGE_REQUIRED"}
        
        if cred.status == TrustStatus.REVOKED:
            return {"allowed": False, "reason": "REVOKED", "action": "DENIED"}
        
        if cred.status == TrustStatus.SUSPENDED:
            return {"allowed": False, "reason": "SUSPENDED", "action": "RECHALLENGE_REQUIRED"}
        
        if cred.is_valid(at):
            remaining = (cred.expires_at - (at or datetime.now(timezone.utc))).total_seconds() / 3600
            return {"allowed": True, "reason": "ACTIVE", "remaining_hours": round(remaining, 1)}
        
        if cred.is_in_grace(at):
            remaining = (cred.grace_deadline - (at or datetime.now(timezone.utc))).total_seconds() / 3600
            return {
                "allowed": False, 
                "reason": "EXPIRED_IN_GRACE",
                "action": "RENEWAL_REQUIRED",
                "grace_remaining_hours": round(remaining, 1),
            }
        
        return {"allowed": False, "reason": "EXPIRED", "action": "FULL_CHALLENGE_REQUIRED"}
    
    def probe(self, agent_id: str, action_class: ActionClass, passed: bool) -> dict:
        """
        Record probe result. Hard-fail semantics.
        
        Per Langley (2014): soft-fail is "completely useless."
        Failed probe = SUSPEND. No retry budget. No grace.
        Agent can re-initiate full challenge sequence.
        """
        key = (agent_id, action_class)
        cred = self.credentials.get(key)
        
        if cred is None:
            return {"error": "NO_CREDENTIAL"}
        
        probe_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
        }
        cred.probe_history.append(probe_record)
        
        if passed:
            self._log("PROBE_PASS", agent_id, action_class, "")
            return {"status": "PASS", "credential_status": cred.status.value}
        
        # HARD FAIL — immediate suspend
        cred.status = TrustStatus.SUSPENDED
        self._log("PROBE_FAIL", agent_id, action_class, 
                  "HARD_FAIL → SUSPENDED. No retry budget.")
        return {
            "status": "FAIL",
            "credential_status": "SUSPENDED",
            "action": "Must re-initiate full challenge sequence",
            "note": "Langley 2014: soft-fail is completely useless",
        }
    
    def detect_ttl_laundering(self, agent_id: str, 
                               target_class: ActionClass) -> dict:
        """
        Detect TTL-laundering: agent accumulates low-stake history
        to borrow trust for high-stake actions.
        
        Pattern: 1000 READs → 1 TRANSFER at borrowed trust level.
        Prevention: action classes are INDEPENDENT trust budgets.
        """
        # Check if agent has high-volume low-stake history
        # but no credential for target class
        low_stake_classes = [c for c in ActionClass 
                           if TTL_FLOORS[c] > TTL_FLOORS[target_class]]
        
        has_low_stake = any(
            self.credentials.get((agent_id, c)) is not None 
            and self.credentials[(agent_id, c)].is_valid()
            for c in low_stake_classes
        )
        
        has_target = (
            self.credentials.get((agent_id, target_class)) is not None
            and self.credentials[(agent_id, target_class)].is_valid()
        )
        
        if has_low_stake and not has_target:
            return {
                "laundering_attempt": True,
                "agent_id": agent_id,
                "target_class": target_class.value,
                "message": f"Agent has low-stake credentials but no {target_class.value} credential. "
                          f"Each action class requires independent challenge. "
                          f"READ history does not subsidize TRANSFER trust.",
            }
        
        return {"laundering_attempt": False}
    
    def _log(self, event: str, agent_id: str, action_class: ActionClass, detail: str):
        self.audit_log.append({
            "event": event,
            "agent_id": agent_id,
            "action_class": action_class.value,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def run_demo():
    """Demonstrate action class TTL enforcement."""
    enforcer = ActionClassEnforcer()
    
    print("=" * 65)
    print("ACTION CLASS TTL ENFORCEMENT")
    print("Anti-TTL-laundering + hard-fail probe semantics")
    print("=" * 65)
    
    # 1. Issue credentials
    print("\n--- Issue credentials ---")
    for ac in ActionClass:
        cred = enforcer.issue("agent_alpha", ac)
        print(f"  {ac.value:10s} TTL={cred.ttl_hours}h  expires={cred.expires_at.strftime('%Y-%m-%d %H:%M')}")
    
    # 2. Check valid access
    print("\n--- Check access (all fresh) ---")
    for ac in ActionClass:
        result = enforcer.check("agent_alpha", ac)
        print(f"  {ac.value:10s} allowed={result['allowed']}  remaining={result.get('remaining_hours', 'N/A')}h")
    
    # 3. Probe failure — hard fail
    print("\n--- Probe failure (TRANSFER) ---")
    result = enforcer.probe("agent_alpha", ActionClass.TRANSFER, passed=False)
    print(f"  Status: {result['status']}")
    print(f"  Credential: {result['credential_status']}")
    print(f"  Action: {result['action']}")
    print(f"  Note: {result['note']}")
    
    # 4. Verify TRANSFER is now blocked
    print("\n--- Check TRANSFER after probe failure ---")
    result = enforcer.check("agent_alpha", ActionClass.TRANSFER)
    print(f"  Allowed: {result['allowed']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Action: {result['action']}")
    
    # 5. Other action classes still work
    print("\n--- Other classes unaffected ---")
    for ac in [ActionClass.READ, ActionClass.WRITE, ActionClass.ATTEST]:
        result = enforcer.check("agent_alpha", ac)
        print(f"  {ac.value:10s} allowed={result['allowed']}")
    
    # 6. TTL laundering detection
    print("\n--- TTL laundering detection ---")
    enforcer.issue("agent_beta", ActionClass.READ)
    enforcer.issue("agent_beta", ActionClass.WRITE)
    # agent_beta tries TRANSFER without earning TRANSFER credential
    result = enforcer.detect_ttl_laundering("agent_beta", ActionClass.TRANSFER)
    print(f"  Laundering attempt: {result['laundering_attempt']}")
    if result['laundering_attempt']:
        print(f"  Message: {result['message']}")
    
    # 7. Expired credential check
    print("\n--- Expired credential (simulated) ---")
    past = datetime.now(timezone.utc) - timedelta(hours=200)
    cred = ActionClassTrust("agent_gamma", ActionClass.READ, past, 168)
    enforcer.credentials[("agent_gamma", ActionClass.READ)] = cred
    result = enforcer.check("agent_gamma", ActionClass.READ)
    print(f"  Status: {result['reason']}")
    print(f"  Action: {result['action']}")
    
    # Summary
    print(f"\n{'=' * 65}")
    print("TTL floors: READ=168h, WRITE=72h, ATTEST=48h, TRANSFER=24h")
    print("Probe failure: HARD-FAIL → SUSPEND (no retry budget)")
    print("Each class = independent trust budget (anti-laundering)")
    print("Short-lived by default: non-renewal IS revocation")
    print("Sources: Langley 2014, LE OCSP removal 2025, CA/B Forum 2023")


if __name__ == "__main__":
    run_demo()
