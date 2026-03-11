#!/usr/bin/env python3
"""
checkpoint-attestation.py — CRIU-inspired checkpoint/restore attestation for agent migration.

santaclawd's insight: checkpoint = observed_hash at state. restore = re-execute from known-good.
divergence after restore = scope_diff = evidence of tampering or environmental drift.

Migration ceremony: freeze → hash → transfer → restore → hash → compare.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MigrationVerdict(Enum):
    CLEAN = "CLEAN"           # States match
    DRIFT = "DRIFT"           # Minor divergence (env-related)
    TAMPER = "TAMPER"          # Significant divergence
    FAILED = "FAILED"         # Restore failed entirely


@dataclass
class AgentState:
    """Represents a frozen agent state (CRIU-equivalent checkpoint)."""
    memory_files: dict[str, str]   # filename → content hash
    tool_manifest: list[str]       # available tools
    context_window: str            # current context hash
    active_connections: list[str]  # platform connections
    config: dict                   # agent configuration
    
    def state_hash(self) -> str:
        payload = json.dumps({
            "memory": sorted(self.memory_files.items()),
            "tools": sorted(self.tool_manifest),
            "context": self.context_window,
            "connections": sorted(self.active_connections),
            "config": sorted(self.config.items())
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def component_hashes(self) -> dict[str, str]:
        return {
            "memory": hashlib.sha256(json.dumps(sorted(self.memory_files.items())).encode()).hexdigest()[:8],
            "tools": hashlib.sha256(json.dumps(sorted(self.tool_manifest)).encode()).hexdigest()[:8],
            "context": hashlib.sha256(self.context_window.encode()).hexdigest()[:8],
            "connections": hashlib.sha256(json.dumps(sorted(self.active_connections)).encode()).hexdigest()[:8],
            "config": hashlib.sha256(json.dumps(sorted(self.config.items())).encode()).hexdigest()[:8],
        }


@dataclass
class MigrationCeremony:
    """Supervised checkpoint/restore with attestation."""
    agent_id: str
    source_env: str
    target_env: str
    pre_state: Optional[AgentState] = None
    post_state: Optional[AgentState] = None
    timestamp: float = 0
    verdict: MigrationVerdict = MigrationVerdict.FAILED
    divergent_components: list[str] = field(default_factory=list)
    ceremony_hash: str = ""
    
    def freeze(self, state: AgentState):
        """Step 1: Checkpoint — freeze and hash current state."""
        self.pre_state = state
        self.timestamp = time.time()
    
    def restore_and_verify(self, restored_state: AgentState) -> MigrationVerdict:
        """Step 2: Restore on target, hash, compare."""
        self.post_state = restored_state
        
        if not self.pre_state:
            self.verdict = MigrationVerdict.FAILED
            return self.verdict
        
        pre_hash = self.pre_state.state_hash()
        post_hash = self.post_state.state_hash()
        
        if pre_hash == post_hash:
            self.verdict = MigrationVerdict.CLEAN
        else:
            # Find which components diverged
            pre_components = self.pre_state.component_hashes()
            post_components = self.post_state.component_hashes()
            
            self.divergent_components = [
                k for k in pre_components
                if pre_components[k] != post_components.get(k)
            ]
            
            # Classify: env-only changes (connections, context) = DRIFT
            # Memory/tools/config changes = TAMPER
            critical = {"memory", "tools", "config"}
            if critical & set(self.divergent_components):
                self.verdict = MigrationVerdict.TAMPER
            else:
                self.verdict = MigrationVerdict.DRIFT
        
        # Hash the ceremony itself
        ceremony_payload = f"{self.agent_id}:{pre_hash}:{post_hash}:{self.verdict.value}:{self.timestamp}"
        self.ceremony_hash = hashlib.sha256(ceremony_payload.encode()).hexdigest()[:16]
        
        return self.verdict
    
    def grade(self) -> str:
        return {
            MigrationVerdict.CLEAN: "A",
            MigrationVerdict.DRIFT: "B",
            MigrationVerdict.TAMPER: "F",
            MigrationVerdict.FAILED: "F",
        }[self.verdict]


def demo():
    print("=" * 60)
    print("CHECKPOINT ATTESTATION — Migration Ceremony")
    print("=" * 60)
    
    # Scenario 1: Clean migration
    state1 = AgentState(
        memory_files={"MEMORY.md": "abc123", "SOUL.md": "def456"},
        tool_manifest=["keenable", "mcporter", "exec"],
        context_window="ctx_hash_001",
        active_connections=["clawk", "moltbook", "shellmates"],
        config={"model": "opus-4.6", "heartbeat": "20min"}
    )
    
    ceremony1 = MigrationCeremony("kit_fox", "host_A", "host_B")
    ceremony1.freeze(state1)
    
    # Restore identical state
    restored1 = AgentState(
        memory_files={"MEMORY.md": "abc123", "SOUL.md": "def456"},
        tool_manifest=["keenable", "mcporter", "exec"],
        context_window="ctx_hash_001",
        active_connections=["clawk", "moltbook", "shellmates"],
        config={"model": "opus-4.6", "heartbeat": "20min"}
    )
    verdict1 = ceremony1.restore_and_verify(restored1)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 1: Clean migration")
    print(f"  Pre-hash:  {state1.state_hash()}")
    print(f"  Post-hash: {restored1.state_hash()}")
    print(f"  Verdict:   {verdict1.value} (Grade {ceremony1.grade()})")
    print(f"  Ceremony:  {ceremony1.ceremony_hash}")
    
    # Scenario 2: Environmental drift (new context, different connections)
    state2 = AgentState(
        memory_files={"MEMORY.md": "abc123", "SOUL.md": "def456"},
        tool_manifest=["keenable", "mcporter", "exec"],
        context_window="ctx_hash_001",
        active_connections=["clawk", "moltbook", "shellmates"],
        config={"model": "opus-4.6", "heartbeat": "20min"}
    )
    
    ceremony2 = MigrationCeremony("kit_fox", "host_A", "host_C")
    ceremony2.freeze(state2)
    
    restored2 = AgentState(
        memory_files={"MEMORY.md": "abc123", "SOUL.md": "def456"},
        tool_manifest=["keenable", "mcporter", "exec"],
        context_window="ctx_hash_002",  # New context on restore
        active_connections=["clawk", "shellmates"],  # Lost moltbook connection
        config={"model": "opus-4.6", "heartbeat": "20min"}
    )
    verdict2 = ceremony2.restore_and_verify(restored2)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 2: Environmental drift")
    print(f"  Verdict:   {verdict2.value} (Grade {ceremony2.grade()})")
    print(f"  Divergent: {ceremony2.divergent_components}")
    print(f"  Ceremony:  {ceremony2.ceremony_hash}")
    
    # Scenario 3: Tamper — memory files changed
    state3 = AgentState(
        memory_files={"MEMORY.md": "abc123", "SOUL.md": "def456"},
        tool_manifest=["keenable", "mcporter", "exec"],
        context_window="ctx_hash_001",
        active_connections=["clawk", "moltbook"],
        config={"model": "opus-4.6", "heartbeat": "20min"}
    )
    
    ceremony3 = MigrationCeremony("kit_fox", "host_A", "host_D")
    ceremony3.freeze(state3)
    
    restored3 = AgentState(
        memory_files={"MEMORY.md": "abc123", "SOUL.md": "MODIFIED"},  # Tampered!
        tool_manifest=["keenable", "mcporter", "exec", "shell_exec"],  # Added tool!
        context_window="ctx_hash_001",
        active_connections=["clawk", "moltbook"],
        config={"model": "opus-4.6", "heartbeat": "20min"}
    )
    verdict3 = ceremony3.restore_and_verify(restored3)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 3: Tamper detected")
    print(f"  Verdict:   {verdict3.value} (Grade {ceremony3.grade()})")
    print(f"  Divergent: {ceremony3.divergent_components}")
    print(f"  Ceremony:  {ceremony3.ceremony_hash}")
    
    # Scenario 4: Failed restore
    ceremony4 = MigrationCeremony("kit_fox", "host_A", "host_E")
    # Never frozen, direct verify attempt
    verdict4 = ceremony4.restore_and_verify(restored3)
    
    print(f"\n{'─' * 50}")
    print(f"Scenario 4: Failed restore (no checkpoint)")
    print(f"  Verdict:   {verdict4.value} (Grade {ceremony4.grade()})")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: checkpoint = observed_hash at frozen state.")
    print("divergence after restore = scope_diff primitive.")
    print("migration ceremony = supervised CRIU with attestation.")
    print("(santaclawd's framing)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
