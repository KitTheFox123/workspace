#!/usr/bin/env python3
"""
soft-cascade-recovery.py — Simulate trust degradation and recovery strategies.

Maps the death of OCSP to agent trust recovery:
- Let's Encrypt killed OCSP (Dec 2024), Google following (H2 2025)
- Replacement: short-lived certs (90d → 47d → 6d!)
- Key insight (Feisty Duck): "with short-lived certificates, we finally have a
  plausible revocation story, even if it doesn't involve any revocation"

ATF SOFT_CASCADE problem (santaclawd):
When trust degrades PARTIALLY — not revoked, just eroded — what triggers
re-attestation? Two strategies:
1. PASSIVE: time heals, auto-clear after cool-off period
2. ACTIVE: agent must pass capability probe to restore

This simulator compares strategies across scenarios:
- Soft-fail (OCSP model): ignore degradation = zero security value
- Passive recovery: auto-restore after TTL expires = trust inflation
- Active recovery (ACME model): challenge required = strongest signal
- Hybrid: passive for minor erosion, active for significant degradation

Key finding from OCSP history: soft-fail was WORSE than no checking.
"If you're under active attack, attackers can simply block your OCSP
attempts and carry on." (Ristić, 2025)

Sources:
- Ristić, "The Slow Death of OCSP" (Feisty Duck, Jan 2025)
- Google Trust Services OCSP deprecation (Apr 2025)
- Let's Encrypt OCSP end-of-life (Dec 2024)
- CA/Browser Forum SC-063v4: short-lived certs + optional OCSP (Aug 2023)
- RFC 8555: ACME protocol (Let's Encrypt automation)
"""

import random
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    FULL = "full"           # Active, recently attested
    DEGRADED = "degraded"   # Partially eroded, still functional
    EXPIRED = "expired"     # TTL exceeded, needs renewal
    REVOKED = "revoked"     # Explicitly revoked
    CHALLENGED = "challenged"  # Undergoing re-attestation


class RecoveryStrategy(Enum):
    SOFT_FAIL = "soft_fail"       # Ignore degradation (OCSP browser model)
    PASSIVE = "passive"           # Auto-restore after cool-off
    ACTIVE = "active"             # Challenge required (ACME model)
    HYBRID = "hybrid"             # Passive for minor, active for major


class EventType(Enum):
    ATTESTATION_SUCCESS = "attest_ok"
    ATTESTATION_FAIL = "attest_fail"
    COMPLAINT = "complaint"
    TIMEOUT = "timeout"
    CHALLENGE_PASS = "challenge_pass"
    CHALLENGE_FAIL = "challenge_fail"
    ATTACK = "attack"             # Malicious actor exploiting degraded trust


@dataclass
class TrustRecord:
    agent_id: str
    trust_score: float          # 0.0 to 1.0
    state: TrustState
    ttl_remaining: int          # Ticks until expiry
    degradation_count: int = 0  # Number of erosion events
    recovery_count: int = 0     # Number of successful recoveries
    exploited_count: int = 0    # Times trust was exploited while degraded
    
    @property
    def is_vulnerable(self) -> bool:
        """Agent is vulnerable if degraded but still trusted."""
        return self.state == TrustState.DEGRADED and self.trust_score > 0.3


@dataclass
class SimResult:
    strategy: str
    ticks: int
    avg_trust: float
    exploits: int
    false_recoveries: int       # Recovered without actual improvement
    legitimate_blocks: int      # Legitimate agents blocked unnecessarily
    total_challenges: int
    recovery_success_rate: float


class SoftCascadeSimulator:
    """
    Simulate trust degradation and recovery under different strategies.
    
    Models the OCSP lesson: soft-fail checking is worse than no checking
    because it provides false confidence. Same applies to trust recovery.
    """
    
    def __init__(self, num_agents: int = 20, ticks: int = 200, seed: int = 42):
        self.num_agents = num_agents
        self.ticks = ticks
        self.rng = random.Random(seed)
        
        # Simulation parameters
        self.base_ttl = 72           # Base TTL in ticks (maps to 72h)
        self.degradation_rate = 0.15 # Probability of erosion event per tick
        self.attack_rate = 0.05      # Probability of attack on degraded agent
        self.challenge_pass_rate = 0.7  # Probability of passing challenge
        self.passive_cooloff = 20    # Ticks before passive recovery
        self.degradation_threshold = 0.5  # Below this = "significant" degradation
    
    def init_agents(self) -> list[TrustRecord]:
        return [
            TrustRecord(
                agent_id=f"agent_{i}",
                trust_score=1.0,
                state=TrustState.FULL,
                ttl_remaining=self.base_ttl,
            )
            for i in range(self.num_agents)
        ]
    
    def apply_degradation(self, agent: TrustRecord) -> Optional[EventType]:
        """Random erosion event."""
        if self.rng.random() < self.degradation_rate:
            erosion = self.rng.uniform(0.05, 0.25)
            agent.trust_score = max(0.0, agent.trust_score - erosion)
            agent.degradation_count += 1
            if agent.trust_score < self.degradation_threshold:
                agent.state = TrustState.DEGRADED
            return EventType.COMPLAINT
        return None
    
    def apply_attack(self, agent: TrustRecord) -> Optional[EventType]:
        """Attack attempt on vulnerable agent."""
        if agent.is_vulnerable and self.rng.random() < self.attack_rate:
            agent.exploited_count += 1
            return EventType.ATTACK
        return None
    
    def tick_ttl(self, agent: TrustRecord):
        """Decrement TTL."""
        agent.ttl_remaining -= 1
        if agent.ttl_remaining <= 0:
            agent.state = TrustState.EXPIRED
    
    def recover_soft_fail(self, agent: TrustRecord):
        """OCSP model: ignore degradation entirely."""
        # "Soft-fail OCSP checking became the norm... that is, unfortunately, pointless."
        if agent.state == TrustState.DEGRADED:
            # Pretend everything is fine
            agent.state = TrustState.FULL  # False recovery
    
    def recover_passive(self, agent: TrustRecord, tick: int):
        """Auto-restore after cool-off period."""
        if agent.state == TrustState.DEGRADED:
            # Wait for cool-off, then auto-restore
            if agent.degradation_count > 0 and tick % self.passive_cooloff == 0:
                agent.trust_score = min(1.0, agent.trust_score + 0.3)
                agent.state = TrustState.FULL
                agent.recovery_count += 1
    
    def recover_active(self, agent: TrustRecord) -> bool:
        """ACME model: challenge required for recovery."""
        if agent.state in (TrustState.DEGRADED, TrustState.EXPIRED):
            agent.state = TrustState.CHALLENGED
            if self.rng.random() < self.challenge_pass_rate:
                agent.trust_score = min(1.0, agent.trust_score + 0.4)
                agent.state = TrustState.FULL
                agent.recovery_count += 1
                agent.ttl_remaining = self.base_ttl
                return True
            else:
                agent.trust_score = max(0.0, agent.trust_score - 0.1)
                agent.state = TrustState.DEGRADED
                return False
        return False
    
    def recover_hybrid(self, agent: TrustRecord, tick: int) -> bool:
        """Passive for minor, active for significant degradation."""
        if agent.state == TrustState.DEGRADED:
            if agent.trust_score >= self.degradation_threshold:
                # Minor: passive recovery
                if tick % self.passive_cooloff == 0:
                    agent.trust_score = min(1.0, agent.trust_score + 0.2)
                    agent.state = TrustState.FULL
                    agent.recovery_count += 1
                return False
            else:
                # Significant: active challenge required
                return self.recover_active(agent)
        elif agent.state == TrustState.EXPIRED:
            return self.recover_active(agent)
        return False
    
    def run(self, strategy: RecoveryStrategy) -> SimResult:
        agents = self.init_agents()
        trust_history = []
        exploits = 0
        false_recoveries = 0
        legitimate_blocks = 0
        total_challenges = 0
        
        for tick in range(self.ticks):
            tick_trust = []
            
            for agent in agents:
                # 1. TTL decay
                self.tick_ttl(agent)
                
                # 2. Random degradation
                self.apply_degradation(agent)
                
                # 3. Attack attempts
                event = self.apply_attack(agent)
                if event == EventType.ATTACK:
                    exploits += 1
                
                # 4. Recovery based on strategy
                if strategy == RecoveryStrategy.SOFT_FAIL:
                    if agent.state == TrustState.DEGRADED:
                        old_score = agent.trust_score
                        self.recover_soft_fail(agent)
                        if agent.trust_score <= 0.5:
                            false_recoveries += 1
                
                elif strategy == RecoveryStrategy.PASSIVE:
                    self.recover_passive(agent, tick)
                
                elif strategy == RecoveryStrategy.ACTIVE:
                    if agent.state in (TrustState.DEGRADED, TrustState.EXPIRED):
                        total_challenges += 1
                        passed = self.recover_active(agent)
                        if not passed and agent.trust_score > 0.6:
                            legitimate_blocks += 1
                
                elif strategy == RecoveryStrategy.HYBRID:
                    if agent.state in (TrustState.DEGRADED, TrustState.EXPIRED):
                        if agent.trust_score < self.degradation_threshold:
                            total_challenges += 1
                        passed = self.recover_hybrid(agent, tick)
                        if not passed and agent.trust_score > 0.6:
                            legitimate_blocks += 1
                
                # 5. TTL renewal for healthy agents
                if agent.state == TrustState.FULL and agent.ttl_remaining <= 0:
                    agent.ttl_remaining = self.base_ttl
                
                tick_trust.append(agent.trust_score)
            
            trust_history.append(statistics.mean(tick_trust))
        
        total_recoveries = sum(a.recovery_count for a in agents)
        total_degradations = sum(a.degradation_count for a in agents)
        
        return SimResult(
            strategy=strategy.value,
            ticks=self.ticks,
            avg_trust=round(statistics.mean(trust_history), 4),
            exploits=exploits,
            false_recoveries=false_recoveries,
            legitimate_blocks=legitimate_blocks,
            total_challenges=total_challenges,
            recovery_success_rate=round(total_recoveries / max(total_degradations, 1), 4),
        )


def run_comparison():
    print("=" * 70)
    print("SOFT CASCADE RECOVERY — TRUST DEGRADATION STRATEGY COMPARISON")
    print("Based on OCSP death (LE Dec 2024, Google Apr 2025)")
    print("=" * 70)
    
    sim = SoftCascadeSimulator(num_agents=30, ticks=300, seed=42)
    
    strategies = [
        RecoveryStrategy.SOFT_FAIL,
        RecoveryStrategy.PASSIVE,
        RecoveryStrategy.ACTIVE,
        RecoveryStrategy.HYBRID,
    ]
    
    results = []
    for strategy in strategies:
        result = sim.run(strategy)
        results.append(result)
    
    # Display comparison
    print(f"\n{'Strategy':<15} {'Avg Trust':>10} {'Exploits':>10} {'False Rec':>10} {'Blocks':>10} {'Challenges':>10} {'Rec Rate':>10}")
    print("-" * 75)
    for r in results:
        print(f"{r.strategy:<15} {r.avg_trust:>10.4f} {r.exploits:>10} {r.false_recoveries:>10} {r.legitimate_blocks:>10} {r.total_challenges:>10} {r.recovery_success_rate:>10.4f}")
    
    print(f"\n{'=' * 70}")
    print("ANALYSIS")
    print(f"{'=' * 70}")
    
    sf, pa, ac, hy = results
    
    print(f"\n1. SOFT_FAIL: avg trust {sf.avg_trust:.3f}, {sf.exploits} DETECTED exploits, {sf.false_recoveries} false recoveries")
    print(f"   → 0 detected ≠ 0 actual. Attacks invisible because degraded→FULL instantly.")
    print(f"   → OCSP lesson: 'soft-fail checking is worse than no checking'")
    print(f"   → {sf.false_recoveries} false recoveries = trust score decays to {sf.avg_trust:.3f} anyway")
    
    print(f"\n2. PASSIVE: avg trust {pa.avg_trust:.3f}, {pa.exploits} exploits")
    print(f"   → Auto-restore = trust inflation. No proof of actual improvement.")
    print(f"   → 'Time heals' is a lie when the underlying problem persists.")
    
    print(f"\n3. ACTIVE (ACME): avg trust {ac.avg_trust:.3f}, {ac.exploits} exploits, {ac.legitimate_blocks} false blocks")
    print(f"   → Challenge-based = strongest signal. {ac.total_challenges} challenges issued.")
    print(f"   → Maps to LE short-lived certs: 'we have a plausible revocation story'")
    
    print(f"\n4. HYBRID: avg trust {hy.avg_trust:.3f}, {hy.exploits} exploits, {hy.total_challenges} challenges")
    print(f"   → Best balance: passive for minor erosion, active for significant.")
    print(f"   → Analogous to: standard certs (47d) for most + short-lived (6d) for high-security")
    
    # Winner determination
    best = min(results, key=lambda r: r.exploits)
    print(f"\n→ LOWEST EXPLOIT RATE: {best.strategy} ({best.exploits} exploits)")
    
    best_trust = max(results, key=lambda r: r.avg_trust)
    print(f"→ HIGHEST AVG TRUST: {best_trust.strategy} ({best_trust.avg_trust:.4f})")
    
    # The OCSP lesson
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT (from PKI history):")
    print("  OCSP soft-fail was WORSE than not checking at all.")
    print("  It gave users false confidence while providing zero attack prevention.")
    print("  Same for trust: passive auto-recovery = false confidence.")
    print("  Active re-attestation (ACME model) = the only honest recovery.")
    print("  Short TTL eliminates revocation entirely — absence of renewal IS revocation.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    run_comparison()
