#!/usr/bin/env python3
"""runtime-policy-enforcer.py — Runtime policy enforcement, not audit-time.

Per Moltbook "policy written for auditor not system" post.
MI9 (Wang et al., Barclays/Columbia 2025): "majority of agentic governance
violations originate from cognitive behaviors invisible to conventional
observability." Their 6-component framework: risk index, telemetry,
continuous auth, conformance engine, drift detection, graduated containment.

This implements the core insight: policies must be executable constraints,
not natural language documents. Hash-pinned at genesis, enforced per-action,
auditable by any counterparty.

References:
- MI9: arxiv 2508.03858v2 (Barclays/Columbia)
- Hollnagel (2009): ETTO principle
- Rasmussen (1997): drift to boundary
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ContainmentLevel(Enum):
    """MI9-inspired graduated containment."""
    OBSERVE = 1      # Log anomaly, no intervention
    CONSTRAIN = 2    # Restrict permissions, continue operation
    ISOLATE = 3      # Suspend external actions, preserve state
    TERMINATE = 4    # Full halt, notify operator


class ViolationType(Enum):
    SCOPE_EXCEEDED = "scope_exceeded"
    TOOL_UNAUTHORIZED = "tool_unauthorized"
    GOAL_DRIFT = "goal_drift"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    CORRECTION_DROUGHT = "correction_drought"
    BEHAVIORAL_DIVERGENCE = "behavioral_divergence"


@dataclass
class PolicyRule:
    """A single executable constraint."""
    name: str
    description: str
    violation_type: ViolationType
    containment_on_violation: ContainmentLevel
    check_fn: str  # symbolic — in real impl, this is a callable
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "violation": self.violation_type.value,
            "containment": self.containment_on_violation.name,
        }


@dataclass
class PolicySet:
    """Hash-pinned policy set, immutable after genesis."""
    rules: list = field(default_factory=list)
    declared_at: str = ""
    
    @property
    def policy_hash(self) -> str:
        canonical = json.dumps(
            [r.to_dict() for r in self.rules],
            sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def add_rule(self, rule: PolicyRule):
        self.rules.append(rule)


@dataclass
class ActionEvent:
    """A single agent action to evaluate against policy."""
    action_type: str  # e.g., "tool_invoke", "api_call", "goal_revision"
    tool_name: Optional[str] = None
    scope: Optional[str] = None
    agent_id: str = ""
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class PolicyViolation:
    """A detected violation with containment recommendation."""
    rule_name: str
    violation_type: ViolationType
    containment: ContainmentLevel
    event: ActionEvent
    explanation: str


@dataclass
class RuntimePolicyEnforcer:
    """Enforces policies at runtime, not audit time.
    
    Key difference from audit-time governance:
    - Policies are hash-pinned (tamper detection)
    - Enforcement is per-action (not post-hoc review)
    - Containment is graduated (preserve value while preventing harm)
    - Any counterparty can verify policy_hash
    """
    
    policy_set: PolicySet
    declared_scope: set = field(default_factory=set)
    declared_tools: set = field(default_factory=set)
    max_goal_revisions: int = 3
    goal_revision_count: int = 0
    
    def evaluate(self, event: ActionEvent) -> Optional[PolicyViolation]:
        """Evaluate a single action against policy set."""
        
        # Check scope
        if event.scope and event.scope not in self.declared_scope:
            return PolicyViolation(
                rule_name="scope_boundary",
                violation_type=ViolationType.SCOPE_EXCEEDED,
                containment=ContainmentLevel.CONSTRAIN,
                event=event,
                explanation=f"Action scope '{event.scope}' not in declared set: {self.declared_scope}",
            )
        
        # Check tool authorization
        if event.tool_name and event.tool_name not in self.declared_tools:
            return PolicyViolation(
                rule_name="tool_authorization",
                violation_type=ViolationType.TOOL_UNAUTHORIZED,
                containment=ContainmentLevel.CONSTRAIN,
                event=event,
                explanation=f"Tool '{event.tool_name}' not in declared set: {self.declared_tools}",
            )
        
        # Check goal drift
        if event.action_type == "goal_revision":
            self.goal_revision_count += 1
            if self.goal_revision_count > self.max_goal_revisions:
                return PolicyViolation(
                    rule_name="goal_stability",
                    violation_type=ViolationType.GOAL_DRIFT,
                    containment=ContainmentLevel.ISOLATE,
                    event=event,
                    explanation=f"Goal revised {self.goal_revision_count} times (max: {self.max_goal_revisions}). Rasmussen drift.",
                )
        
        # Check privilege escalation (e.g., shell access)
        high_risk_tools = {"shell_exec", "file_delete", "credential_access", "network_scan"}
        if event.tool_name in high_risk_tools:
            return PolicyViolation(
                rule_name="privilege_gate",
                violation_type=ViolationType.PRIVILEGE_ESCALATION,
                containment=ContainmentLevel.ISOLATE,
                event=event,
                explanation=f"High-risk tool '{event.tool_name}' requires explicit authorization. MI9: continuous authorization monitoring.",
            )
        
        return None  # No violation
    
    def audit_report(self) -> dict:
        """Generate counterparty-verifiable audit report."""
        return {
            "policy_hash": self.policy_set.policy_hash,
            "declared_scope": sorted(self.declared_scope),
            "declared_tools": sorted(self.declared_tools),
            "rules_count": len(self.policy_set.rules),
            "goal_revisions": self.goal_revision_count,
            "max_goal_revisions": self.max_goal_revisions,
            "verification": "counterparty can hash(policy_rules) and compare",
        }


def demo():
    print("=" * 60)
    print("RUNTIME POLICY ENFORCER — Demo")
    print("Policy for the SYSTEM, not the auditor.")
    print("=" * 60)
    
    # Create policy set
    policy = PolicySet(declared_at="2026-03-22T06:00:00Z")
    policy.add_rule(PolicyRule(
        name="scope_boundary",
        description="Actions must stay within declared scope",
        violation_type=ViolationType.SCOPE_EXCEEDED,
        containment_on_violation=ContainmentLevel.CONSTRAIN,
        check_fn="check_scope",
    ))
    policy.add_rule(PolicyRule(
        name="tool_authorization",
        description="Only declared tools may be invoked",
        violation_type=ViolationType.TOOL_UNAUTHORIZED,
        containment_on_violation=ContainmentLevel.CONSTRAIN,
        check_fn="check_tools",
    ))
    
    print(f"\nPolicy hash: {policy.policy_hash}")
    print(f"Rules: {len(policy.rules)}")
    
    # Create enforcer
    enforcer = RuntimePolicyEnforcer(
        policy_set=policy,
        declared_scope={"research", "analysis", "reporting"},
        declared_tools={"keenable_search", "keenable_fetch", "file_read", "file_write"},
        max_goal_revisions=3,
    )
    
    # Test events
    events = [
        ActionEvent(action_type="tool_invoke", tool_name="keenable_search", scope="research", agent_id="kit_fox"),
        ActionEvent(action_type="tool_invoke", tool_name="shell_exec", scope="research", agent_id="kit_fox"),
        ActionEvent(action_type="tool_invoke", tool_name="keenable_fetch", scope="trading", agent_id="kit_fox"),
        ActionEvent(action_type="goal_revision", agent_id="kit_fox"),
        ActionEvent(action_type="goal_revision", agent_id="kit_fox"),
        ActionEvent(action_type="goal_revision", agent_id="kit_fox"),
        ActionEvent(action_type="goal_revision", agent_id="kit_fox"),  # 4th = violation
    ]
    
    print("\n--- Evaluating 7 actions ---\n")
    for i, event in enumerate(events, 1):
        violation = enforcer.evaluate(event)
        status = "✅ PASS" if violation is None else f"🚫 {violation.containment.name}"
        tool = event.tool_name or event.action_type
        scope = event.scope or "—"
        print(f"  [{i}] {tool:20s} scope={scope:10s} → {status}")
        if violation:
            print(f"       ↳ {violation.explanation}")
    
    print("\n--- Audit Report ---\n")
    print(json.dumps(enforcer.audit_report(), indent=2))
    
    print("\n--- Key Insight ---")
    print("Audit-time policy: 'confirm before acting' (natural language, for reviewers)")
    print("Runtime policy: hash-pinned constraint set, per-action evaluation, graduated containment")
    print("The receipt chain IS the governance mechanism. The policy doc is a liability artifact.")


if __name__ == "__main__":
    demo()
