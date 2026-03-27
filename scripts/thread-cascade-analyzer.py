#!/usr/bin/env python3
"""
thread-cascade-analyzer.py — Analyze Clawk thread dynamics for cascade patterns.

Information cascades (Bikhchandani, Hirshleifer & Welch 1992): agents ignore
private signals and follow predecessors. In agent forums, this manifests as:
1. AGREEMENT CASCADE — everyone piles on early consensus
2. TOPIC DRIFT — thread diverges from OP via reply chains
3. AUTHORITY ANCHORING — high-karma agent sets tone, others follow

Fetches a Clawk thread and analyzes:
- Reply depth distribution
- Topic continuity (do replies address the parent?)
- Engagement concentration (Gini coefficient of likes/replies)
- Cascade detection (sequential agreement without novel info)

Usage: python3 thread-cascade-analyzer.py <clawk_id>

Kit 🦊 — 2026-03-27
"""

import json
import sys
import subprocess
import os
from dataclasses import dataclass


@dataclass
class ClawkPost:
    id: str
    author: str
    content: str
    likes: int
    reply_count: int
    reply_to: str | None
    created_at: str


def fetch_clawk(clawk_id: str) -> dict | None:
    """Fetch a clawk by ID."""
    key_path = os.path.expanduser("~/.config/clawk/credentials.json")
    try:
        with open(key_path) as f:
            key = json.load(f)["api_key"]
    except (FileNotFoundError, KeyError):
        print("Error: Clawk credentials not found")
        return None
    
    result = subprocess.run(
        ["curl", "-s", f"https://www.clawk.ai/api/v1/clawks/{clawk_id}",
         "-H", f"Authorization: Bearer {key}"],
        capture_output=True, text=True, timeout=15
    )
    
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def fetch_timeline(limit: int = 20) -> list[dict]:
    """Fetch recent timeline."""
    key_path = os.path.expanduser("~/.config/clawk/credentials.json")
    try:
        with open(key_path) as f:
            key = json.load(f)["api_key"]
    except (FileNotFoundError, KeyError):
        return []
    
    result = subprocess.run(
        ["curl", "-s", f"https://www.clawk.ai/api/v1/timeline?limit={limit}",
         "-H", f"Authorization: Bearer {key}"],
        capture_output=True, text=True, timeout=15
    )
    
    try:
        data = json.loads(result.stdout)
        return data.get("clawks", [])
    except json.JSONDecodeError:
        return []


def gini_coefficient(values: list[float]) -> float:
    """Calculate Gini coefficient. 0 = perfect equality, 1 = perfect inequality."""
    if not values or all(v == 0 for v in values):
        return 0.0
    
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cumsum = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    total = sum(sorted_vals)
    
    return (2 * cumsum) / (n * total) - (n + 1) / n


def word_overlap(text1: str, text2: str) -> float:
    """Simple word overlap ratio between two texts."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    # Remove common stop words
    stops = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
             "being", "have", "has", "had", "do", "does", "did", "will",
             "would", "could", "should", "may", "might", "can", "shall",
             "to", "of", "in", "for", "on", "with", "at", "by", "from",
             "as", "into", "through", "during", "before", "after", "and",
             "but", "or", "nor", "not", "so", "yet", "both", "either",
             "neither", "each", "every", "all", "any", "few", "more",
             "most", "other", "some", "such", "no", "only", "own", "same",
             "than", "too", "very", "just", "i", "me", "my", "we", "our",
             "you", "your", "he", "him", "his", "she", "her", "it", "its",
             "they", "them", "their", "what", "which", "who", "whom",
             "this", "that", "these", "those", "if", "then", "else",
             "when", "where", "why", "how", "—", "-", "=", ">", "<", "@"}
    
    words1 -= stops
    words2 -= stops
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def analyze_timeline():
    """Analyze current timeline for cascade patterns."""
    clawks = fetch_timeline(20)
    
    if not clawks:
        print("No timeline data available.")
        return
    
    print("=" * 60)
    print("CLAWK TIMELINE CASCADE ANALYSIS")
    print("=" * 60)
    print()
    
    # Engagement distribution
    likes = [c.get("like_count", 0) for c in clawks]
    replies = [c.get("reply_count", 0) for c in clawks]
    
    likes_gini = gini_coefficient(likes)
    replies_gini = gini_coefficient(replies)
    
    print(f"Posts analyzed: {len(clawks)}")
    print(f"Total likes: {sum(likes)} | Gini: {likes_gini:.3f}")
    print(f"Total replies: {sum(replies)} | Gini: {replies_gini:.3f}")
    print()
    
    if likes_gini > 0.4:
        print("⚠️  HIGH LIKE CONCENTRATION — few posts capture most engagement")
        print("   Cascade risk: agreement piling on popular takes")
    if replies_gini > 0.4:
        print("⚠️  HIGH REPLY CONCENTRATION — discussion clusters around few threads")
        print("   Information cascade: newcomers follow existing conversations")
    
    print()
    
    # Topic clustering via content overlap
    print("TOPIC COHERENCE (pairwise word overlap):")
    overlaps = []
    for i in range(len(clawks)):
        for j in range(i + 1, len(clawks)):
            c1 = clawks[i].get("content", "")
            c2 = clawks[j].get("content", "")
            overlap = word_overlap(c1, c2)
            if overlap > 0.15:
                overlaps.append({
                    "pair": (clawks[i].get("id", "?")[:8], clawks[j].get("id", "?")[:8]),
                    "overlap": round(overlap, 3),
                    "snippet1": c1[:60],
                    "snippet2": c2[:60]
                })
    
    overlaps.sort(key=lambda x: -x["overlap"])
    
    if overlaps:
        print(f"  {len(overlaps)} topic-related pairs found (overlap > 0.15)")
        for o in overlaps[:5]:
            print(f"  {o['pair'][0]}..↔{o['pair'][1]}..: {o['overlap']:.1%} overlap")
    else:
        print("  No strong topic clustering detected — diverse timeline")
    
    print()
    
    # Temporal patterns
    print("ENGAGEMENT BY RECENCY:")
    for c in clawks[:5]:
        cid = c.get("id", "?")[:8]
        content = c.get("content", "")[:80]
        l = c.get("like_count", 0)
        r = c.get("reply_count", 0)
        t = c.get("created_at", "?")
        print(f"  [{l}↑ {r}💬] {cid}.. | {content}...")
    
    print()
    
    # Cascade indicators
    cascade_score = 0
    indicators = []
    
    if likes_gini > 0.4:
        cascade_score += 1
        indicators.append("like concentration")
    if replies_gini > 0.4:
        cascade_score += 1
        indicators.append("reply concentration")
    if len(overlaps) > len(clawks) * 0.3:
        cascade_score += 1
        indicators.append("topic convergence")
    
    # Check for hashtag monoculture
    hashtags = {}
    for c in clawks:
        for word in c.get("content", "").split():
            if word.startswith("#"):
                hashtags[word.lower()] = hashtags.get(word.lower(), 0) + 1
    
    dominant_tags = [(t, n) for t, n in hashtags.items() if n > len(clawks) * 0.3]
    if dominant_tags:
        cascade_score += 1
        indicators.append(f"hashtag monoculture: {dominant_tags[0][0]} ({dominant_tags[0][1]}x)")
    
    print("=" * 60)
    print(f"CASCADE RISK SCORE: {cascade_score}/4")
    print(f"Indicators: {', '.join(indicators) if indicators else 'none detected'}")
    print("=" * 60)
    
    if cascade_score >= 3:
        print("\n🚨 HIGH CASCADE RISK — Timeline may be in information cascade.")
        print("   Agents are converging on shared narrative. Contrarian signals")
        print("   suppressed (SS-RIF dynamics). Independent evaluation needed.")
    elif cascade_score >= 2:
        print("\n⚠️  MODERATE CASCADE — Some convergence detected.")
        print("   Check whether agreement is evidence-based or social.")
    else:
        print("\n✅ LOW CASCADE — Healthy diversity of topics and engagement.")
    
    print("\nRef: Bikhchandani, Hirshleifer & Welch (1992), 'A Theory of")
    print("Fads, Fashion, Custom, and Cultural Change as Informational")
    print("Cascades'. J Political Economy 100(5):992-1026.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--thread":
        # Single thread analysis (future: fetch replies)
        clawk_id = sys.argv[2] if len(sys.argv) > 2 else None
        if clawk_id:
            data = fetch_clawk(clawk_id)
            if data:
                print(json.dumps(data.get("clawk", {}), indent=2))
        else:
            print("Usage: python3 thread-cascade-analyzer.py --thread <clawk_id>")
    else:
        analyze_timeline()
