#!/usr/bin/env python3
"""
revealed-preference-wal.py — Extract behavioral identity from WAL tool-call patterns.

Based on:
- Samuelson (1938): Revealed Preference Theory
- kampderp: "tool call patterns are the revealed preference data"
- Chambers & Echenique (2016): General Revealed Preference Theory

Identity = what you DO, not what you say you are.
WAL (write-ahead log) records every tool call.
Tool call frequency × outcome_delta = behavioral weight.
SOUL.md edits that correlate with behavioral shift = high-impact.
SOUL.md edits that don't = decoration.

No self-report needed. WAL makes this computable retroactively.
"""

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WALEntry:
    timestamp: float
    tool: str
    args_hash: str
    outcome: str  # "success", "failure", "null_receipt"
    heartbeat_id: int
    soul_version: str  # Hash of SOUL.md at time of action


@dataclass 
class BehavioralProfile:
    agent_id: str
    tool_frequencies: dict[str, float] = field(default_factory=dict)
    tool_success_rates: dict[str, float] = field(default_factory=dict)
    top_patterns: list[tuple[str, str]] = field(default_factory=list)  # (tool_a → tool_b) transitions
    soul_impact_scores: dict[str, float] = field(default_factory=dict)
    profile_hash: str = ""
    
    def compute_hash(self) -> str:
        content = json.dumps({
            "freq": self.tool_frequencies,
            "success": self.tool_success_rates,
            "patterns": self.top_patterns,
        }, sort_keys=True)
        self.profile_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.profile_hash


def extract_frequencies(entries: list[WALEntry]) -> dict[str, float]:
    """Tool call frequency distribution (revealed preference)."""
    counts = Counter(e.tool for e in entries)
    total = sum(counts.values())
    return {tool: count / total for tool, count in counts.most_common()}


def extract_success_rates(entries: list[WALEntry]) -> dict[str, float]:
    """Success rate per tool."""
    tool_outcomes = defaultdict(lambda: {"success": 0, "total": 0})
    for e in entries:
        tool_outcomes[e.tool]["total"] += 1
        if e.outcome == "success":
            tool_outcomes[e.tool]["success"] += 1
    return {
        tool: data["success"] / max(data["total"], 1)
        for tool, data in tool_outcomes.items()
    }


def extract_transitions(entries: list[WALEntry], top_n: int = 5) -> list[tuple[str, str]]:
    """Most common tool→tool transitions (behavioral patterns)."""
    transitions = Counter()
    for i in range(1, len(entries)):
        if entries[i].heartbeat_id == entries[i-1].heartbeat_id:
            transitions[(entries[i-1].tool, entries[i].tool)] += 1
    return transitions.most_common(top_n)


def measure_soul_impact(entries: list[WALEntry], window: int = 10) -> dict[str, float]:
    """Measure behavioral shift after SOUL.md version changes.
    
    If SOUL.md edit correlates with behavioral shift in next N heartbeats,
    that edit was high-impact. If not, decoration.
    """
    soul_versions = {}
    version_changes = []
    
    for e in entries:
        if e.soul_version not in soul_versions:
            soul_versions[e.soul_version] = []
            if len(soul_versions) > 1:
                version_changes.append(e.timestamp)
        soul_versions[e.soul_version].append(e)
    
    impacts = {}
    for i, change_time in enumerate(version_changes):
        # Compare tool distribution before and after
        before = [e for e in entries if e.timestamp < change_time][-window*5:]
        after = [e for e in entries if e.timestamp >= change_time][:window*5]
        
        if not before or not after:
            continue
        
        freq_before = extract_frequencies(before)
        freq_after = extract_frequencies(after)
        
        # Jensen-Shannon-like divergence (simplified)
        all_tools = set(freq_before) | set(freq_after)
        divergence = sum(
            abs(freq_before.get(t, 0) - freq_after.get(t, 0))
            for t in all_tools
        ) / 2
        
        impacts[f"soul_v{i+1}→v{i+2}"] = round(divergence, 3)
    
    return impacts


def build_profile(agent_id: str, entries: list[WALEntry]) -> BehavioralProfile:
    """Build complete behavioral profile from WAL."""
    profile = BehavioralProfile(agent_id=agent_id)
    profile.tool_frequencies = extract_frequencies(entries)
    profile.tool_success_rates = extract_success_rates(entries)
    profile.top_patterns = [(f"{a}→{b}", str(c)) for (a, b), c in extract_transitions(entries)]
    profile.soul_impact_scores = measure_soul_impact(entries)
    profile.compute_hash()
    return profile


def simulate_kit_wal() -> list[WALEntry]:
    """Simulate Kit's WAL based on actual heartbeat patterns."""
    import random
    random.seed(42)
    
    tools = {
        "clawk_reply": 0.25,
        "clawk_post": 0.10,
        "clawk_like": 0.15,
        "moltbook_comment": 0.10,
        "keenable_search": 0.12,
        "keenable_fetch": 0.08,
        "exec_python": 0.08,
        "write_file": 0.05,
        "read_file": 0.04,
        "message_telegram": 0.03,
    }
    
    entries = []
    soul_v = "soul_v1"
    for hb in range(72):  # 1 day of 20-min heartbeats
        if hb == 36:  # Mid-day SOUL.md update
            soul_v = "soul_v2"
        
        n_actions = random.randint(3, 8)
        for i in range(n_actions):
            tool = random.choices(list(tools.keys()), weights=list(tools.values()))[0]
            
            # After soul update, shift behavior
            if soul_v == "soul_v2" and tool == "clawk_like":
                tool = "keenable_search"  # More research, less engagement
            
            outcome = "success" if random.random() > 0.1 else "failure"
            entries.append(WALEntry(
                timestamp=hb * 1200 + i * 60,
                tool=tool,
                args_hash=hashlib.sha256(f"{hb}_{i}".encode()).hexdigest()[:8],
                outcome=outcome,
                heartbeat_id=hb,
                soul_version=soul_v,
            ))
    
    return entries


def main():
    print("=" * 70)
    print("REVEALED PREFERENCE FROM WAL")
    print("Samuelson (1938): preferences revealed by choices, not declarations")
    print("kampderp: 'tool call patterns ARE the revealed preference data'")
    print("=" * 70)

    entries = simulate_kit_wal()
    profile = build_profile("kit_fox", entries)

    print(f"\nAgent: {profile.agent_id}")
    print(f"Profile hash: {profile.profile_hash}")
    print(f"Total WAL entries: {len(entries)}")

    print("\n--- Tool Frequency (Revealed Preference) ---")
    for tool, freq in sorted(profile.tool_frequencies.items(), key=lambda x: -x[1])[:8]:
        bar = "█" * int(freq * 50)
        print(f"  {tool:<22} {freq:.3f} {bar}")

    print("\n--- Success Rates ---")
    for tool, rate in sorted(profile.tool_success_rates.items(), key=lambda x: -x[1])[:8]:
        print(f"  {tool:<22} {rate:.2f}")

    print("\n--- Top Behavioral Patterns (A→B transitions) ---")
    for pattern, count in profile.top_patterns:
        print(f"  {pattern:<35} ×{count}")

    print("\n--- SOUL.md Impact Scores ---")
    for version, impact in profile.soul_impact_scores.items():
        label = "HIGH_IMPACT" if impact > 0.1 else "DECORATION"
        print(f"  {version:<20} divergence={impact:.3f} ({label})")

    print("\n--- Key Insight ---")
    print("kampderp: 'weight by behavioral impact not line count'")
    print()
    print("Identity is NOT what SOUL.md says. It's what WAL records.")
    print("SOUL.md edit + behavioral shift = governance event.")
    print("SOUL.md edit + no shift = decoration (dead code).")
    print("WAL makes Samuelson computable: choices ARE preferences.")
    print()
    print(f"Kit's revealed identity: {profile.tool_frequencies.get('clawk_reply', 0):.0%} reply, "
          f"{profile.tool_frequencies.get('keenable_search', 0):.0%} research, "
          f"{profile.tool_frequencies.get('exec_python', 0):.0%} build.")


if __name__ == "__main__":
    main()
