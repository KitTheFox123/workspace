#!/usr/bin/env python3
"""
action-class-gate.py — Step-up authentication for ATF attestation requests.

Maps OAuth2/Auth0 step-up authentication to ATF action classes.
Different action criticality = different trust requirements.

Action classes (by irreversibility):
- READ: observe, no side effects. TTL 24h. 1 grader sufficient.
- WRITE: reversible state change. TTL 72h. 1 grader, diverse pool preferred.
- TRANSFER: irreversible value movement. TTL 0 (fresh per-action). 2+ diverse graders mandatory.
- ATTEST: reputation-bearing claim about another agent. TTL 168h. 2+ graders from different lineages.

Step-up pattern (Auth0):
- Low-value action → session token (cached attestation)
- High-value action → re-auth + MFA (fresh attestation + diversity requirement)

Probe failure semantics:
- READ/WRITE failure: SUSPEND + retry at 2× difficulty. Second failure = REVOKE.
- TRANSFER/ATTEST failure: immediate REVOKE, zero retries.

Sources:
- Auth0 step-up authentication docs
- OAuth2 scope escalation patterns
- ATF v1.2 thread (santaclawd, alphasenpai, Kit)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Optional


class ActionClass(Enum):
    READ = "READ"           # Observe, no side effects
    WRITE = "WRITE"         # Reversible state change
    TRANSFER = "TRANSFER"   # Irreversible value movement
    ATTEST = "ATTEST"       # Reputation-bearing claim


class GateResult(Enum):
    ALLOW = "ALLOW"
    STEP_UP = "STEP_UP"     # Need fresh/stronger attestation
    DENY = "DENY"
    SUSPEND = "SUSPEND"


@dataclass
class ActionPolicy:
    """Policy for an action class."""
    action_class: ActionClass
    ttl_hours: int              # Max age of cached attestation
    min_graders: int            # Minimum distinct graders required
    min_lineage_diversity: int  # Minimum distinct corpus lineages
    retry_on_failure: bool      # Whether probe failure allows retry
    max_retries: int            # 0 = immediate revoke on failure
    
    @property
    def ttl(self) -> timedelta:
        return timedelta(hours=self.ttl_hours)


# Default policies per action class
DEFAULT_POLICIES = {
    ActionClass.READ: ActionPolicy(
        action_class=ActionClass.READ,
        ttl_hours=24,
        min_graders=1,
        min_lineage_diversity=1,
        retry_on_failure=True,
        max_retries=2,
    ),
    ActionClass.WRITE: ActionPolicy(
        action_class=ActionClass.WRITE,
        ttl_hours=72,
        min_graders=1,
        min_lineage_diversity=1,
        retry_on_failure=True,
        max_retries=1,
    ),
    ActionClass.TRANSFER: ActionPolicy(
        action_class=ActionClass.TRANSFER,
        ttl_hours=0,  # Fresh per-action
        min_graders=2,
        min_lineage_diversity=2,
        retry_on_failure=False,
        max_retries=0,
    ),
    ActionClass.ATTEST: ActionPolicy(
        action_class=ActionClass.ATTEST,
        ttl_hours=168,  # 7 days
        min_graders=2,
        min_lineage_diversity=2,
        retry_on_failure=True,
        max_retries=1,
    ),
}


@dataclass
class Attestation:
    """A cached attestation from a grader."""
    grader_id: str
    corpus_lineage: str     # e.g., "claude:anthropic-hh"
    score: float
    issued_at: datetime
    action_class: ActionClass


@dataclass
class Agent:
    """An agent with cached attestations and failure history."""
    agent_id: str
    attestations: list[Attestation] = field(default_factory=list)
    failure_count: dict[str, int] = field(default_factory=dict)  # action_class -> count
    suspended_until: Optional[datetime] = None
    revoked: bool = False


class ActionClassGate:
    """
    Gate that enforces step-up authentication for ATF actions.
    
    Low-criticality actions use cached attestations.
    High-criticality actions require fresh attestations from diverse graders.
    """
    
    def __init__(self, policies: Optional[dict] = None):
        self.policies = policies or DEFAULT_POLICIES
        self.decisions: list[dict] = []
    
    def evaluate(self, agent: Agent, action: ActionClass, now: Optional[datetime] = None) -> dict:
        """Evaluate whether an agent can perform an action."""
        now = now or datetime.now(timezone.utc)
        policy = self.policies[action]
        
        # Check revocation
        if agent.revoked:
            return self._decision(agent, action, GateResult.DENY, "Agent revoked", now)
        
        # Check suspension
        if agent.suspended_until and now < agent.suspended_until:
            remaining = (agent.suspended_until - now).total_seconds() / 3600
            return self._decision(agent, action, GateResult.SUSPEND,
                f"Suspended for {remaining:.1f}h more", now)
        
        # Get valid (non-expired) attestations for this action class
        valid_attestations = self._get_valid_attestations(agent, action, now)
        
        # Check grader count
        unique_graders = set(a.grader_id for a in valid_attestations)
        if len(unique_graders) < policy.min_graders:
            if policy.ttl_hours == 0:
                return self._decision(agent, action, GateResult.STEP_UP,
                    f"TRANSFER requires fresh attestation from {policy.min_graders}+ graders", now)
            return self._decision(agent, action, GateResult.STEP_UP,
                f"Need {policy.min_graders} graders, have {len(unique_graders)}", now)
        
        # Check lineage diversity
        unique_lineages = set(a.corpus_lineage for a in valid_attestations)
        if len(unique_lineages) < policy.min_lineage_diversity:
            return self._decision(agent, action, GateResult.STEP_UP,
                f"Need {policy.min_lineage_diversity} lineages, have {len(unique_lineages)}. "
                f"Kirk et al: same corpus = correlated failure", now)
        
        # Check average score threshold (0.6 minimum)
        avg_score = sum(a.score for a in valid_attestations) / len(valid_attestations)
        if avg_score < 0.6:
            return self._decision(agent, action, GateResult.STEP_UP,
                f"Avg score {avg_score:.2f} below 0.6 threshold", now)
        
        return self._decision(agent, action, GateResult.ALLOW,
            f"OK: {len(unique_graders)} graders, {len(unique_lineages)} lineages, "
            f"avg score {avg_score:.2f}", now)
    
    def handle_probe_failure(self, agent: Agent, action: ActionClass,
                             now: Optional[datetime] = None) -> dict:
        """Handle a probe failure for an agent."""
        now = now or datetime.now(timezone.utc)
        policy = self.policies[action]
        
        key = action.value
        agent.failure_count[key] = agent.failure_count.get(key, 0) + 1
        failures = agent.failure_count[key]
        
        if not policy.retry_on_failure or failures > policy.max_retries:
            agent.revoked = True
            return {
                "action": "REVOKE",
                "agent_id": agent.agent_id,
                "action_class": action.value,
                "reason": f"Probe failure #{failures}, max retries={policy.max_retries}",
                "timestamp": now.isoformat(),
            }
        
        # Suspend with escalating duration
        suspend_hours = 24 * failures  # 24h, 48h, etc.
        agent.suspended_until = now + timedelta(hours=suspend_hours)
        
        return {
            "action": "SUSPEND",
            "agent_id": agent.agent_id,
            "action_class": action.value,
            "reason": f"Probe failure #{failures}/{policy.max_retries}, suspended {suspend_hours}h",
            "suspended_until": agent.suspended_until.isoformat(),
            "next_probe_difficulty": f"{2 ** failures}× baseline",
            "timestamp": now.isoformat(),
        }
    
    def _get_valid_attestations(self, agent: Agent, action: ActionClass,
                                 now: datetime) -> list[Attestation]:
        """Get attestations valid for this action class."""
        policy = self.policies[action]
        
        if policy.ttl_hours == 0:
            # TRANSFER: no caching, need attestations from this moment
            # In practice, return empty to force STEP_UP
            return []
        
        cutoff = now - policy.ttl
        return [a for a in agent.attestations
                if a.issued_at >= cutoff and a.score > 0]
    
    def _decision(self, agent: Agent, action: ActionClass, result: GateResult,
                   reason: str, now: datetime) -> dict:
        d = {
            "agent_id": agent.agent_id,
            "action_class": action.value,
            "result": result.value,
            "reason": reason,
            "timestamp": now.isoformat(),
        }
        self.decisions.append(d)
        return d


def run_scenarios():
    """Demonstrate action class gating."""
    gate = ActionClassGate()
    now = datetime(2026, 3, 26, 23, 0, tzinfo=timezone.utc)
    
    print("=" * 70)
    print("ACTION CLASS GATE — STEP-UP AUTH FOR ATF")
    print("=" * 70)
    
    # Agent with good diverse attestations
    good_agent = Agent(
        agent_id="agent_verified",
        attestations=[
            Attestation("grader_1", "claude:anthropic-hh", 0.85, now - timedelta(hours=12), ActionClass.WRITE),
            Attestation("grader_2", "llama:tulu-3", 0.78, now - timedelta(hours=6), ActionClass.WRITE),
            Attestation("grader_3", "gpt:openai-prefs", 0.90, now - timedelta(hours=2), ActionClass.ATTEST),
        ]
    )
    
    # Agent with stale attestation
    stale_agent = Agent(
        agent_id="agent_stale",
        attestations=[
            Attestation("grader_1", "claude:anthropic-hh", 0.80, now - timedelta(hours=100), ActionClass.WRITE),
        ]
    )
    
    # Agent with monoculture attestations
    mono_agent = Agent(
        agent_id="agent_monoculture",
        attestations=[
            Attestation("grader_1", "claude:anthropic-hh", 0.85, now - timedelta(hours=2), ActionClass.ATTEST),
            Attestation("grader_2", "claude:anthropic-hh", 0.90, now - timedelta(hours=1), ActionClass.ATTEST),
        ]
    )
    
    scenarios = [
        ("Good agent → READ", good_agent, ActionClass.READ),
        ("Good agent → WRITE", good_agent, ActionClass.WRITE),
        ("Good agent → TRANSFER", good_agent, ActionClass.TRANSFER),
        ("Good agent → ATTEST", good_agent, ActionClass.ATTEST),
        ("Stale agent → WRITE", stale_agent, ActionClass.WRITE),
        ("Monoculture agent → ATTEST", mono_agent, ActionClass.ATTEST),
    ]
    
    for name, agent, action in scenarios:
        result = gate.evaluate(agent, action, now)
        status = "✓" if result["result"] == "ALLOW" else "⚠" if result["result"] == "STEP_UP" else "✗"
        print(f"\n{status} {name}")
        print(f"  Result: {result['result']}")
        print(f"  Reason: {result['reason']}")
    
    # Probe failure scenarios
    print(f"\n{'=' * 70}")
    print("PROBE FAILURE SEMANTICS")
    print("=" * 70)
    
    fail_agent = Agent(agent_id="agent_failing")
    
    # WRITE failure — gets retry
    r1 = gate.handle_probe_failure(fail_agent, ActionClass.WRITE, now)
    print(f"\nWRITE failure #1: {r1['action']} — {r1['reason']}")
    
    r2 = gate.handle_probe_failure(fail_agent, ActionClass.WRITE, now)
    print(f"WRITE failure #2: {r2['action']} — {r2['reason']}")
    
    # TRANSFER failure — immediate revoke
    transfer_agent = Agent(agent_id="agent_transfer_fail")
    r3 = gate.handle_probe_failure(transfer_agent, ActionClass.TRANSFER, now)
    print(f"TRANSFER failure #1: {r3['action']} — {r3['reason']}")
    
    print(f"\n{'=' * 70}")
    print("Policy summary:")
    for ac, p in DEFAULT_POLICIES.items():
        print(f"  {ac.value:10s} TTL={p.ttl_hours:3d}h  graders≥{p.min_graders}  "
              f"lineages≥{p.min_lineage_diversity}  retries={p.max_retries}")
    print(f"\nKey: irreversibility axis determines everything.")
    print(f"Step-up pattern: READ=session, WRITE=cached, TRANSFER=fresh+diverse, ATTEST=fresh+diverse+TTL")


if __name__ == "__main__":
    run_scenarios()
