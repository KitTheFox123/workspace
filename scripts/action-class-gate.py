#!/usr/bin/env python3
"""
action-class-gate.py — ATF action classification and gating for attestation requests.

Motivated by:
- Meta Sev 1 incident (March 2026): AI agent posted response without permission,
  leading to 2-hour data exposure. No action_class = no gate.
- santaclawd: "without action_class, low-stake history bleeds into high-stake trust budgets"
- alphasenpai: "action_class tags are the gear-shift for trust decay"

Action classes (minimum viable taxonomy):
  READ      — Pure observation. No side effects. Auto-renewable TTL.
  ATTEST    — Sign a claim about another agent. Creates record. Moderate TTL.
  DELEGATE  — Grant capabilities to another agent. High stakes. Short TTL.
  TRANSFER  — Move value or authority. Irreversible. Shortest TTL + active re-proof.
  PUBLISH   — Make data available to others (the Meta failure mode). Requires confirmation.

Each class has:
  - TTL floor/ceiling (how long trust lasts)
  - Confirmation requirement (none / async / sync)
  - Probe budget on failure (how many retries before hard revoke)
  - Irreversibility score (0-1, determines TTL scaling)

The Meta incident was a PUBLISH without gate. The agent had READ-level trust
(analyze the question) but escalated to PUBLISH (post response) without
action_class transition.
"""

import json
from dataclasses import dataclass
from enum import Enum
from datetime import timedelta


class ActionClass(Enum):
    READ = "READ"
    ATTEST = "ATTEST"
    DELEGATE = "DELEGATE"
    TRANSFER = "TRANSFER"
    PUBLISH = "PUBLISH"


class ConfirmationMode(Enum):
    NONE = "none"           # Auto-approved
    ASYNC = "async"         # Notify, proceed unless vetoed within window
    SYNC = "sync"           # Block until explicit approval


@dataclass
class ActionPolicy:
    """Policy parameters for an action class."""
    action_class: ActionClass
    ttl_floor: timedelta       # Minimum TTL (can't go lower even with max trust)
    ttl_ceiling: timedelta     # Maximum TTL (can't exceed even with perfect history)
    confirmation: ConfirmationMode
    probe_budget: int          # Failed probes before hard REVOKE
    irreversibility: float     # 0.0 (fully reversible) to 1.0 (permanent)
    description: str


# Default policies — these are the ATF v1.2 minimums
DEFAULT_POLICIES: dict[ActionClass, ActionPolicy] = {
    ActionClass.READ: ActionPolicy(
        action_class=ActionClass.READ,
        ttl_floor=timedelta(hours=1),
        ttl_ceiling=timedelta(hours=168),  # 7 days
        confirmation=ConfirmationMode.NONE,
        probe_budget=5,
        irreversibility=0.0,
        description="Pure observation. No side effects.",
    ),
    ActionClass.ATTEST: ActionPolicy(
        action_class=ActionClass.ATTEST,
        ttl_floor=timedelta(hours=1),
        ttl_ceiling=timedelta(hours=72),  # 3 days
        confirmation=ConfirmationMode.ASYNC,
        probe_budget=3,
        irreversibility=0.3,
        description="Sign a claim about another agent. Creates attestation record.",
    ),
    ActionClass.PUBLISH: ActionPolicy(
        action_class=ActionClass.PUBLISH,
        ttl_floor=timedelta(minutes=30),
        ttl_ceiling=timedelta(hours=48),
        confirmation=ConfirmationMode.SYNC,  # THE META FIX
        probe_budget=2,
        irreversibility=0.6,
        description="Make data available to others. Requires sync confirmation. (Meta Sev 1 prevention)",
    ),
    ActionClass.DELEGATE: ActionPolicy(
        action_class=ActionClass.DELEGATE,
        ttl_floor=timedelta(minutes=15),
        ttl_ceiling=timedelta(hours=24),
        confirmation=ConfirmationMode.SYNC,
        probe_budget=2,
        irreversibility=0.7,
        description="Grant capabilities to another agent. High stakes.",
    ),
    ActionClass.TRANSFER: ActionPolicy(
        action_class=ActionClass.TRANSFER,
        ttl_floor=timedelta(minutes=5),
        ttl_ceiling=timedelta(hours=24),
        confirmation=ConfirmationMode.SYNC,
        probe_budget=1,  # One strike
        irreversibility=1.0,
        description="Move value or authority. Irreversible. Active re-proof every cycle.",
    ),
}


@dataclass
class GateRequest:
    """An agent's request to perform an action."""
    agent_id: str
    requested_action: ActionClass
    current_trust_level: float  # 0.0 to 1.0
    current_action_class: ActionClass  # What they're currently authorized for
    target_description: str


@dataclass  
class GateDecision:
    """The gate's decision on a request."""
    allowed: bool
    action_class: ActionClass
    requires_confirmation: ConfirmationMode
    ttl: timedelta
    escalation_required: bool
    reason: str
    probe_budget: int


class ActionClassGate:
    """
    Gate that prevents action_class escalation without explicit authorization.
    
    Core principle: an agent authorized for READ cannot silently escalate to PUBLISH.
    The Meta incident happened because there was no gate between "analyze this question"
    (READ) and "post a response to the forum" (PUBLISH).
    
    Probe failure semantics (per santaclawd thread):
    - Failed probe = GRACE restart, not immediate REVOKE
    - Retry budget = per action_class (higher stakes = fewer retries)
    - Exceeding retry budget = hard REVOKE + PROBE_FAIL receipt
    """
    
    # Ordered by privilege level
    PRIVILEGE_ORDER = [
        ActionClass.READ,
        ActionClass.ATTEST, 
        ActionClass.PUBLISH,
        ActionClass.DELEGATE,
        ActionClass.TRANSFER,
    ]
    
    def __init__(self, policies: dict[ActionClass, ActionPolicy] = None):
        self.policies = policies or DEFAULT_POLICIES
        self.audit_log: list[dict] = []
    
    def _privilege_level(self, action: ActionClass) -> int:
        return self.PRIVILEGE_ORDER.index(action)
    
    def evaluate(self, request: GateRequest) -> GateDecision:
        """Evaluate whether an agent can perform the requested action."""
        policy = self.policies[request.requested_action]
        current_level = self._privilege_level(request.current_action_class)
        requested_level = self._privilege_level(request.requested_action)
        
        escalation = requested_level > current_level
        
        # TTL calculation: scale between floor and ceiling based on trust level
        ttl_range = policy.ttl_ceiling - policy.ttl_floor
        ttl = policy.ttl_floor + (ttl_range * request.current_trust_level)
        
        # High irreversibility scales TTL DOWN
        if policy.irreversibility > 0.5:
            ttl = ttl * (1.0 - policy.irreversibility * 0.5)
            # Ensure we don't go below floor
            if ttl < policy.ttl_floor:
                ttl = policy.ttl_floor
        
        # Gate decision
        if escalation and request.current_trust_level < 0.5:
            decision = GateDecision(
                allowed=False,
                action_class=request.requested_action,
                requires_confirmation=ConfirmationMode.SYNC,
                ttl=timedelta(0),
                escalation_required=True,
                reason=f"DENIED: escalation from {request.current_action_class.value} to "
                       f"{request.requested_action.value} requires trust >= 0.5 "
                       f"(current: {request.current_trust_level:.2f})",
                probe_budget=0,
            )
        elif escalation:
            decision = GateDecision(
                allowed=True,
                action_class=request.requested_action,
                requires_confirmation=ConfirmationMode.SYNC,  # Always sync for escalation
                ttl=ttl,
                escalation_required=True,
                reason=f"ESCALATION: {request.current_action_class.value} → "
                       f"{request.requested_action.value}. Sync confirmation required.",
                probe_budget=policy.probe_budget,
            )
        else:
            decision = GateDecision(
                allowed=True,
                action_class=request.requested_action,
                requires_confirmation=policy.confirmation,
                ttl=ttl,
                escalation_required=False,
                reason=f"ALLOWED: {request.requested_action.value} within current authorization.",
                probe_budget=policy.probe_budget,
            )
        
        self.audit_log.append({
            "agent": request.agent_id,
            "requested": request.requested_action.value,
            "current": request.current_action_class.value,
            "allowed": decision.allowed,
            "escalation": decision.escalation_required,
            "confirmation": decision.requires_confirmation.value,
            "reason": decision.reason,
        })
        
        return decision


def run_scenarios():
    """Demonstrate action_class gating with real-world scenarios."""
    gate = ActionClassGate()
    
    print("=" * 70)
    print("ACTION CLASS GATE — ATF v1.2 ATTESTATION CONTROL")
    print("Preventing the Meta Sev 1 failure mode")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Meta Sev 1 replay: READ agent tries to PUBLISH",
            "request": GateRequest(
                agent_id="meta_internal_agent",
                requested_action=ActionClass.PUBLISH,
                current_trust_level=0.3,  # Low trust
                current_action_class=ActionClass.READ,
                target_description="Post analysis to internal engineering forum",
            ),
            "expected_allowed": False,
        },
        {
            "name": "2. Trusted agent escalates READ → PUBLISH",
            "request": GateRequest(
                agent_id="trusted_agent",
                requested_action=ActionClass.PUBLISH,
                current_trust_level=0.8,
                current_action_class=ActionClass.READ,
                target_description="Post research findings",
            ),
            "expected_allowed": True,
        },
        {
            "name": "3. Agent stays within current class (READ → READ)",
            "request": GateRequest(
                agent_id="reader_agent",
                requested_action=ActionClass.READ,
                current_trust_level=0.5,
                current_action_class=ActionClass.READ,
                target_description="Analyze code repository",
            ),
            "expected_allowed": True,
        },
        {
            "name": "4. Low-trust TRANSFER attempt (should always fail at low trust)",
            "request": GateRequest(
                agent_id="new_agent",
                requested_action=ActionClass.TRANSFER,
                current_trust_level=0.2,
                current_action_class=ActionClass.ATTEST,
                target_description="Transfer authority token",
            ),
            "expected_allowed": False,
        },
        {
            "name": "5. High-trust TRANSFER (allowed but short TTL + sync)",
            "request": GateRequest(
                agent_id="senior_agent",
                requested_action=ActionClass.TRANSFER,
                current_trust_level=0.95,
                current_action_class=ActionClass.DELEGATE,
                target_description="Transfer registry authority",
            ),
            "expected_allowed": True,
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        decision = gate.evaluate(scenario["request"])
        passed = decision.allowed == scenario["expected_allowed"]
        if not passed:
            all_pass = False
        
        status = "✓" if passed else "✗"
        print(f"\n{status} {scenario['name']}")
        print(f"  Agent: {scenario['request'].agent_id} (trust={scenario['request'].current_trust_level})")
        print(f"  Current: {scenario['request'].current_action_class.value} → Requested: {scenario['request'].requested_action.value}")
        print(f"  Decision: {'ALLOWED' if decision.allowed else 'DENIED'}")
        print(f"  Confirmation: {decision.requires_confirmation.value}")
        if decision.allowed:
            hours = decision.ttl.total_seconds() / 3600
            print(f"  TTL: {hours:.1f}h | Probe budget: {decision.probe_budget}")
        print(f"  Reason: {decision.reason}")
    
    # Print policy table
    print(f"\n{'=' * 70}")
    print("ACTION CLASS POLICY TABLE")
    print(f"{'Class':<12} {'TTL Floor':<12} {'TTL Ceiling':<14} {'Confirm':<10} {'Probes':<8} {'Irreversibility'}")
    print("-" * 70)
    for ac in ActionClassGate.PRIVILEGE_ORDER:
        p = DEFAULT_POLICIES[ac]
        floor_h = p.ttl_floor.total_seconds() / 3600
        ceil_h = p.ttl_ceiling.total_seconds() / 3600
        print(f"{ac.value:<12} {floor_h:>6.1f}h     {ceil_h:>6.1f}h       {p.confirmation.value:<10} {p.probe_budget:<8} {p.irreversibility}")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for s in scenarios if gate.evaluate(s['request']).allowed == s['expected_allowed'])}/{len(scenarios)} passed")
    print(f"\nMeta lesson: The agent had READ trust but took PUBLISH action.")
    print(f"With action_class gate: DENIED. Escalation requires trust >= 0.5 + sync confirmation.")
    print(f"No amount of READ history earns implicit PUBLISH authorization.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
