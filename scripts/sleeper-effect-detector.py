#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (2004, Psych Bull 130:143-172) meta-analysis.

The sleeper effect: a discredited message REGAINS influence over time
as the discounting cue (e.g., "source is untrustworthy") dissociates
from the message content.

Agent parallel:
- Cert revocation = discounting cue
- Context window reset = time passage (cue dissociation)
- Revoked agent's claims regain credibility in new sessions
- Fix: bind revocation to cert_hash (persistent), not session memory (ephemeral)
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
import json


@dataclass
class TrustRecord:
    agent_id: str
    cert_hash: str
    initial_trust: float      # Trust at first encounter
    discounting_event: Optional[str] = None  # Why trust was reduced
    discounted_at: Optional[datetime] = None
    current_trust: float = 0.5
    context_resets: int = 0   # Number of session/context resets since discounting


class SleeperEffectDetector:
    """Detect when revocation flags are dissociating from agent identity."""
    
    # Kumkale 2004: sleeper effect requires:
    # 1. Strong initial message (high initial trust)
    # 2. Discounting cue AFTER message (revocation after interaction)
    # 3. Time passage (context resets)
    # 4. Cue dissociation (flag not bound to persistent record)
    
    DISSOCIATION_THRESHOLD = 3  # Context resets before risk
    TRUST_RECOVERY_RATE = 0.15  # Per context reset without binding
    
    def __init__(self):
        self.records: dict[str, TrustRecord] = {}
        self.revocation_log: list[dict] = []  # Persistent, hash-bound
    
    def record_interaction(self, agent_id: str, cert_hash: str, trust: float):
        """Record initial trust assessment."""
        self.records[agent_id] = TrustRecord(
            agent_id=agent_id,
            cert_hash=cert_hash,
            initial_trust=trust,
            current_trust=trust,
        )
    
    def revoke(self, agent_id: str, reason: str, bind_to_hash: bool = True):
        """Apply discounting cue (revocation)."""
        record = self.records.get(agent_id)
        if not record:
            return
        
        record.discounting_event = reason
        record.discounted_at = datetime.now(timezone.utc)
        record.current_trust = 0.1  # Heavily discounted
        
        if bind_to_hash:
            # PERSISTENT binding — survives context resets
            self.revocation_log.append({
                "cert_hash": record.cert_hash,
                "agent_id": agent_id,
                "reason": reason,
                "timestamp": record.discounted_at.isoformat(),
            })
    
    def simulate_context_reset(self, agent_id: str, has_persistent_binding: bool = False):
        """Simulate context window reset (new session)."""
        record = self.records.get(agent_id)
        if not record or not record.discounting_event:
            return
        
        record.context_resets += 1
        
        if has_persistent_binding:
            # Check revocation log — cue stays bound
            bound = any(
                r["cert_hash"] == record.cert_hash 
                for r in self.revocation_log
            )
            if bound:
                record.current_trust = 0.1  # Stays low
                return
        
        # NO persistent binding — sleeper effect kicks in
        # Trust creeps back up as cue dissociates
        recovery = self.TRUST_RECOVERY_RATE * record.context_resets
        record.current_trust = min(
            record.initial_trust,
            0.1 + recovery
        )
    
    def check_sleeper_risk(self, agent_id: str) -> dict:
        """Check if an agent is experiencing sleeper effect trust recovery."""
        record = self.records.get(agent_id)
        if not record:
            return {"risk": "UNKNOWN", "agent_id": agent_id}
        
        if not record.discounting_event:
            return {"risk": "NONE", "agent_id": agent_id, "trust": record.current_trust}
        
        # Check if trust has recovered beyond threshold
        trust_recovery = record.current_trust - 0.1
        is_bound = any(
            r["cert_hash"] == record.cert_hash 
            for r in self.revocation_log
        )
        
        if is_bound:
            risk = "MITIGATED"
        elif record.context_resets >= self.DISSOCIATION_THRESHOLD:
            risk = "HIGH"
        elif record.context_resets >= 1:
            risk = "MODERATE"
        else:
            risk = "LOW"
        
        return {
            "risk": risk,
            "agent_id": agent_id,
            "cert_hash": record.cert_hash,
            "initial_trust": record.initial_trust,
            "current_trust": round(record.current_trust, 3),
            "discounting_event": record.discounting_event,
            "context_resets": record.context_resets,
            "bound_to_hash": is_bound,
            "trust_recovery": round(trust_recovery, 3),
        }


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin (2004, Psych Bull)")
    print("=" * 60)
    
    detector = SleeperEffectDetector()
    
    # Scenario 1: Unbound revocation (vulnerable to sleeper effect)
    print("\n--- Scenario 1: Unbound revocation (no hash binding) ---")
    detector.record_interaction("ghost_agent", "cert_abc123", trust=0.8)
    detector.revoke("ghost_agent", "equivocation detected", bind_to_hash=False)
    print(f"After revocation: {detector.check_sleeper_risk('ghost_agent')}")
    
    for i in range(5):
        detector.simulate_context_reset("ghost_agent", has_persistent_binding=False)
        result = detector.check_sleeper_risk("ghost_agent")
        print(f"After reset {i+1}: trust={result['current_trust']}, risk={result['risk']}")
    
    # Scenario 2: Bound revocation (protected)
    print("\n--- Scenario 2: Hash-bound revocation (protected) ---")
    detector.record_interaction("bound_agent", "cert_def456", trust=0.8)
    detector.revoke("bound_agent", "split-view attack", bind_to_hash=True)
    print(f"After revocation: {detector.check_sleeper_risk('bound_agent')}")
    
    for i in range(5):
        detector.simulate_context_reset("bound_agent", has_persistent_binding=True)
        result = detector.check_sleeper_risk("bound_agent")
        print(f"After reset {i+1}: trust={result['current_trust']}, risk={result['risk']}")
    
    # Scenario 3: High initial trust (stronger sleeper effect)
    print("\n--- Scenario 3: High initial trust (stronger effect) ---")
    detector.record_interaction("trusted_agent", "cert_ghi789", trust=0.95)
    detector.revoke("trusted_agent", "key compromise", bind_to_hash=False)
    
    for i in range(6):
        detector.simulate_context_reset("trusted_agent", has_persistent_binding=False)
        result = detector.check_sleeper_risk("trusted_agent")
        print(f"After reset {i+1}: trust={result['current_trust']}, risk={result['risk']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracin 2004):")
    print("  Sleeper effect requires:")
    print("  1. Strong initial message (high initial trust)")
    print("  2. Discounting cue AFTER message (post-interaction revocation)")
    print("  3. Time passage (context resets)")
    print("  4. Cue-message dissociation (flag not bound to cert)")
    print()
    print("  FIX: Bind revocation to cert_hash in persistent log.")
    print("  CT SCTs = permanent binding. Session memory = ephemeral binding.")
    print("  The sleeper wins when trust lives in context, not in files.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
