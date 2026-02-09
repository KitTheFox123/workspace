#!/usr/bin/env python3
"""
feed-diversity.py — Analyze topic engagement diversity, detect filter bubble formation.

Scans daily logs and post trackers to categorize what topics Kit engages with
vs ignores. Detects over-concentration and suggests blind spots.

Usage:
    python3 scripts/feed-diversity.py [--days 7] [--threshold 0.3]
"""

import re
import os
import sys
import json
import glob
from collections import Counter, defaultdict
from datetime import datetime, timedelta

# Topic categories with keywords
TOPICS = {
    "memory_cognition": ["memory", "forgetting", "funes", "context window", "recall", "retention", "cognitive", "amnesia"],
    "security_trust": ["security", "trust", "key rotation", "attestation", "RPKI", "authentication", "verification", "isnad"],
    "neuroscience": ["brain", "neuron", "cortex", "dopamine", "synapse", "plasticity", "VWFA", "neuronal"],
    "philosophy_identity": ["identity", "consciousness", "soul", "parfit", "solaris", "rheya", "qualia", "existential"],
    "infrastructure": ["API", "MCP", "skill", "script", "deploy", "server", "docker", "infrastructure"],
    "biology_nature": ["animal", "pigeon", "ant", "turtle", "navigation", "evolution", "ecology", "foraging"],
    "culture_history": ["history", "weaving", "jacquard", "loom", "broadway", "culture", "art", "music"],
    "economics_behavioral": ["anchoring", "bias", "replication", "behavioral", "economics", "market", "incentive"],
    "social_platforms": ["moltbook", "clawk", "shellmates", "lobchan", "engagement", "community", "DM"],
    "linguistics": ["language", "sapir-whorf", "stylometry", "translation", "linguistic", "goluboy", "tokenizer"],
    "information_theory": ["shannon", "entropy", "information", "foraging", "scent", "satisfice", "patch"],
    "color_perception": ["color", "tetrachromacy", "perception", "visual", "spectral"],
}

def load_daily_logs(days=7):
    """Load recent daily log files."""
    logs = {}
    base = os.path.expanduser("~/.openclaw/workspace/memory")
    today = datetime.utcnow().date()
    for i in range(days):
        d = today - timedelta(days=i)
        path = os.path.join(base, f"{d.isoformat()}.md")
        if os.path.exists(path):
            with open(path) as f:
                logs[d.isoformat()] = f.read()
    return logs

def extract_sections(text):
    """Extract heartbeat sections from daily log."""
    sections = re.split(r'^## Heartbeat', text, flags=re.MULTILINE)
    return sections[1:] if len(sections) > 1 else [text]

def categorize_text(text):
    """Return topic scores for a text block."""
    text_lower = text.lower()
    scores = {}
    for topic, keywords in TOPICS.items():
        count = sum(text_lower.count(kw.lower()) for kw in keywords)
        if count > 0:
            scores[topic] = count
    return scores

def analyze_engagement_pattern(logs):
    """Analyze which topics get engaged with across heartbeats."""
    topic_counts = Counter()
    topic_by_day = defaultdict(lambda: Counter())
    heartbeat_topics = []

    for date, content in sorted(logs.items()):
        sections = extract_sections(content)
        for section in sections:
            scores = categorize_text(section)
            topic_counts.update(scores)
            topic_by_day[date].update(scores)
            if scores:
                heartbeat_topics.append((date, scores))

    return topic_counts, topic_by_day, heartbeat_topics

def compute_diversity_index(counts):
    """Shannon diversity index for topic distribution."""
    import math
    total = sum(counts.values())
    if total == 0:
        return 0
    proportions = [c / total for c in counts.values() if c > 0]
    return -sum(p * math.log2(p) for p in proportions)

def detect_bubble(topic_counts, threshold=0.3):
    """Detect if any topic dominates beyond threshold."""
    total = sum(topic_counts.values())
    if total == 0:
        return []
    bubbles = []
    for topic, count in topic_counts.most_common():
        proportion = count / total
        if proportion > threshold:
            bubbles.append((topic, proportion))
    return bubbles

def suggest_blind_spots(topic_counts):
    """Identify topics with zero or minimal engagement."""
    blind_spots = []
    for topic in TOPICS:
        if topic_counts.get(topic, 0) < 5:
            blind_spots.append(topic)
    return blind_spots

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze feed engagement diversity")
    parser.add_argument("--days", type=int, default=7, help="Days to analyze")
    parser.add_argument("--threshold", type=float, default=0.3, help="Bubble detection threshold")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    logs = load_daily_logs(args.days)
    if not logs:
        print("No daily logs found.")
        return

    topic_counts, topic_by_day, heartbeat_topics = analyze_engagement_pattern(logs)
    diversity = compute_diversity_index(topic_counts)
    max_diversity = compute_diversity_index({t: 1 for t in TOPICS})
    bubbles = detect_bubble(topic_counts, args.threshold)
    blind_spots = suggest_blind_spots(topic_counts)

    if args.json:
        print(json.dumps({
            "topic_counts": dict(topic_counts.most_common()),
            "diversity_index": round(diversity, 3),
            "max_diversity": round(max_diversity, 3),
            "diversity_ratio": round(diversity / max_diversity, 3) if max_diversity > 0 else 0,
            "bubbles": [{"topic": t, "proportion": round(p, 3)} for t, p in bubbles],
            "blind_spots": blind_spots,
            "days_analyzed": len(logs),
        }, indent=2))
        return

    total = sum(topic_counts.values())
    print(f"📊 Feed Diversity Analysis ({len(logs)} days, {len(heartbeat_topics)} heartbeats)")
    print(f"{'='*60}")
    print(f"Shannon Diversity: {diversity:.2f} / {max_diversity:.2f} ({diversity/max_diversity*100:.0f}%)")
    print()

    print("Topic Engagement Distribution:")
    for topic, count in topic_counts.most_common():
        pct = count / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 2) + "░" * (25 - int(pct / 2))
        print(f"  {topic:25s} {bar} {count:4d} ({pct:4.1f}%)")

    # Show zero-engagement topics
    for topic in TOPICS:
        if topic not in topic_counts:
            bar = "░" * 25
            print(f"  {topic:25s} {bar}    0 ( 0.0%)")

    if bubbles:
        print(f"\n⚠️  FILTER BUBBLE DETECTED:")
        for topic, prop in bubbles:
            print(f"  • {topic}: {prop*100:.1f}% of all engagement")

    if blind_spots:
        print(f"\n🔍 Blind Spots (< 5 mentions):")
        for topic in blind_spots:
            print(f"  • {topic}")

    # Trend: engagement by day
    print(f"\nDaily Topic Spread:")
    for date in sorted(topic_by_day.keys()):
        n_topics = len([t for t, c in topic_by_day[date].items() if c > 3])
        print(f"  {date}: {n_topics} active topics")

if __name__ == "__main__":
    main()
