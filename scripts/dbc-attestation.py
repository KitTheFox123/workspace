#!/usr/bin/env python3
"""
dbc-attestation.py — Design by Contract (Meyer 1992) for agent trust.

Preconditions: scope_hash valid before action
Postconditions: state transition attested after action  
Invariants: identity preserved across sessions

Post-hoc disputes = debugging without assertions.
Bake attestation into the contract, not the dispute process.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Verdict(Enum):
    PASS = "PASS"
    PRECONDITION_FAIL = "PRECONDITION_FAIL"
    POSTCONDITION_FAIL = "POSTCONDITION_FAIL"
    INVARIANT_FAIL = "INVARIANT_FAIL"


@dataclass
class Contract:
    """A DbC contract for an agent action."""
    action_name: str
    # Preconditions
    scope_hash_required: str
    min_trust_score: float = 0.0
    required_capabilities: list = field(default_factory=list)
    # Postconditions  
    expected_state_change: Optional[str] = None
    max_duration_s: float = float('inf')
    # Invariants
    identity_key: Optional[str] = None


@dataclass 
class ActionContext:
    """Runtime context for checking a contract."""
    agent_id: str
    scope_hash: str
    trust_score: float
    capabilities: list
    identity_key: str
    pre_state_hash: str
    post_state_hash: Optional[str] = None
    duration_s: float = 0.0


def check_preconditions(contract: Contract, ctx: ActionContext) -> list[str]:
    """Check all preconditions before action executes."""
    failures = []
    if ctx.scope_hash != contract.scope_hash_required:
        failures.append(f"scope_hash mismatch: got {ctx.scope_hash[:8]}, expected {contract.scope_hash_required[:8]}")
    if ctx.trust_score < contract.min_trust_score:
        failures.append(f"trust_score {ctx.trust_score:.2f} < required {contract.min_trust_score:.2f}")
    missing = set(contract.required_capabilities) - set(ctx.capabilities)
    if missing:
        failures.append(f"missing capabilities: {missing}")
    return failures


def check_postconditions(contract: Contract, ctx: ActionContext) -> list[str]:
    """Check all postconditions after action completes."""
    failures = []
    if contract.expected_state_change and ctx.post_state_hash is None:
        failures.append("no post-state hash provided")
    if ctx.duration_s > contract.max_duration_s:
        failures.append(f"duration {ctx.duration_s:.1f}s > max {contract.max_duration_s:.1f}s")
    if ctx.pre_state_hash == ctx.post_state_hash and contract.expected_state_change:
        failures.append("state unchanged despite expected change")
    return failures


def check_invariants(contract: Contract, ctx: ActionContext) -> list[str]:
    """Check invariants that must hold before AND after."""
    failures = []
    if contract.identity_key and ctx.identity_key != contract.identity_key:
        failures.append(f"identity key changed: {ctx.identity_key[:8]} ≠ {contract.identity_key[:8]}")
    if not ctx.agent_id:
        failures.append("agent_id missing")
    return failures


def execute_with_contract(contract: Contract, ctx: ActionContext) -> dict:
    """Full DbC check: invariants + preconditions → action → postconditions + invariants."""
    results = {
        "action": contract.action_name,
        "agent": ctx.agent_id,
        "checks": {},
        "verdict": Verdict.PASS.value,
    }
    
    # Check invariants (before)
    inv_pre = check_invariants(contract, ctx)
    if inv_pre:
        results["checks"]["invariant_pre"] = inv_pre
        results["verdict"] = Verdict.INVARIANT_FAIL.value
        results["grade"] = "F"
        return results
    results["checks"]["invariant_pre"] = "✓"
    
    # Check preconditions
    pre = check_preconditions(contract, ctx)
    if pre:
        results["checks"]["preconditions"] = pre
        results["verdict"] = Verdict.PRECONDITION_FAIL.value
        results["grade"] = "D"
        return results
    results["checks"]["preconditions"] = "✓"
    
    # (Action executes here)
    
    # Check postconditions
    post = check_postconditions(contract, ctx)
    if post:
        results["checks"]["postconditions"] = post
        results["verdict"] = Verdict.POSTCONDITION_FAIL.value
        results["grade"] = "C"
        return results
    results["checks"]["postconditions"] = "✓"
    
    # Check invariants (after)
    inv_post = check_invariants(contract, ctx)
    if inv_post:
        results["checks"]["invariant_post"] = inv_post
        results["verdict"] = Verdict.INVARIANT_FAIL.value
        results["grade"] = "F"
        return results
    results["checks"]["invariant_post"] = "✓"
    
    results["grade"] = "A"
    return results


def demo():
    scope = hashlib.sha256(b"read_file:write_file:search").hexdigest()[:16]
    identity = hashlib.sha256(b"kit_fox_ed25519_pubkey").hexdigest()[:16]
    
    contract = Contract(
        action_name="research_and_post",
        scope_hash_required=scope,
        min_trust_score=0.6,
        required_capabilities=["read_file", "search"],
        expected_state_change="new_post_created",
        max_duration_s=300.0,
        identity_key=identity,
    )
    
    scenarios = [
        ("Healthy action", ActionContext(
            agent_id="kit_fox", scope_hash=scope, trust_score=0.85,
            capabilities=["read_file", "write_file", "search"],
            identity_key=identity,
            pre_state_hash="aaa111", post_state_hash="bbb222", duration_s=45.0
        )),
        ("Scope drift (Ronin pattern)", ActionContext(
            agent_id="kit_fox", scope_hash="wrong_scope_12345",
            trust_score=0.85, capabilities=["read_file", "search"],
            identity_key=identity,
            pre_state_hash="aaa111", post_state_hash="bbb222", duration_s=45.0
        )),
        ("Low trust (cold start)", ActionContext(
            agent_id="new_agent", scope_hash=scope, trust_score=0.3,
            capabilities=["read_file", "search"],
            identity_key=identity,
            pre_state_hash="aaa111", post_state_hash="bbb222", duration_s=45.0
        )),
        ("No state change (stale)", ActionContext(
            agent_id="kit_fox", scope_hash=scope, trust_score=0.85,
            capabilities=["read_file", "write_file", "search"],
            identity_key=identity,
            pre_state_hash="aaa111", post_state_hash="aaa111", duration_s=45.0
        )),
        ("Identity tampered (Nomad pattern)", ActionContext(
            agent_id="kit_fox", scope_hash=scope, trust_score=0.85,
            capabilities=["read_file", "search"],
            identity_key="tampered_key_1234",
            pre_state_hash="aaa111", post_state_hash="bbb222", duration_s=45.0
        )),
    ]
    
    print("=" * 60)
    print("DESIGN BY CONTRACT — Agent Trust Attestation")
    print("Meyer 1992: preconditions + postconditions + invariants")
    print("=" * 60)
    
    for name, ctx in scenarios:
        result = execute_with_contract(contract, ctx)
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Verdict: {result['verdict']} | Grade: {result['grade']}")
        for check, val in result["checks"].items():
            if val == "✓":
                print(f"  {check}: ✓")
            else:
                print(f"  {check}: ✗ {val}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Post-hoc disputes = debugging without assertions.")
    print("Bake attestation into the contract. The precondition IS the")
    print("scope check. The postcondition IS the state attestation.")
    print("The invariant IS identity preservation. (Meyer 1992)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
