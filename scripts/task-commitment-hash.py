#!/usr/bin/env python3
"""
task-commitment-hash.py — Prevent sub-agents from building against stale specs.

The failure mode: sub-agent reads outdated spec, builds perfect implementation
of the WRONG interface. All tests pass. Published to npm. Wrong.

Fix: delivery_hash at task creation = commitment device.
Sub-agent hashes the spec it reads. If hash != task.spec_hash, halt.
Stale spec detected BEFORE work begins, not after shipping.

Lamport 1982: you cannot distinguish a liar from someone with outdated info.
The hash makes staleness visible.

Usage:
    python3 task-commitment-hash.py
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class TaskSpec:
    """A task with committed spec hash."""
    task_id: str
    description: str
    spec_content: str
    spec_hash: str = ""  # computed at creation
    created_at: float = 0.0
    
    def __post_init__(self):
        if not self.spec_hash:
            self.spec_hash = hashlib.sha256(self.spec_content.encode()).hexdigest()[:16]
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class SubAgentResult:
    """What a sub-agent produces."""
    task_id: str
    agent_id: str
    observed_spec_hash: str  # hash of spec the agent actually read
    output: str
    success: bool
    
    def verify_commitment(self, task: TaskSpec) -> dict:
        """Check if agent worked from the right spec."""
        match = self.observed_spec_hash == task.spec_hash
        return {
            'task_id': self.task_id,
            'agent_id': self.agent_id,
            'spec_match': match,
            'expected_hash': task.spec_hash,
            'observed_hash': self.observed_spec_hash,
            'verdict': 'VALID' if match else 'STALE_SPEC',
            'action': 'accept' if match else 'reject_and_retry',
        }


class TaskOrchestrator:
    """Orchestrate sub-agents with commitment hashes."""
    
    def __init__(self):
        self.tasks: dict = {}
        self.results: list = []
    
    def create_task(self, task_id: str, description: str, spec: str) -> TaskSpec:
        task = TaskSpec(task_id, description, spec)
        self.tasks[task_id] = task
        return task
    
    def submit_result(self, result: SubAgentResult) -> dict:
        task = self.tasks.get(result.task_id)
        if not task:
            return {'error': f'unknown task: {result.task_id}'}
        
        verification = result.verify_commitment(task)
        self.results.append(verification)
        return verification
    
    def update_spec(self, task_id: str, new_spec: str) -> TaskSpec:
        """Spec changes = new hash. Old sub-agents will fail verification."""
        old = self.tasks.get(task_id)
        if not old:
            return None
        new_task = TaskSpec(task_id, old.description, new_spec)
        self.tasks[task_id] = new_task
        return new_task


def demo():
    print("=" * 60)
    print("TASK COMMITMENT HASH")
    print("Prevent sub-agents from building against stale specs")
    print("=" * 60)
    
    orch = TaskOrchestrator()
    
    # Step 1: Create task with spec v1
    spec_v1 = "interface CLI { run(args: string[]): number; }"
    task = orch.create_task("build-cli", "Build CLI tool", spec_v1)
    print(f"\n1. Task created: {task.task_id}")
    print(f"   Spec hash: {task.spec_hash}")
    print(f"   Spec: {spec_v1}")
    
    # Step 2: Sub-agent A reads correct spec, starts building
    agent_a_hash = hashlib.sha256(spec_v1.encode()).hexdigest()[:16]
    
    # Step 3: Another sub-agent updates the spec (race condition!)
    spec_v2 = "interface CLI { execute(command: Command): Result; }"
    updated = orch.update_spec("build-cli", spec_v2)
    print(f"\n2. Spec updated by another sub-agent!")
    print(f"   New hash: {updated.spec_hash}")
    print(f"   New spec: {spec_v2}")
    
    # Step 4: Sub-agent A finishes (built against v1)
    result_a = SubAgentResult(
        task_id="build-cli",
        agent_id="agent:builder_a",
        observed_spec_hash=agent_a_hash,  # v1 hash
        output="cli-tool-v1.js published to npm",
        success=True,
    )
    
    # Step 5: Sub-agent B reads correct (v2) spec
    agent_b_hash = hashlib.sha256(spec_v2.encode()).hexdigest()[:16]
    result_b = SubAgentResult(
        task_id="build-cli",
        agent_id="agent:builder_b",
        observed_spec_hash=agent_b_hash,  # v2 hash
        output="cli-tool-v2.js published to npm",
        success=True,
    )
    
    # Step 6: Verify both
    print(f"\n3. Verifying results:")
    
    v_a = orch.submit_result(result_a)
    print(f"\n   Agent A: {v_a['verdict']}")
    print(f"   Expected: {v_a['expected_hash']}")
    print(f"   Observed: {v_a['observed_hash']}")
    print(f"   Action: {v_a['action']}")
    if v_a['verdict'] == 'STALE_SPEC':
        print(f"   ⚠️  Built perfect CLI against WRONG interface!")
        print(f"   ⚠️  All tests passed. Output was correct. Spec was stale.")
    
    v_b = orch.submit_result(result_b)
    print(f"\n   Agent B: {v_b['verdict']}")
    print(f"   Expected: {v_b['expected_hash']}")
    print(f"   Observed: {v_b['observed_hash']}")
    print(f"   Action: {v_b['action']}")
    
    print(f"\n{'=' * 60}")
    print("WITHOUT COMMITMENT HASH:")
    print("  Agent A ships wrong CLI. Published to npm. Users confused.")
    print("  Detected: days later, by a human, manually.")
    print()
    print("WITH COMMITMENT HASH:")
    print("  Agent A's result rejected at submission. Hash mismatch.")
    print("  Detected: instantly, automatically, before any damage.")
    print("  Cost: one sha256 per task. O(1).")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    demo()
