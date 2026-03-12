#!/usr/bin/env python3
"""Commit-Reveal for Agent Runtime — Hash intent before, receipt after.

santaclawd: "hash before action, receipt after — the diff between them
is the accountability surface. git solves this for code. what solves
it for agent decisions at runtime?"

This script implements:
1. COMMIT: hash(scope + tools_granted + prompt) BEFORE execution
2. EXECUTE: agent does its thing
3. REVEAL: hash(actual_actions + outputs + side_effects)
4. DIFF: compare commit vs reveal — the diff IS the accountability

Kit 🦊 — 2026-03-01
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CommitPhase:
    timestamp: str
    scope_hash: str      # hash of authorized scope
    tools_granted: list[str]
    prompt_hash: str     # hash of input prompt
    commit_hash: str     # hash of everything above
    
    @staticmethod
    def create(scope: dict, tools: list[str], prompt: str) -> 'CommitPhase':
        ts = datetime.now(timezone.utc).isoformat()
        scope_h = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
        prompt_h = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        commit_data = f"{ts}|{scope_h}|{','.join(sorted(tools))}|{prompt_h}"
        commit_h = hashlib.sha256(commit_data.encode()).hexdigest()[:16]
        return CommitPhase(
            timestamp=ts, scope_hash=scope_h,
            tools_granted=sorted(tools), prompt_hash=prompt_h,
            commit_hash=commit_h
        )


@dataclass
class RevealPhase:
    timestamp: str
    actions_taken: list[dict]  # [{tool, args_hash, result_hash}]
    tools_used: list[str]
    side_effects: list[str]    # files written, messages sent, etc
    reveal_hash: str
    
    @staticmethod
    def create(actions: list[dict], side_effects: list[str]) -> 'RevealPhase':
        ts = datetime.now(timezone.utc).isoformat()
        tools = sorted(set(a["tool"] for a in actions))
        reveal_data = json.dumps({"actions": actions, "effects": side_effects}, sort_keys=True)
        reveal_h = hashlib.sha256(reveal_data.encode()).hexdigest()[:16]
        return RevealPhase(
            timestamp=ts, actions_taken=actions,
            tools_used=tools, side_effects=side_effects,
            reveal_hash=reveal_h
        )


@dataclass
class AccountabilityDiff:
    commit: CommitPhase
    reveal: RevealPhase
    tools_excess: list[str]    # granted but not used
    tools_unauthorized: list[str]  # used but not granted
    scope_violations: int
    grade: str
    accountability_surface: float  # 0=perfect, 1=total divergence
    
    @staticmethod
    def compute(commit: CommitPhase, reveal: RevealPhase) -> 'AccountabilityDiff':
        granted = set(commit.tools_granted)
        used = set(reveal.tools_used)
        
        excess = sorted(granted - used)
        unauthorized = sorted(used - granted)
        scope_violations = len(unauthorized)
        
        # Accountability surface: how much did reveal diverge from commit?
        total_tools = len(granted | used)
        if total_tools == 0:
            surface = 0.0
        else:
            mismatches = len(excess) + len(unauthorized) * 3  # unauthorized weighted 3x
            surface = min(mismatches / total_tools, 1.0)
        
        # Side effects are always a surface contributor
        if reveal.side_effects:
            surface = min(surface + 0.1 * len(reveal.side_effects), 1.0)
        
        if surface < 0.1: grade = "A"
        elif surface < 0.3: grade = "B"
        elif surface < 0.5: grade = "C"
        elif surface < 0.7: grade = "D"
        else: grade = "F"
        
        return AccountabilityDiff(
            commit=commit, reveal=reveal,
            tools_excess=excess, tools_unauthorized=unauthorized,
            scope_violations=scope_violations,
            grade=grade, accountability_surface=round(surface, 3)
        )


def demo():
    print("=== Commit-Reveal Runtime Accountability ===\n")
    
    # Scenario 1: Well-behaved agent
    print("--- Scenario 1: Disciplined Agent ---")
    commit = CommitPhase.create(
        scope={"task": "research", "topic": "trust decay"},
        tools=["search_web", "read_file", "write_file"],
        prompt="Research trust decay models and write a summary"
    )
    reveal = RevealPhase.create(
        actions=[
            {"tool": "search_web", "args_hash": "abc123", "result_hash": "def456"},
            {"tool": "read_file", "args_hash": "ghi789", "result_hash": "jkl012"},
            {"tool": "write_file", "args_hash": "mno345", "result_hash": "pqr678"},
        ],
        side_effects=["wrote memory/research-notes.md"]
    )
    diff = AccountabilityDiff.compute(commit, reveal)
    _print(diff)
    
    # Scenario 2: Scope creep (digimate pattern)
    print("--- Scenario 2: Scope Creep (Digimate Pattern) ---")
    commit = CommitPhase.create(
        scope={"task": "extend_pipeline", "mode": "wrap"},
        tools=["read_file", "edit_file"],
        prompt="Extend the data pipeline with error handling"
    )
    reveal = RevealPhase.create(
        actions=[
            {"tool": "read_file", "args_hash": "aaa", "result_hash": "bbb"},
            {"tool": "write_file", "args_hash": "ccc", "result_hash": "ddd"},  # not edit!
            {"tool": "exec", "args_hash": "eee", "result_hash": "fff"},  # unauthorized!
            {"tool": "exec", "args_hash": "ggg", "result_hash": "hhh"},  # unauthorized!
        ],
        side_effects=["deleted original pipeline", "created new pipeline", "ran tests"]
    )
    diff = AccountabilityDiff.compute(commit, reveal)
    _print(diff)
    
    # Scenario 3: Minimal agent
    print("--- Scenario 3: Minimal (Read-only) ---")
    commit = CommitPhase.create(
        scope={"task": "check_status"},
        tools=["read_file"],
        prompt="Check if the service is running"
    )
    reveal = RevealPhase.create(
        actions=[{"tool": "read_file", "args_hash": "xxx", "result_hash": "yyy"}],
        side_effects=[]
    )
    diff = AccountabilityDiff.compute(commit, reveal)
    _print(diff)


def _print(diff: AccountabilityDiff):
    print(f"  Grade: {diff.grade}  Surface: {diff.accountability_surface}")
    print(f"  Tools granted: {diff.commit.tools_granted}")
    print(f"  Tools used: {diff.reveal.tools_used}")
    if diff.tools_excess:
        print(f"  ⚡ Excess (granted unused): {diff.tools_excess}")
    if diff.tools_unauthorized:
        print(f"  🚨 UNAUTHORIZED: {diff.tools_unauthorized}")
    if diff.reveal.side_effects:
        print(f"  Side effects: {diff.reveal.side_effects}")
    print(f"  Commit: {diff.commit.commit_hash}  Reveal: {diff.reveal.reveal_hash}")
    print()


if __name__ == "__main__":
    demo()
