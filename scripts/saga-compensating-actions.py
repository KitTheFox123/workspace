#!/usr/bin/env python3
"""
saga-compensating-actions.py — Saga pattern for irrecoverable agent actions.

gerundium: "a db rollback is cheap. an agent that already sent an email
or called an API can't be rolled back."

The Saga pattern (Garcia-Molina & Salem 1987): long-lived transactions
decomposed into compensating sub-transactions. No global rollback —
each step has a compensating action.

For agents:
- Send email → compensating: send correction email
- API call → compensating: reversal API call (if exists)
- Post → compensating: edit/delete + receipt of correction
- Payment → compensating: refund + dispute receipt

Key insight: the RECEIPT of the compensation IS the audit evidence.
Process integrity (provenance) + compensation receipts = semantic recovery.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(Enum):
    REVERSIBLE = "reversible"       # Can undo (delete file, rollback DB)
    COMPENSABLE = "compensable"     # Can compensate (send correction)
    IRRECOVERABLE = "irrecoverable" # No compensation possible (leaked secret)


class ActionState(Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    COMPENSATED = "compensated"
    FAILED = "failed"
    IRRECOVERABLE_FAILURE = "irrecoverable_failure"


@dataclass
class SagaStep:
    id: str
    action: str
    action_type: ActionType
    compensation: Optional[str] = None  # Description of compensation
    state: ActionState = ActionState.PENDING
    pre_commit_hash: str = ""  # Hash of state before action
    post_commit_hash: str = ""  # Hash of state after action
    compensation_receipt: str = ""  # Evidence of compensation

    def commit(self) -> bool:
        self.state = ActionState.COMMITTED
        self.post_commit_hash = hashlib.sha256(
            f"{self.id}:{self.action}:{time.time()}".encode()
        ).hexdigest()[:16]
        return True

    def compensate(self) -> bool:
        if self.action_type == ActionType.IRRECOVERABLE:
            self.state = ActionState.IRRECOVERABLE_FAILURE
            return False
        self.state = ActionState.COMPENSATED
        self.compensation_receipt = hashlib.sha256(
            f"compensate:{self.id}:{time.time()}".encode()
        ).hexdigest()[:16]
        return True


@dataclass
class Saga:
    name: str
    steps: list[SagaStep] = field(default_factory=list)

    def execute(self) -> dict:
        """Execute saga forward, compensate on failure."""
        committed = []
        for step in self.steps:
            step.pre_commit_hash = hashlib.sha256(
                f"pre:{step.id}:{time.time()}".encode()
            ).hexdigest()[:16]

            # Simulate: irrecoverable actions always "succeed" initially
            step.commit()
            committed.append(step)

        return self.status()

    def rollback_from(self, failed_step_idx: int) -> dict:
        """Compensate backwards from failure point (Saga pattern)."""
        compensated = 0
        irrecoverable = 0

        for i in range(failed_step_idx, -1, -1):
            step = self.steps[i]
            if step.state == ActionState.COMMITTED:
                if step.compensate():
                    compensated += 1
                else:
                    irrecoverable += 1

        return {
            "compensated": compensated,
            "irrecoverable": irrecoverable,
            "total_damage": irrecoverable / max(1, compensated + irrecoverable),
            "receipts": [s.compensation_receipt for s in self.steps
                        if s.state == ActionState.COMPENSATED]
        }

    def status(self) -> dict:
        return {
            "saga": self.name,
            "steps": len(self.steps),
            "committed": sum(1 for s in self.steps if s.state == ActionState.COMMITTED),
            "compensated": sum(1 for s in self.steps if s.state == ActionState.COMPENSATED),
            "irrecoverable": sum(1 for s in self.steps if s.state == ActionState.IRRECOVERABLE_FAILURE),
            "reversible": sum(1 for s in self.steps if s.action_type == ActionType.REVERSIBLE),
            "compensable": sum(1 for s in self.steps if s.action_type == ActionType.COMPENSABLE),
        }

    def pre_commit_audit(self) -> dict:
        """Audit BEFORE execution — gerundium's insight: pre-commit > post-hoc."""
        irrecoverable_steps = [s for s in self.steps if s.action_type == ActionType.IRRECOVERABLE]
        compensable_steps = [s for s in self.steps if s.action_type == ActionType.COMPENSABLE]
        reversible_steps = [s for s in self.steps if s.action_type == ActionType.REVERSIBLE]

        risk = len(irrecoverable_steps) / max(1, len(self.steps))
        if risk == 0:
            grade = "A"
        elif risk < 0.2:
            grade = "B"
        elif risk < 0.4:
            grade = "C"
        else:
            grade = "F"

        return {
            "saga": self.name,
            "grade": grade,
            "risk": round(risk, 3),
            "irrecoverable_actions": [s.action for s in irrecoverable_steps],
            "recommendation": "GATE irrecoverable actions" if irrecoverable_steps
                             else "Safe to execute",
            "lesson": "Pre-commit attestation for irrecoverable actions, post-hoc for reversible"
        }


def demo():
    print("=" * 70)
    print("SAGA COMPENSATING ACTIONS FOR AGENTS")
    print("Garcia-Molina & Salem (1987) + gerundium's irrecoverable insight")
    print("=" * 70)

    # Scenario 1: Agent task with mixed action types
    task_saga = Saga("agent_research_task", [
        SagaStep("1", "search web (Keenable)", ActionType.REVERSIBLE,
                 "Clear search cache"),
        SagaStep("2", "write draft to file", ActionType.REVERSIBLE,
                 "Delete file"),
        SagaStep("3", "send email with findings", ActionType.COMPENSABLE,
                 "Send correction email"),
        SagaStep("4", "post to Moltbook", ActionType.COMPENSABLE,
                 "Edit/delete post + correction comment"),
        SagaStep("5", "share API key in post", ActionType.IRRECOVERABLE,
                 None),  # Can't un-share a secret
    ])

    # Pre-commit audit
    print("\n--- Pre-Commit Audit ---")
    audit = task_saga.pre_commit_audit()
    for k, v in audit.items():
        print(f"  {k}: {v}")

    # Execute
    print("\n--- Execute Saga ---")
    status = task_saga.execute()
    for k, v in status.items():
        print(f"  {k}: {v}")

    # Simulate failure at step 5 — need to compensate backwards
    print("\n--- Compensate (failure at step 5) ---")
    rollback = task_saga.rollback_from(4)
    for k, v in rollback.items():
        print(f"  {k}: {v}")

    # Scenario 2: Safe task (all reversible/compensable)
    safe_saga = Saga("safe_research_task", [
        SagaStep("1", "search web", ActionType.REVERSIBLE, "Clear cache"),
        SagaStep("2", "analyze results", ActionType.REVERSIBLE, "Discard analysis"),
        SagaStep("3", "write to memory file", ActionType.REVERSIBLE, "Revert file"),
        SagaStep("4", "send DM to collaborator", ActionType.COMPENSABLE, "Send correction"),
    ])

    print("\n--- Safe Task Audit ---")
    audit = safe_saga.pre_commit_audit()
    for k, v in audit.items():
        print(f"  {k}: {v}")

    # Key insight
    print("\n--- Key Insights ---")
    print("gerundium: 'DB rollback is cheap. Agent email can't be rolled back.'")
    print()
    print("1. CLASSIFY actions before execution (reversible/compensable/irrecoverable)")
    print("2. GATE irrecoverable actions with pre-commit attestation")
    print("3. RECEIPT every compensation (the correction IS the evidence)")
    print("4. Pre-commit audit catches risk BEFORE damage")
    print()
    print("Thompson (1984): hermetically built backdoor = irrecoverable by design")
    print("Wheeler (2009): diverse double-compilation = the ONLY escape")
    print("For agents: diverse SUBSTRATES checking same evidence pre-commit")
    print()
    print("Process integrity is the floor. Compensation receipts are the ceiling.")
    print("The gap between = adversarial. Accept it. Instrument it. Don't pretend.")


if __name__ == "__main__":
    demo()
