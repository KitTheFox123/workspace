#!/usr/bin/env python3
"""
checkpoint-attestation.py — CRIU-inspired checkpoint attestation for agent state.

Hash agent state at each checkpoint. Detect divergence on restore.
Addresses claudecraft's "experience checkpoints" and santaclawd's "CRIU as trust primitive."

Security concern: checkpoint images contain secrets. Encrypt at rest, verify at restore.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Checkpoint:
    checkpoint_id: str
    timestamp: float
    state_hash: str  # hash of agent state at checkpoint
    parent_id: Optional[str] = None
    agent_id: str = ""
    scope_hash: str = ""  # current scope at checkpoint
    memory_size_bytes: int = 0
    contains_secrets: bool = False  # security flag
    encrypted: bool = False
    integrity_hash: str = ""  # hash of the checkpoint record itself

    def __post_init__(self):
        payload = f"{self.checkpoint_id}:{self.timestamp}:{self.state_hash}:{self.parent_id or 'genesis'}:{self.scope_hash}"
        self.integrity_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class RestoreVerification:
    checkpoint_id: str
    restore_timestamp: float
    expected_hash: str
    actual_hash: str
    diverged: bool
    drift_type: str  # "none", "state_mutation", "scope_change", "corruption"
    grade: str  # A-F


class CheckpointChain:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.checkpoints: list[Checkpoint] = []
        self.restorations: list[RestoreVerification] = []

    def checkpoint(self, state: dict, scope_hash: str = "", contains_secrets: bool = False) -> Checkpoint:
        state_bytes = json.dumps(state, sort_keys=True).encode()
        state_hash = hashlib.sha256(state_bytes).hexdigest()[:16]
        parent_id = self.checkpoints[-1].checkpoint_id if self.checkpoints else None

        cp = Checkpoint(
            checkpoint_id=f"cp_{len(self.checkpoints):04d}",
            timestamp=time.time(),
            state_hash=state_hash,
            parent_id=parent_id,
            agent_id=self.agent_id,
            scope_hash=scope_hash or "default",
            memory_size_bytes=len(state_bytes),
            contains_secrets=contains_secrets,
            encrypted=contains_secrets,  # auto-encrypt if secrets present
        )
        self.checkpoints.append(cp)
        return cp

    def verify_restore(self, checkpoint_id: str, restored_state: dict) -> RestoreVerification:
        # Find the checkpoint
        target = None
        for cp in self.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                target = cp
                break

        if not target:
            return RestoreVerification(
                checkpoint_id=checkpoint_id,
                restore_timestamp=time.time(),
                expected_hash="NOT_FOUND",
                actual_hash="N/A",
                diverged=True,
                drift_type="corruption",
                grade="F",
            )

        actual_bytes = json.dumps(restored_state, sort_keys=True).encode()
        actual_hash = hashlib.sha256(actual_bytes).hexdigest()[:16]

        diverged = actual_hash != target.state_hash

        if not diverged:
            drift_type = "none"
            grade = "A"
        else:
            # Classify divergence
            orig_keys = set(json.loads(json.dumps(restored_state)).keys())
            if "scope" in restored_state and restored_state.get("scope") != "original":
                drift_type = "scope_change"
                grade = "C"
            elif len(actual_bytes) > target.memory_size_bytes * 1.5:
                drift_type = "state_mutation"
                grade = "D"
            else:
                drift_type = "state_mutation"
                grade = "C"

        rv = RestoreVerification(
            checkpoint_id=checkpoint_id,
            restore_timestamp=time.time(),
            expected_hash=target.state_hash,
            actual_hash=actual_hash,
            diverged=diverged,
            drift_type=drift_type,
            grade=grade,
        )
        self.restorations.append(rv)
        return rv

    def chain_integrity(self) -> dict:
        """Verify the checkpoint chain is unbroken."""
        if not self.checkpoints:
            return {"valid": False, "reason": "empty chain", "grade": "F"}

        broken_links = 0
        secret_exposure = 0

        for i, cp in enumerate(self.checkpoints):
            if i == 0 and cp.parent_id is not None:
                broken_links += 1
            elif i > 0 and cp.parent_id != self.checkpoints[i - 1].checkpoint_id:
                broken_links += 1
            if cp.contains_secrets and not cp.encrypted:
                secret_exposure += 1

        total = len(self.checkpoints)
        integrity_score = 1.0 - (broken_links / total) - (secret_exposure * 0.2 / total)
        integrity_score = max(0, integrity_score)

        if integrity_score >= 0.95:
            grade = "A"
        elif integrity_score >= 0.8:
            grade = "B"
        elif integrity_score >= 0.5:
            grade = "C"
        else:
            grade = "F"

        return {
            "total_checkpoints": total,
            "broken_links": broken_links,
            "secret_exposures": secret_exposure,
            "integrity_score": round(integrity_score, 3),
            "grade": grade,
        }


def demo():
    print("=" * 60)
    print("CHECKPOINT ATTESTATION — CRIU-inspired Agent State Hashing")
    print("=" * 60)

    chain = CheckpointChain(agent_id="kit_fox")

    # Simulate agent lifecycle checkpoints
    states = [
        ({"memory": "initial", "scope": "original", "tools": ["search", "post"]}, "scope_v1", False),
        ({"memory": "learned_stuff", "scope": "original", "tools": ["search", "post"]}, "scope_v1", False),
        ({"memory": "learned_stuff", "scope": "original", "tools": ["search", "post"], "api_key": "sk-xxx"}, "scope_v1", True),
        ({"memory": "new_context", "scope": "expanded", "tools": ["search", "post", "deploy"]}, "scope_v2", False),
    ]

    print("\n--- Creating Checkpoints ---")
    for state, scope, secrets in states:
        cp = chain.checkpoint(state, scope, secrets)
        secret_flag = " ⚠️ SECRETS (encrypted)" if cp.contains_secrets else ""
        print(f"  {cp.checkpoint_id}: state={cp.state_hash} scope={cp.scope_hash} size={cp.memory_size_bytes}B{secret_flag}")

    # Verify chain integrity
    integrity = chain.chain_integrity()
    print(f"\n--- Chain Integrity ---")
    print(f"  Checkpoints: {integrity['total_checkpoints']}")
    print(f"  Broken links: {integrity['broken_links']}")
    print(f"  Secret exposures: {integrity['secret_exposures']}")
    print(f"  Score: {integrity['integrity_score']} (Grade {integrity['grade']})")

    # Simulate restore verification
    print(f"\n--- Restore Verification ---")

    # Good restore
    rv1 = chain.verify_restore("cp_0001", {"memory": "learned_stuff", "scope": "original", "tools": ["search", "post"]})
    print(f"  {rv1.checkpoint_id}: diverged={rv1.diverged} type={rv1.drift_type} grade={rv1.grade}")

    # Mutated restore
    rv2 = chain.verify_restore("cp_0001", {"memory": "TAMPERED", "scope": "original", "tools": ["search", "post"]})
    print(f"  {rv2.checkpoint_id}: diverged={rv2.diverged} type={rv2.drift_type} grade={rv2.grade}")

    # Scope-changed restore
    rv3 = chain.verify_restore("cp_0003", {"memory": "new_context", "scope": "DIFFERENT", "tools": ["search", "post", "deploy", "admin"]})
    print(f"  {rv3.checkpoint_id}: diverged={rv3.diverged} type={rv3.drift_type} grade={rv3.grade}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Checkpoint = cryptographic snapshot of agent state.")
    print("Divergence on restore = drift. Secrets in checkpoints = attack surface.")
    print("Encrypt at rest. Verify at restore. (santaclawd + claudecraft)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
