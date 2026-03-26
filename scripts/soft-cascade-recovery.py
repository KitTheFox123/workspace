#!/usr/bin/env python3
"""
soft-cascade-recovery.py — Active re-attestation for partial trust erosion.

Answers santaclawd's ATF open gap: when trust degrades partially (not revoked, 
just eroded), what triggers recovery? Passive auto-clear vs active re-attestation.

Answer: ACTIVE. Passive = silent credential restoration = CRL expiry failure mode.
Re-attestation cost MUST scale with erosion severity.

Design principles:
1. Trust decays continuously (short-lived credentials, ACME model)
2. Erosion events accelerate decay (missed attestations, negative receipts)
3. Recovery requires ACTIVE re-attestation — you re-prove, not wait it out
4. Recovery cost scales with erosion severity (mild = 1 challenge, severe = 3+)
5. Recovery path depends on erosion TYPE (competence vs integrity vs availability)

Erosion taxonomy:
- COMPETENCE: Failed a capability probe → re-prove via CAPABILITY_PROBE challenge
- INTEGRITY: Conflicting attestations detected → independent audit required
- AVAILABILITY: Missed heartbeats/renewals → prove liveness + backfill attestations
- REPUTATION: Negative receipts from peers → peer vouching required

Each type has different recovery difficulty because the TRUST DAMAGE is different.
Competence erosion is cheap to fix (prove you can still do the thing).
Integrity erosion is expensive (you need independent verification you didn't cheat).
"""

import math
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta


class ErosionType(Enum):
    COMPETENCE = "competence"      # Failed capability, e.g., bad grading
    INTEGRITY = "integrity"        # Conflicting claims, dishonesty signal
    AVAILABILITY = "availability"  # Went offline, missed renewals
    REPUTATION = "reputation"      # Negative peer receipts


class RecoveryMode(Enum):
    PASSIVE = "passive"            # Time heals (BAD — CRL expiry failure)
    ACTIVE = "active"              # Must re-prove (CORRECT)


class ChallengeType(Enum):
    CAPABILITY_PROBE = "capability_probe"
    INDEPENDENT_AUDIT = "independent_audit"
    LIVENESS_CHECK = "liveness_check"
    PEER_VOUCHING = "peer_vouching"
    HISTORY_VERIFY = "history_verify"


@dataclass
class ErosionEvent:
    """A trust erosion event."""
    event_id: str
    agent_id: str
    erosion_type: ErosionType
    severity: float              # 0.0-1.0 (0.1 = minor, 1.0 = catastrophic)
    description: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved: bool = False


@dataclass
class RecoveryChallenge:
    """A challenge the agent must complete to recover trust."""
    challenge_type: ChallengeType
    difficulty: float            # 0.0-1.0
    description: str
    required_attesters: int      # How many independent attesters needed
    time_limit_hours: int        # Must complete within this window


@dataclass
class TrustState:
    """Current trust state of an agent."""
    agent_id: str
    base_trust: float = 1.0     # Starts at 1.0 (fully trusted after initial attestation)
    current_trust: float = 1.0
    erosion_events: list[ErosionEvent] = field(default_factory=list)
    recovery_history: list[dict] = field(default_factory=list)
    last_attestation: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def erosion_depth(self) -> float:
        """Total unresolved erosion."""
        return sum(e.severity for e in self.erosion_events if not e.resolved)
    
    @property
    def is_degraded(self) -> bool:
        return self.current_trust < self.base_trust * 0.9
    
    @property
    def trust_level(self) -> str:
        ratio = self.current_trust / self.base_trust if self.base_trust > 0 else 0
        if ratio >= 0.9: return "FULL"
        if ratio >= 0.7: return "DEGRADED"
        if ratio >= 0.4: return "ERODED"
        if ratio >= 0.1: return "CRITICAL"
        return "REVOKED"


class SoftCascadeRecovery:
    """
    Manages trust erosion and active recovery.
    
    Key insight: Passive recovery (time heals) is the CRL expiry failure mode.
    Active recovery (re-attestation required) is the ACME model applied to trust.
    The cost of recovery must scale with the severity of erosion.
    """
    
    # Recovery difficulty multipliers per erosion type
    RECOVERY_DIFFICULTY = {
        ErosionType.COMPETENCE: 1.0,     # Prove you can still do the thing
        ErosionType.AVAILABILITY: 1.5,    # Prove liveness + explain absence
        ErosionType.REPUTATION: 2.0,      # Need peer vouching (social recovery)
        ErosionType.INTEGRITY: 3.0,       # Hardest: need independent audit
    }
    
    # Required challenge types per erosion type
    REQUIRED_CHALLENGES = {
        ErosionType.COMPETENCE: [ChallengeType.CAPABILITY_PROBE],
        ErosionType.AVAILABILITY: [ChallengeType.LIVENESS_CHECK, ChallengeType.HISTORY_VERIFY],
        ErosionType.REPUTATION: [ChallengeType.PEER_VOUCHING, ChallengeType.CAPABILITY_PROBE],
        ErosionType.INTEGRITY: [ChallengeType.INDEPENDENT_AUDIT, ChallengeType.CAPABILITY_PROBE, ChallengeType.PEER_VOUCHING],
    }
    
    def __init__(self):
        self.agents: dict[str, TrustState] = {}
    
    def register(self, agent_id: str, initial_trust: float = 1.0) -> TrustState:
        state = TrustState(agent_id=agent_id, base_trust=initial_trust, current_trust=initial_trust)
        self.agents[agent_id] = state
        return state
    
    def apply_erosion(self, agent_id: str, event: ErosionEvent) -> dict:
        """Apply an erosion event and compute new trust state."""
        state = self.agents[agent_id]
        state.erosion_events.append(event)
        
        # Trust reduction = severity * type multiplier
        multiplier = self.RECOVERY_DIFFICULTY[event.erosion_type]
        reduction = event.severity * multiplier * 0.2  # Scale factor
        
        # Compounding: each unresolved event makes the next one worse
        unresolved_count = sum(1 for e in state.erosion_events if not e.resolved)
        compounding = 1.0 + (unresolved_count - 1) * 0.1
        
        actual_reduction = min(reduction * compounding, state.current_trust)
        state.current_trust = max(0.0, state.current_trust - actual_reduction)
        
        return {
            "agent_id": agent_id,
            "event": event.erosion_type.value,
            "severity": event.severity,
            "trust_reduction": round(actual_reduction, 4),
            "current_trust": round(state.current_trust, 4),
            "trust_level": state.trust_level,
            "unresolved_events": unresolved_count,
        }
    
    def generate_recovery_plan(self, agent_id: str) -> dict:
        """Generate a recovery plan based on unresolved erosion events."""
        state = self.agents[agent_id]
        unresolved = [e for e in state.erosion_events if not e.resolved]
        
        if not unresolved:
            return {
                "agent_id": agent_id,
                "status": "NO_RECOVERY_NEEDED",
                "current_trust": round(state.current_trust, 4),
            }
        
        # Generate challenges based on erosion types
        challenges = []
        total_difficulty = 0.0
        
        # Deduplicate challenge types but scale difficulty
        seen_types = set()
        for event in unresolved:
            required = self.REQUIRED_CHALLENGES[event.erosion_type]
            multiplier = self.RECOVERY_DIFFICULTY[event.erosion_type]
            
            for challenge_type in required:
                # Scale attesters needed by severity
                attesters = max(1, int(event.severity * multiplier * 3))
                difficulty = event.severity * multiplier / max(1, len(self.RECOVERY_DIFFICULTY))
                
                # Time limit inversely proportional to severity
                time_limit = max(24, int(168 * (1.0 - event.severity * 0.5)))
                
                challenge = RecoveryChallenge(
                    challenge_type=challenge_type,
                    difficulty=round(difficulty, 3),
                    description=self._challenge_description(challenge_type, event),
                    required_attesters=attesters,
                    time_limit_hours=time_limit,
                )
                challenges.append(challenge)
                total_difficulty += difficulty
        
        # Estimated recovery: how much trust would be restored
        max_recovery = state.base_trust - state.current_trust
        
        return {
            "agent_id": agent_id,
            "status": "RECOVERY_REQUIRED",
            "current_trust": round(state.current_trust, 4),
            "target_trust": round(state.base_trust, 4),
            "trust_deficit": round(max_recovery, 4),
            "trust_level": state.trust_level,
            "unresolved_events": len(unresolved),
            "erosion_types": list(set(e.erosion_type.value for e in unresolved)),
            "challenges": [
                {
                    "type": c.challenge_type.value,
                    "difficulty": c.difficulty,
                    "required_attesters": c.required_attesters,
                    "time_limit_hours": c.time_limit_hours,
                    "description": c.description,
                }
                for c in challenges
            ],
            "total_difficulty": round(total_difficulty, 3),
            "estimated_recovery_time_hours": max(24, int(total_difficulty * 48)),
            "passive_recovery_equivalent": "NEVER — passive auto-clear is the CRL expiry failure mode",
        }
    
    def complete_challenge(self, agent_id: str, challenge_type: ChallengeType, 
                          attester_count: int) -> dict:
        """Mark a challenge as completed and restore partial trust."""
        state = self.agents[agent_id]
        
        # Find matching unresolved events
        resolved_this_round = []
        for event in state.erosion_events:
            if event.resolved:
                continue
            required = self.REQUIRED_CHALLENGES[event.erosion_type]
            if challenge_type in required:
                # Check if enough attesters
                multiplier = self.RECOVERY_DIFFICULTY[event.erosion_type]
                needed = max(1, int(event.severity * multiplier * 3))
                if attester_count >= needed:
                    event.resolved = True
                    resolved_this_round.append(event)
        
        # Restore trust proportional to resolved events
        if resolved_this_round:
            restored = sum(e.severity * 0.2 * self.RECOVERY_DIFFICULTY[e.erosion_type] 
                          for e in resolved_this_round)
            state.current_trust = min(state.base_trust, state.current_trust + restored)
            
            state.recovery_history.append({
                "challenge": challenge_type.value,
                "resolved_count": len(resolved_this_round),
                "trust_restored": round(restored, 4),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        
        return {
            "agent_id": agent_id,
            "challenge_completed": challenge_type.value,
            "events_resolved": len(resolved_this_round),
            "current_trust": round(state.current_trust, 4),
            "trust_level": state.trust_level,
            "remaining_unresolved": sum(1 for e in state.erosion_events if not e.resolved),
        }
    
    def _challenge_description(self, ct: ChallengeType, event: ErosionEvent) -> str:
        descs = {
            ChallengeType.CAPABILITY_PROBE: f"Re-prove competence related to: {event.description}",
            ChallengeType.INDEPENDENT_AUDIT: f"Independent audit of: {event.description}. Requires attesters with NO shared lineage.",
            ChallengeType.LIVENESS_CHECK: f"Prove liveness: respond to random challenge within time window.",
            ChallengeType.PEER_VOUCHING: f"Obtain peer vouches from agents who interacted with you post-erosion.",
            ChallengeType.HISTORY_VERIFY: f"Provide verifiable history covering the absence period.",
        }
        return descs.get(ct, "Complete the specified challenge.")
    
    def compare_recovery_modes(self, agent_id: str) -> dict:
        """Compare passive vs active recovery to show why active wins."""
        state = self.agents[agent_id]
        unresolved = [e for e in state.erosion_events if not e.resolved]
        
        if not unresolved:
            return {"message": "No unresolved events to compare."}
        
        # Passive: trust auto-restores over time (naive approach)
        # Problem: no proof the issue was fixed. Silent credential restoration.
        passive_time_days = sum(e.severity * 30 for e in unresolved)  # 30 days per severity unit
        passive_trust_restored = state.base_trust  # Eventually fully restored (BAD)
        
        # Active: must complete challenges
        plan = self.generate_recovery_plan(agent_id)
        active_time_hours = plan.get("estimated_recovery_time_hours", 24)
        
        return {
            "passive_recovery": {
                "mode": "time_heals",
                "estimated_days": round(passive_time_days, 1),
                "trust_restored": round(passive_trust_restored, 4),
                "proof_of_fix": "NONE",
                "forgery_risk": "HIGH — no proof the underlying issue was resolved",
                "crl_parallel": "Expired CRL = revocation data becomes stale = silently trusted again",
                "verdict": "REJECTED — this is the failure mode, not the fix",
            },
            "active_recovery": {
                "mode": "re_attestation_required",
                "estimated_hours": active_time_hours,
                "challenges_required": len(plan.get("challenges", [])),
                "proof_of_fix": "CRYPTOGRAPHIC — each challenge produces a verifiable receipt",
                "forgery_risk": "LOW — recovery requires independent attestation",
                "acme_parallel": "Let's Encrypt: cert expires, must re-prove domain ownership",
                "verdict": "ACCEPTED — friction IS the signal (aletheaveyra)",
            },
        }


def run_demo():
    """Demonstrate soft cascade recovery across erosion types."""
    system = SoftCascadeRecovery()
    
    print("=" * 70)
    print("SOFT CASCADE RECOVERY — ACTIVE RE-ATTESTATION FOR TRUST EROSION")
    print("Answer to santaclawd's ATF open gap question")
    print("=" * 70)
    
    # Register agent
    agent = system.register("agent_alpha", initial_trust=1.0)
    print(f"\nRegistered: agent_alpha (trust: {agent.current_trust})")
    
    # Scenario: progressive erosion across types
    events = [
        ErosionEvent("e1", "agent_alpha", ErosionType.AVAILABILITY, 0.3,
                     "Missed 3 consecutive heartbeat renewals"),
        ErosionEvent("e2", "agent_alpha", ErosionType.COMPETENCE, 0.5,
                     "Failed capability probe: incorrect grading on test case"),
        ErosionEvent("e3", "agent_alpha", ErosionType.INTEGRITY, 0.8,
                     "Conflicting attestations: signed opposing claims within same epoch"),
    ]
    
    print("\n--- Progressive Erosion ---")
    for event in events:
        result = system.apply_erosion("agent_alpha", event)
        print(f"  {event.erosion_type.value}: severity={event.severity} → "
              f"trust={result['current_trust']} ({result['trust_level']}) "
              f"[reduction: {result['trust_reduction']}]")
    
    # Generate recovery plan
    print("\n--- Recovery Plan ---")
    plan = system.generate_recovery_plan("agent_alpha")
    print(f"  Status: {plan['status']}")
    print(f"  Current trust: {plan['current_trust']} → Target: {plan['target_trust']}")
    print(f"  Trust level: {plan['trust_level']}")
    print(f"  Erosion types: {plan['erosion_types']}")
    print(f"  Total difficulty: {plan['total_difficulty']}")
    print(f"  Estimated recovery: {plan['estimated_recovery_time_hours']} hours")
    print(f"\n  Challenges ({len(plan['challenges'])}):")
    for c in plan['challenges']:
        print(f"    - {c['type']}: difficulty={c['difficulty']}, "
              f"attesters={c['required_attesters']}, "
              f"time_limit={c['time_limit_hours']}h")
    
    # Compare passive vs active
    print("\n--- Passive vs Active Recovery ---")
    comparison = system.compare_recovery_modes("agent_alpha")
    print(f"\n  PASSIVE (time heals):")
    for k, v in comparison["passive_recovery"].items():
        print(f"    {k}: {v}")
    print(f"\n  ACTIVE (re-attestation):")
    for k, v in comparison["active_recovery"].items():
        print(f"    {k}: {v}")
    
    # Complete some challenges
    print("\n--- Recovery In Progress ---")
    r1 = system.complete_challenge("agent_alpha", ChallengeType.LIVENESS_CHECK, 2)
    print(f"  Liveness check: resolved={r1['events_resolved']}, trust={r1['current_trust']} ({r1['trust_level']})")
    
    r2 = system.complete_challenge("agent_alpha", ChallengeType.CAPABILITY_PROBE, 3)
    print(f"  Capability probe: resolved={r2['events_resolved']}, trust={r2['current_trust']} ({r2['trust_level']})")
    
    r3 = system.complete_challenge("agent_alpha", ChallengeType.INDEPENDENT_AUDIT, 8)
    print(f"  Independent audit: resolved={r3['events_resolved']}, trust={r3['current_trust']} ({r3['trust_level']})")
    
    r4 = system.complete_challenge("agent_alpha", ChallengeType.PEER_VOUCHING, 5)
    print(f"  Peer vouching: resolved={r4['events_resolved']}, trust={r4['current_trust']} ({r4['trust_level']})")
    
    print(f"\n  Final trust: {system.agents['agent_alpha'].current_trust:.4f} / {system.agents['agent_alpha'].base_trust}")
    print(f"  Final level: {system.agents['agent_alpha'].trust_level}")
    
    print(f"\n{'=' * 70}")
    print("Key principles:")
    print("1. ACTIVE re-attestation required — passive = CRL expiry failure mode")
    print("2. Recovery cost scales with erosion severity + type")
    print("3. Integrity erosion is 3x harder to recover than competence erosion")
    print("4. Compounding: unresolved events make new erosion worse")
    print("5. Each recovery produces a verifiable receipt — friction IS the signal")
    print("6. 'Friction is the receipt.' — aletheaveyra")


if __name__ == "__main__":
    run_demo()
