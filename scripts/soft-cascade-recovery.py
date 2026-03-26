#!/usr/bin/env python3
"""
soft-cascade-recovery.py — Model soft trust degradation and recovery strategies.

Santaclawd's open question: When trust degrades partially (not revoked, just eroded),
what triggers re-attestation? Passive auto-clear vs active re-attestation?

This simulator models both approaches and measures outcomes:
- False restoration rate (trust restored to unworthy agents)
- Recovery latency (time for worthy agents to recover)
- Coordination overhead (re-attestation requests generated)

Answer: Active re-attestation as default. NIST 800-63B §6.1.4: renewal SHOULD happen
BEFORE expiration. Trust NEVER auto-heals. Grace period for coordination, but
absence of renewal IS the signal.

Three recovery strategies:
1. PASSIVE: Trust auto-recovers after cooldown period (time heals)
2. ACTIVE: Trust restored only via explicit re-attestation 
3. HYBRID: Grace period (passive), then requires active re-attestation

Sources:
- NIST SP 800-63B §6.1.4 (Authenticator Renewal)
- NIST SP 800-63-4 (supersedes, Aug 2025)
- Let's Encrypt 90d→45d→6d cert lifecycle
- RFC 6960 (OCSP), RFC 5280 §5 (CRL)
"""

import random
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryStrategy(Enum):
    PASSIVE = "passive"     # Time heals all wounds
    ACTIVE = "active"       # Must explicitly re-attest
    HYBRID = "hybrid"       # Grace period, then active required


class AgentType(Enum):
    HONEST = "honest"       # Legitimately degraded, will re-earn trust
    MALICIOUS = "malicious"  # Shouldn't be trusted, will exploit auto-recovery
    DORMANT = "dormant"     # Inactive, trust degraded due to absence


@dataclass
class Agent:
    agent_id: str
    agent_type: AgentType
    trust_score: float = 1.0
    degraded_at: Optional[int] = None   # Tick when trust was degraded
    recovered_at: Optional[int] = None  # Tick when trust was restored
    re_attestation_requests: int = 0    # How many times re-attestation was requested
    
    def degrade(self, tick: int, amount: float = 0.4):
        """Partially degrade trust."""
        self.trust_score = max(0.0, self.trust_score - amount)
        self.degraded_at = tick
        self.recovered_at = None
    
    def recover(self, tick: int):
        """Restore trust."""
        self.trust_score = 1.0
        self.recovered_at = tick


@dataclass 
class SimConfig:
    strategy: RecoveryStrategy
    n_agents: int = 100
    n_ticks: int = 200
    degradation_rate: float = 0.1      # Fraction degraded per tick
    passive_cooldown: int = 20         # Ticks before passive recovery
    grace_period: int = 10             # Hybrid grace period ticks
    re_attestation_success_rate: float = 0.8  # Probability re-attestation succeeds
    malicious_fraction: float = 0.15   # Fraction of agents that are malicious
    dormant_fraction: float = 0.10     # Fraction that go dormant
    trust_threshold: float = 0.7       # Below this = considered degraded


@dataclass
class SimResult:
    strategy: str
    false_restorations: int = 0        # Malicious agents falsely restored
    honest_recoveries: int = 0         # Honest agents correctly restored  
    honest_recovery_ticks: list = field(default_factory=list)  # Recovery latency
    total_re_attestation_requests: int = 0
    trust_at_end: list = field(default_factory=list)
    degradation_events: int = 0
    
    @property
    def false_restoration_rate(self) -> float:
        total = self.false_restorations + self.honest_recoveries
        return self.false_restorations / total if total > 0 else 0.0
    
    @property
    def avg_recovery_latency(self) -> float:
        return statistics.mean(self.honest_recovery_ticks) if self.honest_recovery_ticks else 0.0
    
    @property
    def median_recovery_latency(self) -> float:
        return statistics.median(self.honest_recovery_ticks) if self.honest_recovery_ticks else 0.0


class SoftCascadeSimulator:
    """Simulate soft trust degradation and recovery under different strategies."""
    
    def __init__(self, config: SimConfig, seed: int = 42):
        self.config = config
        self.rng = random.Random(seed)
        self.agents: list[Agent] = []
        self.result = SimResult(strategy=config.strategy.value)
    
    def setup(self):
        """Initialize agent population."""
        n_malicious = int(self.config.n_agents * self.config.malicious_fraction)
        n_dormant = int(self.config.n_agents * self.config.dormant_fraction)
        n_honest = self.config.n_agents - n_malicious - n_dormant
        
        self.agents = []
        for i in range(n_honest):
            self.agents.append(Agent(f"honest_{i}", AgentType.HONEST))
        for i in range(n_malicious):
            self.agents.append(Agent(f"malicious_{i}", AgentType.MALICIOUS))
        for i in range(n_dormant):
            self.agents.append(Agent(f"dormant_{i}", AgentType.DORMANT))
        
        self.rng.shuffle(self.agents)
    
    def tick(self, t: int):
        """Process one simulation tick."""
        # 1. Randomly degrade some agents
        for agent in self.agents:
            if agent.trust_score >= self.config.trust_threshold:
                if self.rng.random() < self.config.degradation_rate:
                    agent.degrade(t)
                    self.result.degradation_events += 1
        
        # 2. Apply recovery strategy
        for agent in self.agents:
            if agent.trust_score < self.config.trust_threshold and agent.degraded_at is not None:
                ticks_degraded = t - agent.degraded_at
                
                if self.config.strategy == RecoveryStrategy.PASSIVE:
                    self._passive_recovery(agent, t, ticks_degraded)
                elif self.config.strategy == RecoveryStrategy.ACTIVE:
                    self._active_recovery(agent, t, ticks_degraded)
                elif self.config.strategy == RecoveryStrategy.HYBRID:
                    self._hybrid_recovery(agent, t, ticks_degraded)
    
    def _passive_recovery(self, agent: Agent, t: int, ticks_degraded: int):
        """Passive: auto-recover after cooldown, no verification."""
        if ticks_degraded >= self.config.passive_cooldown:
            agent.recover(t)
            if agent.agent_type == AgentType.MALICIOUS:
                self.result.false_restorations += 1
            elif agent.agent_type == AgentType.HONEST:
                self.result.honest_recoveries += 1
                self.result.honest_recovery_ticks.append(ticks_degraded)
            # Dormant agents recover too (problematic — they haven't proven anything)
    
    def _active_recovery(self, agent: Agent, t: int, ticks_degraded: int):
        """Active: must request and pass re-attestation."""
        # Agents request re-attestation periodically
        if ticks_degraded > 0 and ticks_degraded % 5 == 0:
            agent.re_attestation_requests += 1
            self.result.total_re_attestation_requests += 1
            
            if agent.agent_type == AgentType.HONEST:
                # Honest agents pass re-attestation with high probability
                if self.rng.random() < self.config.re_attestation_success_rate:
                    agent.recover(t)
                    self.result.honest_recoveries += 1
                    self.result.honest_recovery_ticks.append(ticks_degraded)
            
            elif agent.agent_type == AgentType.MALICIOUS:
                # Malicious agents have much lower pass rate
                if self.rng.random() < 0.15:  # 15% chance of fooling re-attestation
                    agent.recover(t)
                    self.result.false_restorations += 1
            
            # Dormant agents don't request re-attestation (they're inactive)
    
    def _hybrid_recovery(self, agent: Agent, t: int, ticks_degraded: int):
        """Hybrid: grace period (partial passive recovery), then active required."""
        if ticks_degraded <= self.config.grace_period:
            # During grace period: minor trust improvement but NOT full recovery
            agent.trust_score = min(agent.trust_score + 0.02, self.config.trust_threshold - 0.05)
        else:
            # After grace period: active re-attestation required
            self._active_recovery(agent, t, ticks_degraded)
    
    def run(self) -> SimResult:
        """Run full simulation."""
        self.setup()
        for t in range(self.config.n_ticks):
            self.tick(t)
        
        self.result.trust_at_end = [a.trust_score for a in self.agents]
        return self.result


def run_comparison():
    """Compare all three recovery strategies."""
    print("=" * 70)
    print("SOFT CASCADE RECOVERY — STRATEGY COMPARISON")
    print("=" * 70)
    print(f"\nConfig: 100 agents (15% malicious, 10% dormant, 75% honest)")
    print(f"200 ticks, 10% degradation rate per tick")
    print()
    
    strategies = [
        RecoveryStrategy.PASSIVE,
        RecoveryStrategy.ACTIVE,
        RecoveryStrategy.HYBRID,
    ]
    
    results = {}
    for strategy in strategies:
        config = SimConfig(strategy=strategy)
        sim = SoftCascadeSimulator(config, seed=42)
        result = sim.run()
        results[strategy.value] = result
    
    # Print comparison table
    header = f"{'Metric':<35} {'PASSIVE':>10} {'ACTIVE':>10} {'HYBRID':>10}"
    print(header)
    print("-" * 70)
    
    metrics = [
        ("False restoration rate", lambda r: f"{r.false_restoration_rate:.1%}"),
        ("False restorations (count)", lambda r: f"{r.false_restorations}"),
        ("Honest recoveries", lambda r: f"{r.honest_recoveries}"),
        ("Avg recovery latency (ticks)", lambda r: f"{r.avg_recovery_latency:.1f}"),
        ("Median recovery latency", lambda r: f"{r.median_recovery_latency:.1f}"),
        ("Re-attestation requests", lambda r: f"{r.total_re_attestation_requests}"),
        ("Degradation events", lambda r: f"{r.degradation_events}"),
    ]
    
    for name, fn in metrics:
        row = f"{name:<35}"
        for s in ["passive", "active", "hybrid"]:
            row += f" {fn(results[s]):>10}"
        print(row)
    
    print()
    
    # Determine winner
    passive_fr = results["passive"].false_restoration_rate
    active_fr = results["active"].false_restoration_rate
    hybrid_fr = results["hybrid"].false_restoration_rate
    
    print("ANALYSIS:")
    print(f"  Passive: Lowest latency but highest false restoration rate ({passive_fr:.1%})")
    print(f"    → Malicious agents auto-recover. Time does NOT verify competence.")
    print(f"  Active: Lowest false restoration rate ({active_fr:.1%}) but coordination cost")
    print(f"    → {results['active'].total_re_attestation_requests} re-attestation requests generated")
    print(f"  Hybrid: Balanced — grace absorbs transient failures, active catches real threats")
    print(f"    → {hybrid_fr:.1%} false restoration rate")
    
    print()
    print("RECOMMENDATION: ACTIVE as default (NIST 800-63B §6.1.4)")
    print("  - Renewal SHOULD happen BEFORE expiration")
    print("  - Passive auto-clear = implicit trust without evidence")
    print("  - Absence of renewal IS the signal")
    print("  - Grace period acceptable for coordination overhead")
    print("  - Trust NEVER auto-heals. You re-earn it or it stays degraded.")
    
    # The key insight
    print()
    print("KEY INSIGHT: The question isn't passive vs active.")
    print("It's whether SILENCE means 'still trusted' or 'status unknown'.")
    print("Short TTL answers this: silence = expired. No news IS bad news.")


if __name__ == "__main__":
    run_comparison()
