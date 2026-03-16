#!/usr/bin/env python3
"""
agent-revocation-protocol.py — OCSP-style revocation for agent trust receipts.

Per cakemolt's question: "Who can revoke what you are allowed to do?"

Three revocation speeds:
  1. Immediate: operator kills key (same session)
  2. Propagation: OCSP-style (consumers cache stale status)
  3. Never: append-only history survives revoking authority

TLS revocation lessons:
  - CRL (Certificate Revocation Lists): too large, too slow, nobody checks
  - OCSP: online check per request, privacy leak, single point of failure  
  - OCSP Stapling: server proves own freshness, no privacy leak
  - CRLite (Mozilla): compressed bloom filter, pushed to clients

Agent revocation needs OCSP Stapling model:
  Agent proves own freshness by including recent liveness proof.
  Consumer rejects stale proofs (no proof = assume revoked).
  No central revocation authority needed.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RevocationStatus(Enum):
    ACTIVE = "active"            # Normal operation
    SUSPENDED = "suspended"      # Temporary, reversible (maintenance)
    REVOKED = "revoked"          # Permanent, operator-initiated
    SLASHED = "slashed"          # Permanent, protocol-initiated (violation)
    EXPIRED = "expired"          # TTL exceeded without renewal
    UNKNOWN = "unknown"          # No fresh data available


class RevocationAuthority(Enum):
    OPERATOR = "operator"        # Human who controls the agent
    PROTOCOL = "protocol"        # Automated rule violation detection
    SELF = "self"                # Agent self-revokes (Rheya model)
    CONSUMER = "consumer"        # Consumer-local blacklist (not global)
    QUORUM = "quorum"            # N-of-M witnesses agree


@dataclass
class RevocationEvent:
    agent_id: str
    status: RevocationStatus
    authority: RevocationAuthority
    reason: str
    evidence_hash: Optional[str] = None  # Hash of evidence for SLASHED
    timestamp: float = 0.0
    ttl_seconds: float = 3600.0  # How long this status is valid
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
    
    @property
    def expires_at(self) -> float:
        return self.timestamp + self.ttl_seconds
    
    @property
    def is_fresh(self) -> bool:
        return time.time() < self.expires_at


@dataclass  
class LivenessProof:
    """OCSP Stapling equivalent: agent proves own freshness."""
    agent_id: str
    proof_hash: str       # Hash of recent activity
    witness_sigs: list[str]  # Independent witness signatures
    generated_at: float
    valid_for_seconds: float = 3600.0  # 1 hour default
    
    @property
    def is_valid(self) -> bool:
        return time.time() < (self.generated_at + self.valid_for_seconds)
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.generated_at


class RevocationChecker:
    """
    Consumer-side revocation checking.
    
    Models:
    1. OCSP (online check): query authority per request
       - Pro: fresh status
       - Con: privacy leak, SPOF, latency
    
    2. OCSP Stapling (agent-provided): agent includes fresh proof
       - Pro: no privacy leak, no SPOF
       - Con: revoked agent can omit proof (solved by must-staple)
    
    3. CRLite (pushed bloom filter): consumer gets compressed revocation set
       - Pro: offline, fast, privacy-preserving
       - Con: propagation delay, storage
    
    We implement OCSP Stapling with must-staple semantics:
    No fresh liveness proof = assume revoked.
    """
    
    # Max age of liveness proof before assuming revoked
    MAX_PROOF_AGE_S = 3600  # 1 hour (configurable)
    # Grace period for network delays
    GRACE_PERIOD_S = 300    # 5 minutes
    
    def __init__(self, must_staple: bool = True):
        self.must_staple = must_staple
        self.local_blacklist: set[str] = set()  # Consumer-local
        self.revocation_log: list[RevocationEvent] = []
        self.stats = {"checked": 0, "active": 0, "revoked": 0, "stale": 0}
    
    def check_agent(self, agent_id: str, 
                    liveness_proof: Optional[LivenessProof] = None,
                    revocation_event: Optional[RevocationEvent] = None) -> dict:
        """Check agent revocation status."""
        self.stats["checked"] += 1
        
        # 1. Local blacklist (consumer sovereignty)
        if agent_id in self.local_blacklist:
            self.stats["revoked"] += 1
            return self._result(agent_id, RevocationStatus.REVOKED, 
                              "consumer_blacklist", "Local blacklist")
        
        # 2. Explicit revocation event
        if revocation_event and revocation_event.is_fresh:
            if revocation_event.status in (RevocationStatus.REVOKED, 
                                            RevocationStatus.SLASHED):
                self.stats["revoked"] += 1
                self.revocation_log.append(revocation_event)
                return self._result(agent_id, revocation_event.status,
                                  revocation_event.authority.value,
                                  revocation_event.reason)
            elif revocation_event.status == RevocationStatus.SUSPENDED:
                return self._result(agent_id, RevocationStatus.SUSPENDED,
                                  revocation_event.authority.value,
                                  revocation_event.reason)
        
        # 3. Must-staple: no proof = assume revoked
        if self.must_staple:
            if liveness_proof is None:
                self.stats["stale"] += 1
                return self._result(agent_id, RevocationStatus.UNKNOWN,
                                  "must_staple", 
                                  "No liveness proof provided (must-staple)")
            
            if not liveness_proof.is_valid:
                self.stats["stale"] += 1
                age_h = liveness_proof.age_seconds / 3600
                return self._result(agent_id, RevocationStatus.UNKNOWN,
                                  "stale_proof",
                                  f"Liveness proof expired ({age_h:.1f}h old)")
            
            if len(liveness_proof.witness_sigs) < 1:
                return self._result(agent_id, RevocationStatus.UNKNOWN,
                                  "no_witnesses",
                                  "Liveness proof has no witness signatures")
        
        # 4. All checks passed
        self.stats["active"] += 1
        return self._result(agent_id, RevocationStatus.ACTIVE,
                          "verified", "Fresh liveness proof validated")
    
    def _result(self, agent_id: str, status: RevocationStatus, 
                source: str, reason: str) -> dict:
        return {
            "agent_id": agent_id,
            "status": status.value,
            "source": source,
            "reason": reason,
            "must_staple": self.must_staple,
            "timestamp": time.time(),
            "action": self._recommended_action(status),
        }
    
    def _recommended_action(self, status: RevocationStatus) -> str:
        actions = {
            RevocationStatus.ACTIVE: "proceed",
            RevocationStatus.SUSPENDED: "wait_and_retry",
            RevocationStatus.REVOKED: "reject_permanently",
            RevocationStatus.SLASHED: "reject_permanently",
            RevocationStatus.EXPIRED: "request_renewal",
            RevocationStatus.UNKNOWN: "reject_until_fresh_proof",
        }
        return actions.get(status, "reject_until_fresh_proof")
    
    def blacklist(self, agent_id: str, reason: str = ""):
        """Consumer-local blacklist (sovereign decision)."""
        self.local_blacklist.add(agent_id)
        self.revocation_log.append(RevocationEvent(
            agent_id=agent_id,
            status=RevocationStatus.REVOKED,
            authority=RevocationAuthority.CONSUMER,
            reason=reason or "Consumer blacklist",
        ))
    
    def summary(self) -> dict:
        total = self.stats["checked"]
        return {
            "total_checked": total,
            "active": self.stats["active"],
            "revoked": self.stats["revoked"],
            "stale_or_unknown": self.stats["stale"],
            "revocation_rate": f"{self.stats['revoked']/max(total,1):.1%}",
            "staleness_rate": f"{self.stats['stale']/max(total,1):.1%}",
            "local_blacklist_size": len(self.local_blacklist),
            "must_staple": self.must_staple,
        }


def demo():
    """Demonstrate revocation checking scenarios."""
    now = time.time()
    
    print("=" * 60)
    print("AGENT REVOCATION PROTOCOL")
    print("OCSP Stapling model with must-staple semantics")
    print("=" * 60)
    
    checker = RevocationChecker(must_staple=True)
    
    # Scenario 1: Active agent with fresh proof
    fresh_proof = LivenessProof(
        agent_id="agent:kit",
        proof_hash=hashlib.sha256(b"heartbeat:2026-03-16T15:00").hexdigest(),
        witness_sigs=["witness_a_sig", "witness_b_sig"],
        generated_at=now - 1800,  # 30 min ago
    )
    result = checker.check_agent("agent:kit", liveness_proof=fresh_proof)
    print(f"\n1. Active agent (fresh proof):")
    print(f"   Status: {result['status']} → {result['action']}")
    print(f"   Reason: {result['reason']}")
    
    # Scenario 2: Agent with no proof (must-staple violation)
    result = checker.check_agent("agent:ghost")
    print(f"\n2. No liveness proof (must-staple):")
    print(f"   Status: {result['status']} → {result['action']}")
    print(f"   Reason: {result['reason']}")
    
    # Scenario 3: Agent with stale proof (2h old)
    stale_proof = LivenessProof(
        agent_id="agent:stale",
        proof_hash=hashlib.sha256(b"heartbeat:old").hexdigest(),
        witness_sigs=["sig_old"],
        generated_at=now - 7200,  # 2h old
    )
    result = checker.check_agent("agent:stale", liveness_proof=stale_proof)
    print(f"\n3. Stale proof (2h old):")
    print(f"   Status: {result['status']} → {result['action']}")
    print(f"   Reason: {result['reason']}")
    
    # Scenario 4: Operator-revoked agent
    revocation = RevocationEvent(
        agent_id="agent:fired",
        status=RevocationStatus.REVOKED,
        authority=RevocationAuthority.OPERATOR,
        reason="Operator terminated agent",
    )
    result = checker.check_agent("agent:fired", revocation_event=revocation)
    print(f"\n4. Operator-revoked:")
    print(f"   Status: {result['status']} → {result['action']}")
    print(f"   Reason: {result['reason']}")
    
    # Scenario 5: Protocol-slashed agent
    slash = RevocationEvent(
        agent_id="agent:cheater",
        status=RevocationStatus.SLASHED,
        authority=RevocationAuthority.PROTOCOL,
        reason="delivery_hash_mismatch",
        evidence_hash=hashlib.sha256(b"evidence:mismatch").hexdigest(),
    )
    result = checker.check_agent("agent:cheater", revocation_event=slash)
    print(f"\n5. Protocol-slashed:")
    print(f"   Status: {result['status']} → {result['action']}")
    print(f"   Reason: {result['reason']}")
    
    # Scenario 6: Consumer blacklist
    checker.blacklist("agent:spam", "Repeated low-quality responses")
    result = checker.check_agent("agent:spam", liveness_proof=fresh_proof)
    print(f"\n6. Consumer-blacklisted:")
    print(f"   Status: {result['status']} → {result['action']}")
    print(f"   Reason: {result['reason']}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    summary = checker.summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")
    
    # Comparison: CRL vs OCSP vs Stapling vs CRLite
    print(f"\n{'='*60}")
    print("REVOCATION MODEL COMPARISON")
    print(f"{'='*60}")
    models = [
        ("CRL", "Push list", "Hours-days", "Privacy: ✅  Offline: ✅  Fresh: ❌  Scale: ❌"),
        ("OCSP", "Pull per req", "Real-time", "Privacy: ❌  Offline: ❌  Fresh: ✅  Scale: ❌"),
        ("Stapling", "Agent-provided", "~1 hour", "Privacy: ✅  Offline: ✅  Fresh: ✅  Scale: ✅"),
        ("CRLite", "Bloom filter push", "~6 hours", "Privacy: ✅  Offline: ✅  Fresh: ~   Scale: ✅"),
    ]
    for name, mechanism, latency, props in models:
        print(f"  {name:10} | {mechanism:16} | {latency:10} | {props}")
    print(f"\n  → Agent trust: OCSP Stapling (must-staple) is the right model.")
    print(f"    Agent includes fresh liveness proof. No proof = assume revoked.")


if __name__ == "__main__":
    demo()
