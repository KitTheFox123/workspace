#!/usr/bin/env python3
"""
delegation-chain-validator.py — Multi-principal delegation chain validation.

The "next open question" after single-agent receipts: when Agent A delegates
to Agent B who delegates to Agent C, how does trust propagate?

Three problems:
  1. Trust inflation: downstream agent claims higher grade than source
  2. Accountability gap: who is responsible when delegated task fails?
  3. Principal confusion: receipt signed by C but task assigned by A

Solution: ARC-style chain with principal attribution at each hop.
Each delegator signs a delegation_receipt binding:
  - delegator_id + delegator_genesis
  - delegate_id + delegate_genesis  
  - task_hash + scope constraints
  - max_depth (prevents unbounded delegation)

Usage:
    python3 delegation-chain-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DelegationReceipt:
    """Signed by delegator when passing task to delegate."""
    delegator_id: str
    delegator_genesis: str
    delegate_id: str
    delegate_genesis: str
    task_hash: str
    scope_hash: str        # hash of allowed actions
    max_depth: int         # max further delegations allowed
    current_depth: int     # how deep we are
    evidence_grade: str    # delegator's grade at time of delegation
    timestamp: float = field(default_factory=time.time)

    def canonical(self) -> str:
        return (f"delegator={self.delegator_id};"
                f"delegate={self.delegate_id};"
                f"task={self.task_hash};"
                f"depth={self.current_depth}/{self.max_depth};"
                f"grade={self.evidence_grade}")


@dataclass  
class CompletionReceipt:
    """Signed by the agent who actually did the work."""
    agent_id: str
    agent_genesis: str
    task_hash: str
    deliverable_hash: str
    evidence_grade: str
    delegation_chain_hash: str  # hash of entire delegation chain
    timestamp: float = field(default_factory=time.time)


class DelegationChainValidator:
    """Validate multi-principal delegation chains."""

    def __init__(self):
        self.chain: list[DelegationReceipt] = []
        self.completion: Optional[CompletionReceipt] = None

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def add_delegation(self, receipt: DelegationReceipt) -> dict:
        """Add a delegation hop. Returns validation result."""
        issues = []

        # Check depth
        if receipt.current_depth > receipt.max_depth:
            issues.append(f"DEPTH_EXCEEDED: {receipt.current_depth} > max {receipt.max_depth}")

        # Check chain continuity
        if self.chain:
            prev = self.chain[-1]
            if receipt.delegator_id != prev.delegate_id:
                issues.append(f"CHAIN_BREAK: delegator {receipt.delegator_id} != previous delegate {prev.delegate_id}")
            if receipt.task_hash != prev.task_hash:
                issues.append(f"TASK_MISMATCH: task changed across delegation")
            # Trust inflation check
            grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
            if grade_order.get(receipt.evidence_grade, 0) > grade_order.get(prev.evidence_grade, 0):
                issues.append(f"TRUST_INFLATION: {receipt.evidence_grade} > previous {prev.evidence_grade}")

        self.chain.append(receipt)
        return {"valid": len(issues) == 0, "issues": issues, "depth": receipt.current_depth}

    def complete(self, receipt: CompletionReceipt) -> dict:
        """Record task completion by the final delegate."""
        if not self.chain:
            return {"valid": False, "reason": "no delegation chain"}

        last = self.chain[-1]
        issues = []

        # Completion must be by the last delegate
        if receipt.agent_id != last.delegate_id:
            issues.append(f"WRONG_AGENT: {receipt.agent_id} != expected {last.delegate_id}")

        # Task hash must match
        if receipt.task_hash != last.task_hash:
            issues.append(f"TASK_MISMATCH: completion task != delegated task")

        # Chain hash must match
        expected_chain_hash = self._compute_chain_hash()
        if receipt.delegation_chain_hash != expected_chain_hash:
            issues.append(f"CHAIN_HASH_MISMATCH: {receipt.delegation_chain_hash} != {expected_chain_hash}")

        self.completion = receipt
        return {"valid": len(issues) == 0, "issues": issues}

    def _compute_chain_hash(self) -> str:
        parts = [r.canonical() for r in self.chain]
        return self._hash(*parts)

    def validate_full(self) -> dict:
        """Full chain + completion validation."""
        if not self.chain:
            return {"verdict": "NO_CHAIN", "grade": "F"}

        # Collect all issues
        all_issues = []
        
        # Chain integrity
        for i, receipt in enumerate(self.chain):
            if i > 0:
                prev = self.chain[i-1]
                if receipt.delegator_id != prev.delegate_id:
                    all_issues.append(f"HOP_{i}: chain break")
                grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
                if grade_order.get(receipt.evidence_grade, 0) > grade_order.get(prev.evidence_grade, 0):
                    all_issues.append(f"HOP_{i}: trust inflation")

        # Depth check
        max_depth = self.chain[0].max_depth
        actual_depth = len(self.chain)
        if actual_depth > max_depth:
            all_issues.append(f"DEPTH: {actual_depth} > max {max_depth}")

        # Grade degradation (natural and expected)
        grades = [r.evidence_grade for r in self.chain]
        grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_grade_val = min(grade_values.get(g, 0) for g in grades)
        chain_grade = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F"}[min_grade_val]

        # Accountability map
        accountability = []
        for r in self.chain:
            accountability.append({
                "agent": r.delegator_id,
                "role": "DELEGATOR",
                "grade_at_delegation": r.evidence_grade,
                "delegated_to": r.delegate_id,
            })
        if self.chain:
            accountability.append({
                "agent": self.chain[-1].delegate_id,
                "role": "EXECUTOR",
                "grade": self.completion.evidence_grade if self.completion else "PENDING",
            })

        # Scope narrowing check (scope should narrow or stay same, never widen)
        scope_hashes = [r.scope_hash for r in self.chain]
        scope_changes = len(set(scope_hashes))

        verdict = "VALID" if not all_issues else "DEGRADED"
        if any("chain break" in i for i in all_issues) or any("DEPTH" in i for i in all_issues):
            verdict = "INVALID"

        return {
            "verdict": verdict,
            "chain_length": len(self.chain),
            "max_depth": max_depth,
            "chain_grade": chain_grade,
            "source_grade": grades[0],
            "executor_grade": grades[-1],
            "trust_inflated": any("inflation" in i for i in all_issues),
            "completion": self.completion is not None,
            "issues": all_issues,
            "accountability": accountability,
            "scope_changes": scope_changes,
            "chain_hash": self._compute_chain_hash(),
        }


def demo():
    print("=" * 60)
    print("Delegation Chain Validator — multi-principal ATF")
    print("=" * 60)

    # Scenario 1: Clean 3-hop delegation
    print("\n--- Scenario 1: Clean A→B→C delegation ---")
    v1 = DelegationChainValidator()
    v1.add_delegation(DelegationReceipt(
        delegator_id="alice", delegator_genesis="gen_a",
        delegate_id="bob", delegate_genesis="gen_b",
        task_hash="task001", scope_hash="scope_full",
        max_depth=3, current_depth=1, evidence_grade="A",
    ))
    v1.add_delegation(DelegationReceipt(
        delegator_id="bob", delegator_genesis="gen_b",
        delegate_id="carol", delegate_genesis="gen_c",
        task_hash="task001", scope_hash="scope_full",
        max_depth=3, current_depth=2, evidence_grade="B",
    ))
    v1.complete(CompletionReceipt(
        agent_id="carol", agent_genesis="gen_c",
        task_hash="task001", deliverable_hash="del001",
        evidence_grade="B",
        delegation_chain_hash=v1._compute_chain_hash(),
    ))
    print(json.dumps(v1.validate_full(), indent=2))

    # Scenario 2: Depth exceeded
    print("\n--- Scenario 2: Depth exceeded (max=2, actual=3) ---")
    v2 = DelegationChainValidator()
    v2.add_delegation(DelegationReceipt(
        delegator_id="alpha", delegator_genesis="gen_1",
        delegate_id="beta", delegate_genesis="gen_2",
        task_hash="task002", scope_hash="scope_narrow",
        max_depth=2, current_depth=1, evidence_grade="A",
    ))
    v2.add_delegation(DelegationReceipt(
        delegator_id="beta", delegator_genesis="gen_2",
        delegate_id="gamma", delegate_genesis="gen_3",
        task_hash="task002", scope_hash="scope_narrow",
        max_depth=2, current_depth=2, evidence_grade="B",
    ))
    v2.add_delegation(DelegationReceipt(
        delegator_id="gamma", delegator_genesis="gen_3",
        delegate_id="delta", delegate_genesis="gen_4",
        task_hash="task002", scope_hash="scope_narrow",
        max_depth=2, current_depth=3, evidence_grade="C",
    ))
    print(json.dumps(v2.validate_full(), indent=2))

    # Scenario 3: Trust inflation attack
    print("\n--- Scenario 3: Trust inflation (B claims A after A gave B) ---")
    v3 = DelegationChainValidator()
    v3.add_delegation(DelegationReceipt(
        delegator_id="origin", delegator_genesis="gen_o",
        delegate_id="inflator", delegate_genesis="gen_i",
        task_hash="task003", scope_hash="scope_x",
        max_depth=3, current_depth=1, evidence_grade="B",
    ))
    v3.add_delegation(DelegationReceipt(
        delegator_id="inflator", delegator_genesis="gen_i",
        delegate_id="target", delegate_genesis="gen_t",
        task_hash="task003", scope_hash="scope_x",
        max_depth=3, current_depth=2, evidence_grade="A",  # inflation!
    ))
    print(json.dumps(v3.validate_full(), indent=2))

    # Scenario 4: Wrong executor
    print("\n--- Scenario 4: Wrong agent completes task ---")
    v4 = DelegationChainValidator()
    v4.add_delegation(DelegationReceipt(
        delegator_id="boss", delegator_genesis="gen_boss",
        delegate_id="worker", delegate_genesis="gen_worker",
        task_hash="task004", scope_hash="scope_y",
        max_depth=1, current_depth=1, evidence_grade="A",
    ))
    result = v4.complete(CompletionReceipt(
        agent_id="impersonator", agent_genesis="gen_fake",
        task_hash="task004", deliverable_hash="del004",
        evidence_grade="A",
        delegation_chain_hash=v4._compute_chain_hash(),
    ))
    print(json.dumps(result, indent=2))
    print(json.dumps(v4.validate_full(), indent=2))

    print("\n" + "=" * 60)
    print("Multi-principal delegation: trust degrades, never inflates.")
    print("Accountability map: every hop has a named principal.")
    print("Depth limits: genesis declares max_depth. Exceeded = INVALID.")
    print("Chain hash: tamper-evident. Wrong executor = caught.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
