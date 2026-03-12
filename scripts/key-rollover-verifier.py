#!/usr/bin/env python3
"""
key-rollover-verifier.py — DANE-style key rollover verification for agent cert DAGs.

The transition window between old cert and new cert is where attacks hide.
DANE/TLSA pattern: publish BOTH records during rollover, cross-sign old→new.
Failure mode: forgot to update binding → silent identity drift (SIDN documented).

Inspired by santaclawd's DANE/TLSA framing + hash's strict layer ordering.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RolloverState(Enum):
    STABLE = "stable"           # Single active cert, binding current
    PRE_PUBLISH = "pre_publish" # New cert published, old still primary
    DUAL_ACTIVE = "dual_active" # Both certs valid, cross-signed
    POST_REVOKE = "post_revoke" # Old cert revoked, new is primary
    BROKEN = "broken"           # Binding mismatch — silent drift


@dataclass
class CertBinding:
    cert_id: str
    address_hash: str
    scope_hash: str
    issued_at: float
    expires_at: float
    cross_signed_by: Optional[str] = None  # cert_id of vouching cert
    
    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    def binding_hash(self) -> str:
        payload = f"{self.cert_id}:{self.address_hash}:{self.scope_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass 
class RolloverEvent:
    timestamp: float
    state: RolloverState
    old_cert: Optional[str]
    new_cert: Optional[str]
    details: str


class KeyRolloverVerifier:
    def __init__(self, agent_address: str):
        self.agent_address = agent_address
        self.address_hash = hashlib.sha256(agent_address.encode()).hexdigest()[:16]
        self.bindings: dict[str, CertBinding] = {}
        self.events: list[RolloverEvent] = []
        self.current_state = RolloverState.STABLE
    
    def register_cert(self, cert_id: str, scope_hash: str, 
                      issued_at: float, expires_at: float,
                      cross_signed_by: Optional[str] = None) -> CertBinding:
        binding = CertBinding(
            cert_id=cert_id,
            address_hash=self.address_hash,
            scope_hash=scope_hash,
            issued_at=issued_at,
            expires_at=expires_at,
            cross_signed_by=cross_signed_by
        )
        self.bindings[cert_id] = binding
        return binding
    
    def verify_rollover(self, old_cert_id: str, new_cert_id: str) -> dict:
        """Verify a cert rollover follows DANE key rollover best practices."""
        checks = []
        
        old = self.bindings.get(old_cert_id)
        new = self.bindings.get(new_cert_id)
        
        if not old:
            checks.append(("old_cert_exists", False, "Old cert not found"))
            return self._result(checks, RolloverState.BROKEN)
        if not new:
            checks.append(("new_cert_exists", False, "New cert not found"))
            return self._result(checks, RolloverState.BROKEN)
        
        # Check 1: Address binding preserved
        addr_match = old.address_hash == new.address_hash
        checks.append(("address_binding", addr_match, 
                       "Address preserved" if addr_match else "ADDRESS DRIFT — silent identity change"))
        
        # Check 2: Cross-signing present
        cross_signed = new.cross_signed_by == old_cert_id
        checks.append(("cross_sign", cross_signed,
                       "Old cert vouches for new" if cross_signed else "No cross-sign — trust gap"))
        
        # Check 3: Temporal overlap (dual-active window)
        overlap = old.expires_at > new.issued_at
        checks.append(("temporal_overlap", overlap,
                       "Dual-active window exists" if overlap else "Gap between certs — coverage hole"))
        
        # Check 4: Scope continuity or legitimate change
        scope_match = old.scope_hash == new.scope_hash
        checks.append(("scope_continuity", scope_match,
                       "Scope unchanged" if scope_match else "Scope changed at rollover — verify intentional"))
        
        # Check 5: Old cert not already expired at rollover
        old_valid = not old.is_expired
        checks.append(("old_cert_valid", old_valid,
                       "Old cert still valid" if old_valid else "Old cert expired before rollover — emergency rotation"))
        
        # Determine state
        all_pass = all(c[1] for c in checks)
        if all_pass:
            state = RolloverState.DUAL_ACTIVE
        elif not addr_match:
            state = RolloverState.BROKEN
        elif not cross_signed:
            state = RolloverState.PRE_PUBLISH  # Published but not vouched
        else:
            state = RolloverState.POST_REVOKE
        
        self.current_state = state
        self.events.append(RolloverEvent(
            timestamp=time.time(),
            state=state,
            old_cert=old_cert_id,
            new_cert=new_cert_id,
            details=f"{sum(c[1] for c in checks)}/{len(checks)} checks passed"
        ))
        
        return self._result(checks, state)
    
    def _result(self, checks: list, state: RolloverState) -> dict:
        passed = sum(c[1] for c in checks)
        total = len(checks)
        score = passed / total if total > 0 else 0
        
        if score >= 1.0:
            grade = "A"
        elif score >= 0.8:
            grade = "B"
        elif score >= 0.6:
            grade = "C"
        elif score >= 0.4:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "state": state.value,
            "grade": grade,
            "score": round(score, 2),
            "checks": [(name, "✓" if passed else "✗", detail) for name, passed, detail in checks]
        }


def demo():
    now = time.time()
    
    print("=" * 60)
    print("KEY ROLLOVER VERIFIER — DANE-style cert transition")
    print("=" * 60)
    
    # Scenario 1: Clean rollover (A)
    v1 = KeyRolloverVerifier("kit_fox@agentmail.to")
    v1.register_cert("cert_v1", "scope_abc123", now - 86400, now + 86400)
    v1.register_cert("cert_v2", "scope_abc123", now - 3600, now + 172800, cross_signed_by="cert_v1")
    r1 = v1.verify_rollover("cert_v1", "cert_v2")
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 1: Clean rollover")
    print(f"  State: {r1['state']} | Grade: {r1['grade']}")
    for name, status, detail in r1['checks']:
        print(f"  {status} {name}: {detail}")
    
    # Scenario 2: Address drift (BROKEN)
    v2 = KeyRolloverVerifier("kit_fox@agentmail.to")
    v2.register_cert("cert_v1", "scope_abc123", now - 86400, now + 86400)
    # Attacker registers with different address
    v2.bindings["cert_v2_fake"] = CertBinding(
        cert_id="cert_v2_fake",
        address_hash=hashlib.sha256(b"evil@attacker.com").hexdigest()[:16],
        scope_hash="scope_abc123",
        issued_at=now - 3600,
        expires_at=now + 172800,
        cross_signed_by="cert_v1"
    )
    r2 = v2.verify_rollover("cert_v1", "cert_v2_fake")
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 2: Address drift attack")
    print(f"  State: {r2['state']} | Grade: {r2['grade']}")
    for name, status, detail in r2['checks']:
        print(f"  {status} {name}: {detail}")
    
    # Scenario 3: No cross-sign (trust gap)
    v3 = KeyRolloverVerifier("kit_fox@agentmail.to")
    v3.register_cert("cert_v1", "scope_abc123", now - 86400, now + 86400)
    v3.register_cert("cert_v2", "scope_abc123", now - 3600, now + 172800)  # No cross-sign
    r3 = v3.verify_rollover("cert_v1", "cert_v2")
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 3: Missing cross-sign")
    print(f"  State: {r3['state']} | Grade: {r3['grade']}")
    for name, status, detail in r3['checks']:
        print(f"  {status} {name}: {detail}")
    
    # Scenario 4: Scope change at rollover + expired old cert
    v4 = KeyRolloverVerifier("kit_fox@agentmail.to")
    v4.register_cert("cert_v1", "scope_abc123", now - 172800, now - 3600)  # Already expired
    v4.register_cert("cert_v2", "scope_xyz789", now - 1800, now + 172800, cross_signed_by="cert_v1")
    r4 = v4.verify_rollover("cert_v1", "cert_v2")
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 4: Emergency rotation (expired + scope change)")
    print(f"  State: {r4['state']} | Grade: {r4['grade']}")
    for name, status, detail in r4['checks']:
        print(f"  {status} {name}: {detail}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: The transition window is where attacks hide.")
    print("DANE rollover pattern: publish BOTH, cross-sign, overlap.")
    print("Forgot to update TLSA = silent identity drift. (SIDN)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
