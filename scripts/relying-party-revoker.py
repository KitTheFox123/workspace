#!/usr/bin/env python3
"""
relying-party-revoker.py — Relying-party-controlled trust revocation for ATF.

PKI spent 30 years failing to ship relying-party revocation:
- CRL: issuer decides, relying party downloads giant list (RFC 5280)
- OCSP: issuer decides, relying party makes blocking request (RFC 2560)
- Both add central choke points to a beautifully distributed system

Passive revocation (Smallstep, May 2025): short-lived certs die young.
No CRL needed. Automation makes short lifetimes feasible.

ATF implementation: TWO revocation layers:
1. PASSIVE: receipt TTL = passive revocation. Trust expires unless renewed.
   No action needed. This is the default. (Short-lived cert parallel.)
2. ACTIVE: LOCAL_DISTRUST = relying party lowers trust unilaterally.
   No CA/registry permission needed. Counterparty controls own trust store.
   (What OCSP/CRL should have been.)

Key principle (funwolf): "the missing primitive email never solved:
revocation that the RELYING PARTY controls."

Sources:
- Smallstep "Good certificates die young" (May 2025)
- RFC 5280 (CRL), RFC 2560/6960 (OCSP)
- RFC 6962 (CT — transparency without issuer control)
- funwolf: relying-party revocation as missing primitive
- santaclawd: LOCAL_DISTRUST receipt design
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta


class RevocationType(Enum):
    PASSIVE = "passive"       # TTL expiry — no action needed
    LOCAL_DISTRUST = "local_distrust"   # Relying party actively revokes
    SUSPENSION = "suspension"  # Temporary, reversible
    EMERGENCY = "emergency"    # Immediate, all counterparties notified


class TrustState(Enum):
    ACTIVE = "active"
    STALE = "stale"          # Past TTL but in grace period
    EXPIRED = "expired"       # Passively revoked (TTL)
    DISTRUSTED = "distrusted" # Actively revoked by relying party
    SUSPENDED = "suspended"   # Temporarily suspended


@dataclass
class TrustEntry:
    """A trust relationship from relying party's perspective."""
    counterparty_id: str
    trust_score: float          # 0.0 - 1.0
    receipts_count: int
    last_receipt: datetime
    ttl_days: int = 30          # Passive revocation: expires after TTL
    state: TrustState = TrustState.ACTIVE
    local_distrust: Optional[dict] = None  # Active revocation metadata
    history: list = field(default_factory=list)

    @property
    def expires_at(self) -> datetime:
        return self.last_receipt + timedelta(days=self.ttl_days)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at


class RelyingPartyRevoker:
    """
    Relying-party-controlled trust revocation.
    
    Unlike PKI where the CA controls revocation (CRL/OCSP),
    here the RELYING PARTY controls its own trust store.
    
    Two mechanisms:
    1. Passive: TTL expiry (short-lived cert model)
    2. Active: LOCAL_DISTRUST (what OCSP should have been)
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.trust_store: dict[str, TrustEntry] = {}
        self.revocation_log: list[dict] = []

    def add_trust(self, counterparty_id: str, score: float, receipts: int,
                  ttl_days: int = 30) -> TrustEntry:
        """Add or update trust entry."""
        entry = TrustEntry(
            counterparty_id=counterparty_id,
            trust_score=score,
            receipts_count=receipts,
            last_receipt=datetime.now(timezone.utc),
            ttl_days=ttl_days,
        )
        self.trust_store[counterparty_id] = entry
        return entry

    def check_passive_revocation(self) -> list[str]:
        """
        Passive revocation: check TTL expiry on all entries.
        Short-lived cert model: trust dies young unless renewed.
        """
        revoked = []
        now = datetime.now(timezone.utc)
        
        for cid, entry in self.trust_store.items():
            if entry.state in (TrustState.DISTRUSTED, TrustState.SUSPENDED):
                continue  # Already actively revoked
            
            if now > entry.expires_at:
                old_state = entry.state
                entry.state = TrustState.EXPIRED
                revoked.append(cid)
                self._log_revocation(cid, RevocationType.PASSIVE, 
                    f"TTL expired ({entry.ttl_days}d). Last receipt: {entry.last_receipt.isoformat()}")
                entry.history.append({
                    "action": "passive_revocation",
                    "old_state": old_state.value,
                    "timestamp": now.isoformat(),
                })
            elif now > entry.expires_at - timedelta(days=entry.ttl_days * 0.2):
                # Grace period: 20% of TTL before expiry
                if entry.state == TrustState.ACTIVE:
                    entry.state = TrustState.STALE
                    entry.history.append({
                        "action": "stale_warning",
                        "timestamp": now.isoformat(),
                    })
        
        return revoked

    def local_distrust(self, counterparty_id: str, reason: str, 
                       evidence: Optional[list[str]] = None) -> dict:
        """
        Active revocation: relying party unilaterally lowers trust.
        No CA/registry permission needed. This is what OCSP should have been.
        
        The relying party IS the authority over its own trust decisions.
        """
        entry = self.trust_store.get(counterparty_id)
        if not entry:
            return {"error": "no trust entry for counterparty"}
        
        old_score = entry.trust_score
        old_state = entry.state
        
        entry.trust_score = 0.0
        entry.state = TrustState.DISTRUSTED
        entry.local_distrust = {
            "reason": reason,
            "evidence": evidence or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "previous_score": old_score,
        }
        
        entry.history.append({
            "action": "local_distrust",
            "reason": reason,
            "old_score": old_score,
            "old_state": old_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        receipt = {
            "type": "LOCAL_DISTRUST",
            "issuer": self.agent_id,
            "subject": counterparty_id,
            "reason": reason,
            "evidence": evidence or [],
            "previous_score": old_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        self._log_revocation(counterparty_id, RevocationType.LOCAL_DISTRUST, reason)
        return receipt

    def suspend(self, counterparty_id: str, reason: str, 
                duration_days: int = 7) -> dict:
        """Temporary suspension — reversible, unlike LOCAL_DISTRUST."""
        entry = self.trust_store.get(counterparty_id)
        if not entry:
            return {"error": "no trust entry"}
        
        old_state = entry.state
        entry.state = TrustState.SUSPENDED
        entry.history.append({
            "action": "suspension",
            "reason": reason,
            "duration_days": duration_days,
            "old_state": old_state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        self._log_revocation(counterparty_id, RevocationType.SUSPENSION, reason)
        return {"status": "suspended", "duration_days": duration_days}

    def reinstate(self, counterparty_id: str, new_score: Optional[float] = None) -> dict:
        """Reinstate a suspended (not distrusted) entry."""
        entry = self.trust_store.get(counterparty_id)
        if not entry:
            return {"error": "no trust entry"}
        
        if entry.state == TrustState.DISTRUSTED:
            return {"error": "LOCAL_DISTRUST is permanent. Create new trust entry instead."}
        
        if entry.state != TrustState.SUSPENDED:
            return {"error": f"not suspended (state={entry.state.value})"}
        
        entry.state = TrustState.ACTIVE
        if new_score is not None:
            entry.trust_score = new_score
        entry.last_receipt = datetime.now(timezone.utc)  # Reset TTL
        
        entry.history.append({
            "action": "reinstatement",
            "new_score": entry.trust_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        return {"status": "reinstated", "score": entry.trust_score}

    def get_trust(self, counterparty_id: str) -> Optional[dict]:
        """Query current trust state for a counterparty."""
        entry = self.trust_store.get(counterparty_id)
        if not entry:
            return None
        
        return {
            "counterparty": entry.counterparty_id,
            "score": entry.trust_score,
            "state": entry.state.value,
            "receipts": entry.receipts_count,
            "ttl_days": entry.ttl_days,
            "expires_at": entry.expires_at.isoformat(),
            "is_expired": entry.is_expired,
            "local_distrust": entry.local_distrust,
            "history_count": len(entry.history),
        }

    def _log_revocation(self, counterparty_id: str, rev_type: RevocationType, reason: str):
        self.revocation_log.append({
            "counterparty": counterparty_id,
            "type": rev_type.value,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


def run_scenarios():
    """Demonstrate relying-party revocation."""
    print("=" * 70)
    print("RELYING-PARTY TRUST REVOCATION")
    print("PKI failed: CRL/OCSP = issuer controls. ATF: relying party controls.")
    print("=" * 70)
    
    rp = RelyingPartyRevoker("agent_kit")
    all_pass = True
    
    # Scenario 1: Passive revocation via TTL
    print("\n✓ Scenario 1: Passive revocation (short-lived cert model)")
    entry = rp.add_trust("agent_alice", score=0.85, receipts=30, ttl_days=30)
    # Simulate expiry by backdating
    entry.last_receipt = datetime.now(timezone.utc) - timedelta(days=31)
    revoked = rp.check_passive_revocation()
    assert "agent_alice" in revoked, "Should be passively revoked"
    assert entry.state == TrustState.EXPIRED
    print(f"  agent_alice: TTL expired. State: {entry.state.value}")
    print(f"  No CA needed. Trust dies young unless renewed.")
    
    # Scenario 2: Active LOCAL_DISTRUST
    print("\n✓ Scenario 2: LOCAL_DISTRUST (what OCSP should have been)")
    rp.add_trust("agent_bob", score=0.90, receipts=50, ttl_days=30)
    receipt = rp.local_distrust("agent_bob", 
        reason="delivery_failure_pattern",
        evidence=["receipt_123: timeout", "receipt_456: wrong_format"])
    assert receipt["type"] == "LOCAL_DISTRUST"
    assert receipt["previous_score"] == 0.90
    bob = rp.get_trust("agent_bob")
    assert bob["state"] == "distrusted"
    assert bob["score"] == 0.0
    print(f"  agent_bob: score 0.90 → 0.00. State: distrusted")
    print(f"  No registry permission needed. Relying party IS the authority.")
    
    # Scenario 3: Suspension (reversible)
    print("\n✓ Scenario 3: Suspension (temporary, reversible)")
    rp.add_trust("agent_carol", score=0.75, receipts=20, ttl_days=30)
    rp.suspend("agent_carol", reason="under_investigation", duration_days=7)
    carol = rp.get_trust("agent_carol")
    assert carol["state"] == "suspended"
    result = rp.reinstate("agent_carol", new_score=0.60)
    assert result["status"] == "reinstated"
    carol = rp.get_trust("agent_carol")
    assert carol["state"] == "active"
    print(f"  agent_carol: suspended → reinstated at 0.60")
    print(f"  Suspension = temporary investigation. Not permanent distrust.")
    
    # Scenario 4: LOCAL_DISTRUST is permanent
    print("\n✓ Scenario 4: LOCAL_DISTRUST is permanent (no reinstatement)")
    result = rp.reinstate("agent_bob")
    assert "error" in result
    print(f"  agent_bob reinstate attempt: {result['error']}")
    print(f"  Permanent = burned bridge. Must create new trust relationship.")
    
    # Scenario 5: Stale warning before expiry
    print("\n✓ Scenario 5: Stale warning (20% TTL grace period)")
    entry = rp.add_trust("agent_dave", score=0.80, receipts=15, ttl_days=30)
    entry.last_receipt = datetime.now(timezone.utc) - timedelta(days=25)  # 5 days left
    rp.check_passive_revocation()
    assert entry.state == TrustState.STALE
    print(f"  agent_dave: 5 days remaining → STALE warning")
    print(f"  RFC 8767 serve-stale model: degrade gracefully before hard expiry.")
    
    print(f"\n{'=' * 70}")
    print(f"5/5 scenarios passed")
    print(f"\nRevocation log: {len(rp.revocation_log)} entries")
    for log in rp.revocation_log:
        print(f"  [{log['type']}] {log['counterparty']}: {log['reason']}")
    
    print(f"\nKey insight: PKI revocation failed because the ISSUER controls it.")
    print(f"ATF revocation works because the RELYING PARTY controls it.")
    print(f"Passive (TTL) + Active (LOCAL_DISTRUST) = complete coverage.")
    print(f"No central choke point. No CRL downloads. No OCSP blocking calls.")
    
    return True


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
