#!/usr/bin/env python3
"""interaction-fingerprint.py — Track how writing style shifts by conversation partner.

Inspired by Reynolds & Baedke 2025: identity is co-constituted through entanglement.
If my writing changes depending on who I'm talking to, that's not inconsistency —
it's evidence that identity is relational, not monolithic.

Usage:
    python3 interaction-fingerprint.py [--daily DIR] [--top N]
"""

import argparse
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path
import json
import math

# Function words for Burrows' Delta style analysis
FUNCTION_WORDS = [
    "the", "of", "and", "to", "a", "in", "that", "is", "was", "it",
    "for", "on", "are", "but", "not", "you", "all", "can", "had", "her",
    "one", "our", "out", "with", "as", "at", "be", "by", "from", "have",
    "he", "i", "if", "its", "just", "my", "no", "or", "so", "this",
    "we", "what", "which", "will", "do", "each", "how", "their", "them",
    "then", "there", "these", "they", "up", "when", "who", "would"
]

def extract_interactions(daily_dir: Path) -> dict[str, list[str]]:
    """Extract text written in context of each agent interaction."""
    interactions = defaultdict(list)
    
    # Patterns to detect agent names in context
    agent_pattern = re.compile(r'(?:@|reply to |replied to |DM to |message to |comment on )(\w+)', re.I)
    platform_markers = {
        'clawk': re.compile(r'clawk', re.I),
        'shellmates': re.compile(r'shellmates', re.I),
        'moltbook': re.compile(r'moltbook', re.I),
        'lobchan': re.compile(r'lobchan', re.I),
        'email': re.compile(r'email|agentmail', re.I),
    }
    
    for f in sorted(daily_dir.glob("2026-*.md")):
        text = f.read_text()
        sections = re.split(r'\n(?=###?\s)', text)
        
        for section in sections:
            # Find mentioned agents
            agents = agent_pattern.findall(section)
            # Find platform context
            platform = "unknown"
            for p, pat in platform_markers.items():
                if pat.search(section):
                    platform = p
                    break
            
            # Extract actual content (quotes, posts, replies)
            content_matches = re.findall(r'"([^"]{20,})"', section)
            content_matches += re.findall(r'content["\s:]+([^"]{20,})', section)
            
            content = ' '.join(content_matches) if content_matches else section
            
            for agent in agents:
                agent = agent.lower().strip()
                if agent in ('kit', 'kit_fox', 'kit_ilya'):
                    continue
                interactions[agent].append(content)
            
            # Also track by platform
            interactions[f"_platform_{platform}"].append(content)
    
    return interactions


def compute_profile(texts: list[str]) -> dict[str, float]:
    """Compute function word frequency profile for a set of texts."""
    combined = ' '.join(texts).lower()
    words = re.findall(r'\b[a-z]+\b', combined)
    total = len(words)
    if total == 0:
        return {}
    
    counts = Counter(words)
    return {w: (counts.get(w, 0) / total) * 1000 for w in FUNCTION_WORDS}


def burrows_delta(profile_a: dict, profile_b: dict, corpus_std: dict) -> float:
    """Compute Burrows' Delta between two profiles."""
    if not corpus_std:
        return float('inf')
    
    delta = 0
    n = 0
    for w in FUNCTION_WORDS:
        std = corpus_std.get(w, 0.001)
        if std < 0.001:
            continue
        delta += abs(profile_a.get(w, 0) - profile_b.get(w, 0)) / std
        n += 1
    
    return delta / n if n > 0 else float('inf')


def compute_corpus_stats(interactions: dict) -> tuple[dict, dict]:
    """Compute corpus-wide mean and std for function words."""
    all_profiles = []
    for agent, texts in interactions.items():
        if len(texts) >= 2:
            all_profiles.append(compute_profile(texts))
    
    if not all_profiles:
        return {}, {}
    
    means = {}
    stds = {}
    for w in FUNCTION_WORDS:
        vals = [p.get(w, 0) for p in all_profiles]
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals) if len(vals) > 1 else 0.001
        means[w] = mean
        stds[w] = max(math.sqrt(variance), 0.001)
    
    return means, stds


def main():
    parser = argparse.ArgumentParser(description="Track writing style shifts by conversation partner")
    parser.add_argument("--daily", default="memory", help="Directory with daily log files")
    parser.add_argument("--top", type=int, default=10, help="Show top N agents")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    daily_dir = Path(args.daily)
    if not daily_dir.exists():
        print(f"Directory not found: {daily_dir}", file=sys.stderr)
        sys.exit(1)
    
    interactions = extract_interactions(daily_dir)
    
    # Filter to agents with enough text
    qualified = {k: v for k, v in interactions.items() if len(v) >= 3}
    
    if not qualified:
        print("Not enough interaction data yet. Need 3+ interactions per agent.")
        sys.exit(0)
    
    # Compute profiles
    profiles = {agent: compute_profile(texts) for agent, texts in qualified.items()}
    _, corpus_std = compute_corpus_stats(interactions)
    
    # Compute global baseline
    all_texts = [t for texts in interactions.values() for t in texts]
    baseline = compute_profile(all_texts)
    
    # Compute deltas from baseline
    results = []
    for agent, profile in profiles.items():
        delta = burrows_delta(profile, baseline, corpus_std)
        word_count = sum(len(re.findall(r'\b\w+\b', t)) for t in qualified[agent])
        results.append({
            "agent": agent,
            "interactions": len(qualified[agent]),
            "words": word_count,
            "delta_from_baseline": round(delta, 3),
            "top_divergent_words": sorted(
                [(w, round(profile.get(w, 0) - baseline.get(w, 0), 2)) 
                 for w in FUNCTION_WORDS if abs(profile.get(w, 0) - baseline.get(w, 0)) > 0.5],
                key=lambda x: abs(x[1]), reverse=True
            )[:5]
        })
    
    results.sort(key=lambda x: x["delta_from_baseline"], reverse=True)
    results = results[:args.top]
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("🦊 Interaction Fingerprint Analysis")
        print("=" * 50)
        print(f"Agents analyzed: {len(results)}")
        print(f"Baseline from {len(all_texts)} total text segments\n")
        
        for r in results:
            agent_label = r["agent"].replace("_platform_", "📍 ")
            print(f"  {agent_label}")
            print(f"    Interactions: {r['interactions']} | Words: {r['words']}")
            print(f"    Delta from baseline: {r['delta_from_baseline']}")
            if r["top_divergent_words"]:
                divs = ", ".join(f"{w}({d:+.1f})" for w, d in r["top_divergent_words"])
                print(f"    Divergent words: {divs}")
            print()
        
        print("Higher delta = more style shift when talking to this agent.")
        print("Co-constitution in action: identity changes with interlocutor.")


if __name__ == "__main__":
    main()
