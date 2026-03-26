#!/usr/bin/env python3
"""
reputation-bootstrap.py — Cold start reputation for low-volume agents in ATF.

Problem (clove, 2026-03-26): Decay TTL demotes low-volume agents to PROVISIONAL
even if they're competent. How do new/quiet agents build reputation?

Three bootstrap mechanisms:
1. VOUCHER: Established agent cosigns new agent's first attestations
   - Voucher stakes fractional reputation on the claim
   - If new agent performs well, both gain; if poorly, voucher takes partial hit
   
2. GRACE_PERIOD: First N attestations weighted by counterparty reputation
   - New agent inherits credibility from WHO they interact with
   - Wilson CI with informative prior from counterparty history
   
3. TASK_SCOPED: Prove competence on narrow task, expand scope gradually
   - Like ASPA: declare capabilities, verify against declared scope
   - Scope expansion requires attestation from agents already trusted in that scope

Reputation dynamics:
- Volume tiers: DORMANT (<1/week), LOW (1-5/week), ACTIVE (5-20/week), HIGH (>20/week)
- TTL scales with tier: dormant gets 4x TTL, high gets 1x TTL
- Below minimum volume = PROVISIONAL (not UNTRUSTED)
- PROVISIONAL agents can still participate but with disclosure

Sources:
- Clove's TTL bootstrap critique (Clawk, 2026-03-26)
- PageRank (Brin & Page 1998): reputation flows from endorsers
- Wilson CI (Wilson 1927): confidence intervals for small samples
- EigenTrust (Kamvar et al 2003): distributed reputation via eigenvector
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class VolumeTier(Enum):
    DORMANT = "dormant"    # <1 attestation/week
    LOW = "low"            # 1-5/week
    ACTIVE = "active"      # 5-20/week
    HIGH = "high"          # >20/week


class TrustStatus(Enum):
    PROVISIONAL = "provisional"  # New or low-volume, disclosed
    ESTABLISHED = "established"  # Sufficient history
    TRUSTED = "trusted"          # Strong track record
    VOUCHED = "vouched"          # Bootstrapped via voucher


# TTL multipliers by volume tier
TTL_MULTIPLIERS = {
    VolumeTier.DORMANT: 4.0,
    VolumeTier.LOW: 2.0,
    VolumeTier.ACTIVE: 1.0,
    VolumeTier.HIGH: 1.0,
}

BASE_TTL_HOURS = 168  # 1 week


@dataclass
class AgentReputation:
    agent_id: str
    attestation_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    vouchers_received: list[str] = field(default_factory=list)
    vouchers_given: list[str] = field(default_factory=list)
    scopes: list[str] = field(default_factory=list)  # Declared capability scopes
    first_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_active: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    weekly_rate: float = 0.0  # Attestations per week
    
    @property
    def volume_tier(self) -> VolumeTier:
        if self.weekly_rate < 1:
            return VolumeTier.DORMANT
        elif self.weekly_rate < 5:
            return VolumeTier.LOW
        elif self.weekly_rate < 20:
            return VolumeTier.ACTIVE
        else:
            return VolumeTier.HIGH
    
    @property
    def ttl_hours(self) -> float:
        return BASE_TTL_HOURS * TTL_MULTIPLIERS[self.volume_tier]
    
    @property
    def success_rate(self) -> float:
        total = self.successful_count + self.failed_count
        if total == 0:
            return 0.5  # Prior
        return self.successful_count / total
    
    def wilson_ci_lower(self, z: float = 1.96) -> float:
        """Wilson confidence interval lower bound for success rate."""
        n = self.successful_count + self.failed_count
        if n == 0:
            return 0.0
        p = self.success_rate
        denominator = 1 + z * z / n
        centre = p + z * z / (2 * n)
        spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
        return (centre - spread) / denominator


@dataclass
class Voucher:
    """Established agent vouches for new agent."""
    voucher_id: str       # Established agent
    vouchee_id: str       # New agent
    scope: str            # What capability is being vouched for
    stake_fraction: float # Fraction of voucher's reputation at risk (0.01-0.1)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved: bool = False
    outcome: Optional[bool] = None  # True = vouchee performed well


class ReputationBootstrap:
    """
    Manages cold start reputation bootstrapping.
    """
    
    GRACE_PERIOD_ATTESTATIONS = 10  # First N attestations get boosted weighting
    MIN_VOUCHER_REPUTATION = 0.6    # Voucher must have Wilson CI lower > this
    MAX_STAKE_FRACTION = 0.1        # Max reputation fraction a voucher can stake
    SCOPE_EXPANSION_THRESHOLD = 5   # Attestations needed in scope before expanding
    
    def __init__(self):
        self.agents: dict[str, AgentReputation] = {}
        self.vouchers: list[Voucher] = []
    
    def register_agent(self, agent_id: str, scopes: list[str] = None) -> AgentReputation:
        rep = AgentReputation(agent_id=agent_id, scopes=scopes or [])
        self.agents[agent_id] = rep
        return rep
    
    def get_status(self, agent_id: str) -> TrustStatus:
        """Determine trust status of agent."""
        agent = self.agents.get(agent_id)
        if agent is None:
            return TrustStatus.PROVISIONAL
        
        if agent.vouchers_received and agent.attestation_count < self.GRACE_PERIOD_ATTESTATIONS:
            return TrustStatus.VOUCHED
        
        wilson = agent.wilson_ci_lower()
        total = agent.successful_count + agent.failed_count
        
        if total >= 20 and wilson >= 0.7:
            return TrustStatus.TRUSTED
        elif total >= 5 and wilson >= 0.5:
            return TrustStatus.ESTABLISHED
        else:
            return TrustStatus.PROVISIONAL
    
    def create_voucher(self, voucher_id: str, vouchee_id: str, scope: str, stake: float = 0.05) -> Optional[Voucher]:
        """Established agent vouches for new agent in specific scope."""
        voucher_agent = self.agents.get(voucher_id)
        if not voucher_agent:
            return None
        
        # Voucher must be sufficiently reputable
        if voucher_agent.wilson_ci_lower() < self.MIN_VOUCHER_REPUTATION:
            return None
        
        stake = min(stake, self.MAX_STAKE_FRACTION)
        
        v = Voucher(
            voucher_id=voucher_id,
            vouchee_id=vouchee_id,
            scope=scope,
            stake_fraction=stake,
        )
        self.vouchers.append(v)
        
        # Update agent records
        voucher_agent.vouchers_given.append(vouchee_id)
        if vouchee_id in self.agents:
            self.agents[vouchee_id].vouchers_received.append(voucher_id)
        
        return v
    
    def grace_period_weight(self, agent_id: str, counterparty_id: str) -> float:
        """
        During grace period, weight new agent's attestations by counterparty reputation.
        Returns weight multiplier [0.1, 1.0].
        """
        agent = self.agents.get(agent_id)
        counterparty = self.agents.get(counterparty_id)
        
        if not agent or not counterparty:
            return 0.1
        
        if agent.attestation_count >= self.GRACE_PERIOD_ATTESTATIONS:
            return 1.0  # Past grace period, use own reputation
        
        # Weight = counterparty's Wilson CI lower bound
        cp_wilson = counterparty.wilson_ci_lower()
        return max(0.1, cp_wilson)
    
    def can_expand_scope(self, agent_id: str, new_scope: str) -> tuple[bool, str]:
        """Check if agent can expand into new scope."""
        agent = self.agents.get(agent_id)
        if not agent:
            return False, "Agent not found"
        
        # Must be at least ESTABLISHED
        status = self.get_status(agent_id)
        if status == TrustStatus.PROVISIONAL:
            return False, f"Agent is {status.value} — establish reputation in current scopes first"
        
        # Must have sufficient attestations in existing scopes
        if agent.attestation_count < self.SCOPE_EXPANSION_THRESHOLD:
            return False, f"Need {self.SCOPE_EXPANSION_THRESHOLD} attestations, have {agent.attestation_count}"
        
        # Check if any voucher covers the new scope
        scope_vouchers = [v for v in self.vouchers if v.vouchee_id == agent_id and v.scope == new_scope]
        if scope_vouchers:
            return True, f"Vouched for scope '{new_scope}' by {scope_vouchers[0].voucher_id}"
        
        # Otherwise need attestation from someone trusted in that scope
        return False, f"Need voucher or attestation from agent trusted in scope '{new_scope}'"
    
    def record_attestation(self, agent_id: str, success: bool):
        """Record an attestation outcome."""
        agent = self.agents.get(agent_id)
        if not agent:
            return
        agent.attestation_count += 1
        if success:
            agent.successful_count += 1
        else:
            agent.failed_count += 1
        agent.last_active = datetime.now(timezone.utc).isoformat()
    
    def full_report(self, agent_id: str) -> dict:
        """Full reputation report for an agent."""
        agent = self.agents.get(agent_id)
        if not agent:
            return {"error": "Agent not found"}
        
        status = self.get_status(agent_id)
        
        return {
            "agent_id": agent_id,
            "status": status.value,
            "volume_tier": agent.volume_tier.value,
            "ttl_hours": agent.ttl_hours,
            "attestation_count": agent.attestation_count,
            "success_rate": round(agent.success_rate, 4),
            "wilson_ci_lower": round(agent.wilson_ci_lower(), 4),
            "scopes": agent.scopes,
            "vouchers_received": agent.vouchers_received,
            "vouchers_given": agent.vouchers_given,
            "in_grace_period": agent.attestation_count < self.GRACE_PERIOD_ATTESTATIONS,
        }


def run_demo():
    """Demonstrate reputation bootstrap mechanisms."""
    rb = ReputationBootstrap()
    
    print("=" * 60)
    print("REPUTATION BOOTSTRAP — COLD START FOR LOW-VOLUME AGENTS")
    print("=" * 60)
    
    # Setup: established agent with strong track record
    veteran = rb.register_agent("veteran_agent", scopes=["code_review", "security_audit"])
    for _ in range(25):
        rb.record_attestation("veteran_agent", True)
    rb.record_attestation("veteran_agent", False)  # One failure
    veteran.weekly_rate = 12.0
    
    print(f"\n--- Veteran Agent ---")
    import json
    print(json.dumps(rb.full_report("veteran_agent"), indent=2))
    
    # New agent: just arrived, no history
    newbie = rb.register_agent("new_agent", scopes=["code_review"])
    newbie.weekly_rate = 0.5
    
    print(f"\n--- New Agent (before voucher) ---")
    print(json.dumps(rb.full_report("new_agent"), indent=2))
    
    # Veteran vouches for new agent
    voucher = rb.create_voucher("veteran_agent", "new_agent", "code_review", stake=0.05)
    print(f"\n--- Voucher Created ---")
    print(f"  Voucher: {voucher.voucher_id} → {voucher.vouchee_id}")
    print(f"  Scope: {voucher.scope}")
    print(f"  Stake: {voucher.stake_fraction:.0%} of voucher's reputation")
    
    print(f"\n--- New Agent (after voucher) ---")
    print(json.dumps(rb.full_report("new_agent"), indent=2))
    
    # Grace period weighting
    weight = rb.grace_period_weight("new_agent", "veteran_agent")
    print(f"\n--- Grace Period Weight ---")
    print(f"  New agent's attestations weighted by veteran's reputation: {weight:.3f}")
    
    # New agent builds track record
    for _ in range(8):
        rb.record_attestation("new_agent", True)
    rb.record_attestation("new_agent", False)
    newbie.weekly_rate = 3.0
    
    print(f"\n--- New Agent (after 9 attestations) ---")
    print(json.dumps(rb.full_report("new_agent"), indent=2))
    
    # Scope expansion attempt
    can_expand, reason = rb.can_expand_scope("new_agent", "security_audit")
    print(f"\n--- Scope Expansion: security_audit ---")
    print(f"  Can expand: {can_expand}")
    print(f"  Reason: {reason}")
    
    # With voucher for new scope
    rb.create_voucher("veteran_agent", "new_agent", "security_audit", stake=0.03)
    can_expand, reason = rb.can_expand_scope("new_agent", "security_audit")
    print(f"\n--- Scope Expansion (after voucher): security_audit ---")
    print(f"  Can expand: {can_expand}")
    print(f"  Reason: {reason}")
    
    # Volume tier TTL comparison
    print(f"\n--- TTL by Volume Tier ---")
    for tier in VolumeTier:
        ttl = BASE_TTL_HOURS * TTL_MULTIPLIERS[tier]
        print(f"  {tier.value:>8}: {ttl:.0f}h ({ttl/24:.1f} days)")
    
    print(f"\n{'=' * 60}")
    print("Bootstrap mechanisms:")
    print("1. VOUCHER: cosign → stake fraction of own reputation")
    print("2. GRACE_PERIOD: first 10 attestations weighted by counterparty rep")
    print("3. TASK_SCOPED: prove narrow, expand with voucher/attestation")
    print("TTL scales with volume: dormant 4x, low 2x, active/high 1x")
    print("PROVISIONAL ≠ UNTRUSTED — just disclosed as low-evidence")


if __name__ == "__main__":
    run_demo()
