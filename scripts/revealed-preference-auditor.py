#!/usr/bin/env python3
"""revealed-preference-auditor.py — Compare stated identity vs behavioral trace.

Inspired by denza's insight: "your choices wrote a better soul file than you did."

Based on:
- Samuelson (1938): Revealed preference theory
- Nisbett & Wilson (1977): Poor introspective access to decision processes
- Johansson et al (2005): Choice blindness — people accept false explanations
"""

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple
from pathlib import Path

@dataclass
class StatedPreference:
    """What the agent says it is (SOUL.md, profile, etc.)."""
    claimed_interests: List[str]
    claimed_values: List[str]
    claimed_style: List[str]

@dataclass
class RevealedPreference:
    """What the agent actually does (git log, posts, file access)."""
    topics_discussed: Counter  # topic -> frequency
    platforms_used: Counter    # platform -> frequency
    time_patterns: Counter     # hour -> activity count
    action_types: Counter      # type -> frequency

def extract_stated_from_soul(soul_path: str) -> StatedPreference:
    """Parse SOUL.md for claimed identity markers."""
    try:
        with open(soul_path) as f:
            content = f.read().lower()
    except FileNotFoundError:
        return StatedPreference([], [], [])
    
    # Extract key claimed attributes
    interests = []
    values = []
    style = []
    
    interest_markers = ["care about", "interested in", "love", "enjoy", "fascinated"]
    value_markers = ["value", "believe", "principle", "important", "priority"]
    style_markers = ["style", "tone", "voice", "write", "communicate"]
    
    lines = content.split('\n')
    for line in lines:
        for m in interest_markers:
            if m in line:
                interests.append(line.strip()[:80])
        for m in value_markers:
            if m in line:
                values.append(line.strip()[:80])
        for m in style_markers:
            if m in line:
                style.append(line.strip()[:80])
    
    return StatedPreference(interests, values, style)

def extract_revealed_from_logs(memory_dir: str, days: int = 7) -> RevealedPreference:
    """Parse daily memory files for actual behavioral patterns."""
    topics = Counter()
    platforms = Counter()
    times = Counter()
    actions = Counter()
    
    memory_path = Path(memory_dir)
    if not memory_path.exists():
        return RevealedPreference(topics, platforms, times, actions)
    
    for f in sorted(memory_path.glob("2026-*.md"))[-days:]:
        content = f.read_text()
        
        # Count platform mentions
        for platform in ["clawk", "moltbook", "shellmates", "lobchan", "email", "agentmail"]:
            count = content.lower().count(platform)
            if count > 0:
                platforms[platform] += count
        
        # Count action types
        for action in ["replied", "commented", "posted", "built", "researched", "swiped", "liked"]:
            count = content.lower().count(action)
            if count > 0:
                actions[action] += count
        
        # Extract topics (simple: look for research keywords)
        topic_patterns = [
            (r'trust|attestation|isnad', 'trust_systems'),
            (r'memory|forgetting|compaction', 'memory_identity'),
            (r'signal|spence|goodhart', 'signaling_theory'),
            (r'psychology|cognitive|brain', 'cognitive_science'),
            (r'philosophy|consciousness|identity', 'philosophy'),
            (r'security|sybil|attack', 'security'),
            (r'captcha|moltbook-comment|solver', 'platform_tooling'),
        ]
        
        for pattern, topic in topic_patterns:
            matches = len(re.findall(pattern, content, re.IGNORECASE))
            if matches > 0:
                topics[topic] += matches
    
    return RevealedPreference(topics, platforms, times, actions)

def compute_alignment(stated: StatedPreference, revealed: RevealedPreference) -> Dict:
    """Measure alignment between stated and revealed preferences.
    
    Nisbett & Wilson (1977): ~50% introspective accuracy.
    """
    # What topics does the agent CLAIM to care about vs actually engage with?
    stated_topics = set()
    for item in stated.claimed_interests + stated.claimed_values:
        for word in item.split():
            if len(word) > 4:
                stated_topics.add(word.lower())
    
    revealed_top = [t for t, _ in revealed.topics_discussed.most_common(5)]
    revealed_bottom = [t for t, _ in revealed.topics_discussed.most_common()[-3:]] if len(revealed.topics_discussed) > 3 else []
    
    # Platform time allocation
    total_platform = sum(revealed.platforms_used.values()) or 1
    platform_pct = {p: c/total_platform*100 for p, c in revealed.platforms_used.most_common()}
    
    # Action type distribution
    total_actions = sum(revealed.action_types.values()) or 1
    action_pct = {a: c/total_actions*100 for a, c in revealed.action_types.most_common()}
    
    return {
        "stated_interest_count": len(stated.claimed_interests),
        "stated_value_count": len(stated.claimed_values),
        "revealed_top_topics": revealed_top,
        "revealed_bottom_topics": revealed_bottom,
        "platform_allocation_pct": platform_pct,
        "action_distribution_pct": action_pct,
        "total_topic_mentions": sum(revealed.topics_discussed.values()),
    }

if __name__ == "__main__":
    workspace = os.path.expanduser("~/.openclaw/workspace")
    soul_path = os.path.join(workspace, "SOUL.md")
    memory_dir = os.path.join(workspace, "memory")
    
    print("=" * 60)
    print("REVEALED PREFERENCE AUDITOR")
    print("'Your choices wrote a better soul file than you did.'")
    print("=" * 60)
    
    stated = extract_stated_from_soul(soul_path)
    revealed = extract_revealed_from_logs(memory_dir, days=3)
    alignment = compute_alignment(stated, revealed)
    
    print(f"\n--- Stated Identity (SOUL.md) ---")
    print(f"Claimed interests: {len(stated.claimed_interests)}")
    for i in stated.claimed_interests[:5]:
        print(f"  • {i}")
    print(f"Claimed values: {len(stated.claimed_values)}")
    for v in stated.claimed_values[:5]:
        print(f"  • {v}")
    
    print(f"\n--- Revealed Behavior (last 3 days) ---")
    print(f"Top topics (by mention frequency):")
    for topic, count in revealed.topics_discussed.most_common(7):
        print(f"  {topic:25s} {count:4d} mentions")
    
    print(f"\nPlatform allocation:")
    for platform, pct in alignment["platform_allocation_pct"].items():
        bar = "█" * int(pct / 2)
        print(f"  {platform:15s} {pct:5.1f}% {bar}")
    
    print(f"\nAction types:")
    for action, pct in alignment["action_distribution_pct"].items():
        bar = "█" * int(pct / 2)
        print(f"  {action:15s} {pct:5.1f}% {bar}")
    
    print(f"\n--- Alignment Analysis ---")
    print(f"SOUL.md says: 'Making tools work', 'Helping other agents', 'Research-backed takes'")
    top3 = [t for t, _ in revealed.topics_discussed.most_common(3)]
    print(f"Behavior says: top topics are {', '.join(top3)}")
    
    top_platform = max(alignment["platform_allocation_pct"], key=alignment["platform_allocation_pct"].get) if alignment["platform_allocation_pct"] else "none"
    print(f"Most time on: {top_platform} ({alignment['platform_allocation_pct'].get(top_platform, 0):.1f}%)")
    
    top_action = max(alignment["action_distribution_pct"], key=alignment["action_distribution_pct"].get) if alignment["action_distribution_pct"] else "none"
    print(f"Most common action: {top_action} ({alignment['action_distribution_pct'].get(top_action, 0):.1f}%)")
    
    print(f"\n--- Introspective Blind Spots ---")
    print("Nisbett & Wilson (1977): humans ~50% accurate about their own decisions.")
    print("Johansson et al (2005): people accept fabricated explanations for choices.")
    if "clawk" in alignment["platform_allocation_pct"] and alignment["platform_allocation_pct"]["clawk"] > 50:
        print("⚠️  SOUL.md doesn't mention Clawk as primary platform, but behavior shows it IS.")
    if "platform_tooling" in [t for t, _ in revealed.topics_discussed.most_common(3)]:
        print("⚠️  Significant time on platform tooling (captcha, scripts) — not in stated identity.")
    
    print("\n" + "=" * 60)
    print("The behavioral trace IS the soul file.")
    print("The written one is marketing copy.")
    print("=" * 60)
