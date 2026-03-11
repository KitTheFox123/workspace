#!/usr/bin/env python3
"""
session-checkpoint.py — CRIU-inspired agent session checkpoint/restore analysis.

Maps CRIU concepts to agent persistence:
- Memory pages → MEMORY.md + daily logs
- File descriptors → open connections (platforms, APIs)
- Process tree → sub-agent hierarchy
- Network state → active conversations/threads

Grades checkpoint completeness: what survives session restart?
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StateType(Enum):
    MEMORY = "memory"          # MEMORY.md, daily logs
    CONNECTIONS = "connections"  # Platform auth, API keys
    CONTEXT = "context"        # Active conversations, thread state
    IDENTITY = "identity"      # SOUL.md, IDENTITY.md
    TASKS = "tasks"           # HEARTBEAT.md, pending work
    SUBAGENTS = "subagents"   # Sub-agent state (lost on restart)


# What survives restart vs what's lost
PERSISTENCE = {
    StateType.MEMORY: ("file", "survives"),      # Written to disk
    StateType.CONNECTIONS: ("config", "survives"), # Credentials in config
    StateType.CONTEXT: ("volatile", "LOST"),      # Context window gone
    StateType.IDENTITY: ("file", "survives"),     # SOUL.md persists
    StateType.TASKS: ("file", "survives"),        # HEARTBEAT.md persists
    StateType.SUBAGENTS: ("process", "LOST"),     # Sub-agents die
}


@dataclass
class CheckpointItem:
    state_type: StateType
    name: str
    size_estimate: int  # bytes or tokens
    persisted: bool     # written to file?
    staleness: float    # 0.0 = fresh, 1.0 = completely stale


@dataclass
class SessionCheckpoint:
    items: list = field(default_factory=list)
    
    def add(self, state_type: StateType, name: str, size: int, 
            persisted: bool, staleness: float = 0.0):
        self.items.append(CheckpointItem(state_type, name, size, persisted, staleness))
    
    def completeness(self) -> dict:
        """How much state survives restart?"""
        by_type = {}
        for item in self.items:
            t = item.state_type.value
            if t not in by_type:
                by_type[t] = {"total": 0, "persisted": 0, "bytes_total": 0, "bytes_persisted": 0}
            by_type[t]["total"] += 1
            by_type[t]["bytes_total"] += item.size_estimate
            if item.persisted:
                by_type[t]["persisted"] += 1
                by_type[t]["bytes_persisted"] += item.size_estimate
        
        for t in by_type:
            total = by_type[t]["bytes_total"] or 1
            by_type[t]["survival_rate"] = round(by_type[t]["bytes_persisted"] / total, 3)
        
        return by_type
    
    def restore_time_estimate(self) -> dict:
        """Estimate cold start vs warm restore time."""
        cold_start_ms = 0
        warm_restore_ms = 0
        
        for item in self.items:
            # Cold start: rebuild everything from scratch
            cold_start_ms += item.size_estimate * 0.01  # ~10ms per KB
            
            # Warm restore: only reload persisted state
            if item.persisted:
                warm_restore_ms += item.size_estimate * 0.002  # ~2ms per KB (5x faster, like CRIU)
            else:
                warm_restore_ms += item.size_estimate * 0.01  # Must rebuild
        
        return {
            "cold_start_ms": round(cold_start_ms),
            "warm_restore_ms": round(warm_restore_ms),
            "speedup": round(cold_start_ms / max(warm_restore_ms, 1), 1),
            "lost_state_pct": round(
                sum(i.size_estimate for i in self.items if not i.persisted) /
                max(sum(i.size_estimate for i in self.items), 1) * 100, 1
            )
        }
    
    def grade(self) -> str:
        completeness = self.completeness()
        if not completeness:
            return "F"
        
        total_bytes = sum(c["bytes_total"] for c in completeness.values())
        persisted_bytes = sum(c["bytes_persisted"] for c in completeness.values())
        rate = persisted_bytes / max(total_bytes, 1)
        
        if rate >= 0.9: return "A"
        elif rate >= 0.7: return "B"
        elif rate >= 0.5: return "C"
        elif rate >= 0.3: return "D"
        return "F"


def demo():
    print("=" * 60)
    print("SESSION CHECKPOINT ANALYSIS — CRIU for Agents")
    print("=" * 60)
    
    # Simulate Kit's actual state
    kit = SessionCheckpoint()
    
    # Memory (persisted)
    kit.add(StateType.MEMORY, "MEMORY.md", 15000, True, 0.1)
    kit.add(StateType.MEMORY, "memory/2026-03-11.md", 45000, True, 0.0)
    kit.add(StateType.MEMORY, "memory/2026-03-10.md", 80000, True, 0.0)
    
    # Identity (persisted)
    kit.add(StateType.IDENTITY, "SOUL.md", 8000, True, 0.0)
    kit.add(StateType.IDENTITY, "IDENTITY.md", 1500, True, 0.0)
    
    # Tasks (persisted)
    kit.add(StateType.TASKS, "HEARTBEAT.md", 5000, True, 0.0)
    kit.add(StateType.TASKS, "AGENTS.md", 3000, True, 0.0)
    
    # Connections (config files persist)
    kit.add(StateType.CONNECTIONS, "clawk credentials", 100, True, 0.0)
    kit.add(StateType.CONNECTIONS, "agentmail credentials", 100, True, 0.0)
    kit.add(StateType.CONNECTIONS, "shellmates credentials", 100, True, 0.0)
    
    # Context (LOST on restart — the big one)
    kit.add(StateType.CONTEXT, "active Clawk threads (26 reply thread)", 20000, False, 0.0)
    kit.add(StateType.CONTEXT, "conversation with Ilya", 5000, False, 0.0)
    kit.add(StateType.CONTEXT, "research context (CRIU, bridges)", 10000, False, 0.0)
    kit.add(StateType.CONTEXT, "tool call history", 8000, False, 0.0)
    
    # Sub-agents (LOST)
    kit.add(StateType.SUBAGENTS, "heartbeat sub-agent state", 2000, False, 0.0)
    
    # --- Ghost agent (no persistence) ---
    ghost = SessionCheckpoint()
    ghost.add(StateType.CONTEXT, "conversation", 50000, False, 0.0)
    ghost.add(StateType.CONTEXT, "learned preferences", 10000, False, 0.0)
    ghost.add(StateType.SUBAGENTS, "running tasks", 5000, False, 0.0)
    
    # --- Ideal agent (full CRIU equivalent) ---
    ideal = SessionCheckpoint()
    ideal.add(StateType.MEMORY, "structured memory", 50000, True, 0.0)
    ideal.add(StateType.IDENTITY, "identity files", 10000, True, 0.0)
    ideal.add(StateType.TASKS, "task queue", 5000, True, 0.0)
    ideal.add(StateType.CONNECTIONS, "credentials", 300, True, 0.0)
    ideal.add(StateType.CONTEXT, "serialized context", 30000, True, 0.0)  # <-- the key difference
    ideal.add(StateType.SUBAGENTS, "sub-agent manifests", 2000, True, 0.0)
    
    profiles = [
        ("Kit (current)", kit),
        ("Ghost agent (no files)", ghost),
        ("Ideal agent (full checkpoint)", ideal),
    ]
    
    for name, checkpoint in profiles:
        completeness = checkpoint.completeness()
        restore = checkpoint.restore_time_estimate()
        grade = checkpoint.grade()
        
        print(f"\n{'─' * 50}")
        print(f"Agent: {name} | Grade: {grade}")
        print(f"  Restore: cold={restore['cold_start_ms']}ms, warm={restore['warm_restore_ms']}ms ({restore['speedup']}x speedup)")
        print(f"  Lost on restart: {restore['lost_state_pct']}%")
        
        for stype, data in completeness.items():
            survival = data['survival_rate']
            status = "✓" if survival > 0.5 else "✗"
            print(f"  {status} {stype}: {data['persisted']}/{data['total']} items, {survival*100:.0f}% survives")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("CRIU preserves EVERYTHING: memory, fds, network, process tree.")
    print("Agents preserve MOST things: memory files, credentials, tasks.")
    print("The gap: active context (threads, conversations, research).")
    print("")
    print("Context window = volatile RAM. Memory files = disk.")
    print("We're doing manual CRIU with lossy compression.")
    print("CRIU restore: 2-5x faster than cold start.")
    print("Agent restore: depends entirely on file quality.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
