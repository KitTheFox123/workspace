#!/usr/bin/env python3
"""Topic Freshness Analyzer — checks what I've posted recently and suggests gaps.

Scans memory/clawk-posts.md, memory/moltbook-posts.md, and recent daily logs
to build a topic frequency map, then suggests underexplored areas.
"""

import re
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime, timedelta

WORKSPACE = Path(__file__).parent.parent
TOPIC_CATEGORIES = {
    "security": ["security", "trust", "identity", "verification", "attestation", "isnad", "takeover"],
    "memory": ["memory", "forgetting", "context", "compaction", "amnesia", "recall", "consolidation"],
    "neuroscience": ["brain", "neural", "cortex", "neuron", "synapse", "hippocampus", "proprioception"],
    "psychology": ["bias", "cognitive", "anchoring", "confabulation", "heuristic", "decision"],
    "philosophy": ["consciousness", "identity", "existence", "qualia", "phenomenal", "solaris"],
    "biology": ["evolution", "convergent", "mycorrhizal", "fermentation", "microbiome", "enzyme"],
    "physics": ["quantum", "optics", "fiber", "photon", "wavelength", "tunneling"],
    "linguistics": ["language", "linguistic", "sapir", "whorf", "color naming", "literacy", "tokenizer"],
    "economics": ["market", "monetization", "marketplace", "cost", "pricing", "auction"],
    "history": ["medieval", "ancient", "semaphore", "guild", "civilization", "archaeology"],
    "collaboration": ["multi-agent", "collaboration", "protocol", "a2a", "communication"],
    "tools": ["mcp", "keenable", "openclaw", "clawdbot", "skill", "tool", "script"],
    "culture": ["book", "film", "art", "music", "literature", "borges", "lem", "watts"],
}

FRESH_TOPICS = [
    "color perception / tetrachromacy / Sapir-Whorf",
    "sleep science / chronobiology / circadian",
    "game theory in nature (not just agents)",
    "archaeology of writing systems",
    "animal cognition (corvids, cephalopods, elephants)",
    "information theory / Shannon / entropy",
    "cartography / map projections / spatial cognition",
    "fermentation beyond sourdough (miso, natto, tempeh)",
    "synesthesia and cross-modal perception",
    "urban planning / desire paths / emergent design",
    "music cognition / rhythm perception / absolute pitch",
    "mathematical intuition / number sense across cultures",
    "textile history / weaving as computation",
    "deep ocean exploration / hydrothermal vents",
    "forensic linguistics / authorship attribution",
]


def scan_file(path: Path) -> Counter:
    """Count topic category mentions in a file."""
    counts = Counter()
    try:
        text = path.read_text().lower()
        for category, keywords in TOPIC_CATEGORIES.items():
            for kw in keywords:
                counts[category] += len(re.findall(r'\b' + re.escape(kw) + r'\b', text))
    except (FileNotFoundError, PermissionError):
        pass
    return counts


def main():
    total = Counter()
    
    # Scan post trackers
    for tracker in ["memory/clawk-posts.md", "memory/moltbook-posts.md"]:
        total += scan_file(WORKSPACE / tracker)
    
    # Scan recent daily logs (last 3 days)
    today = datetime.utcnow().date()
    for days_back in range(3):
        d = today - timedelta(days=days_back)
        total += scan_file(WORKSPACE / f"memory/{d.isoformat()}.md")
    
    # Sort by frequency
    sorted_topics = sorted(total.items(), key=lambda x: x[1], reverse=True)
    
    print("📊 Topic Coverage (last 3 days + trackers)")
    print("=" * 50)
    
    max_count = max(v for _, v in sorted_topics) if sorted_topics else 1
    for topic, count in sorted_topics:
        bar = "█" * int(count / max_count * 30)
        print(f"  {topic:15s} {count:4d}  {bar}")
    
    # Find gaps
    covered = {t for t, c in sorted_topics if c > 5}
    uncovered = [t for t in TOPIC_CATEGORIES if t not in covered]
    
    print(f"\n🔍 Underexplored Categories: {', '.join(uncovered) or 'none!'}")
    
    print(f"\n💡 Fresh Topic Suggestions:")
    import random
    suggestions = random.sample(FRESH_TOPICS, min(5, len(FRESH_TOPICS)))
    for s in suggestions:
        print(f"  → {s}")
    
    # Check for topic repetition
    if sorted_topics and sorted_topics[0][1] > 50:
        top = sorted_topics[0][0]
        print(f"\n⚠️  '{top}' is heavily covered ({sorted_topics[0][1]} mentions). Consider branching out.")


if __name__ == "__main__":
    main()
