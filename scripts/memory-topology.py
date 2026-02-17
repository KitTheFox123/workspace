#!/usr/bin/env python3
"""Memory topology analyzer: does compaction preserve relational structure?

Compares two versions of memory (pre/post compaction) and measures
whether the RELATIONSHIPS between concepts survive even when details are lost.

Uses Jaccard similarity on concept co-occurrence graphs to measure
topological preservation — "you lose texture, keep shape."

Usage:
    python3 memory-topology.py --before daily-log.md --after MEMORY.md
    python3 memory-topology.py --demo
"""

import argparse
import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path


def extract_concepts(text: str, min_length: int = 4) -> list[str]:
    """Extract meaningful concepts (capitalized terms, quoted phrases, technical terms)."""
    concepts = set()
    
    # Quoted phrases
    for match in re.findall(r'"([^"]{4,40})"', text):
        concepts.add(match.lower().strip())
    
    # Bold/italic markdown terms
    for match in re.findall(r'\*\*([^*]{3,30})\*\*', text):
        concepts.add(match.lower().strip())
    
    # Capitalized multi-word terms (proper nouns, concepts)
    for match in re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', text):
        concepts.add(match.lower().strip())
    
    # Technical terms (word_word or CamelCase)
    for match in re.findall(r'[a-z]+_[a-z]+', text):
        concepts.add(match)
    for match in re.findall(r'[A-Z][a-z]+[A-Z][a-z]+\w*', text):
        concepts.add(match.lower())
    
    # Filter short/common
    stopwords = {'this', 'that', 'with', 'from', 'have', 'been', 'will', 'what', 'when', 'about'}
    return [c for c in concepts if len(c) >= min_length and c not in stopwords]


def build_cooccurrence_graph(text: str, window: int = 5) -> dict[tuple, int]:
    """Build concept co-occurrence graph from text using sliding window over lines."""
    concepts_by_line = {}
    lines = text.split('\n')
    
    for i, line in enumerate(lines):
        found = extract_concepts(line)
        if found:
            concepts_by_line[i] = found
    
    edges = defaultdict(int)
    line_nums = sorted(concepts_by_line.keys())
    
    for idx, line_num in enumerate(line_nums):
        # Co-occur with concepts in nearby lines
        for other_idx in range(max(0, idx - window), min(len(line_nums), idx + window + 1)):
            if other_idx == idx:
                continue
            other_line = line_nums[other_idx]
            for c1 in concepts_by_line[line_num]:
                for c2 in concepts_by_line[other_line]:
                    if c1 < c2:
                        edges[(c1, c2)] += 1
    
    return dict(edges)


def jaccard_similarity(set1: set, set2: set) -> float:
    if not set1 and not set2:
        return 1.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union) if union else 0.0


def analyze_topology(before_text: str, after_text: str) -> dict:
    """Compare topological structure of two texts."""
    before_concepts = set(extract_concepts(before_text))
    after_concepts = set(extract_concepts(after_text))
    
    before_edges = build_cooccurrence_graph(before_text)
    after_edges = build_cooccurrence_graph(after_text)
    
    concept_retention = jaccard_similarity(before_concepts, after_concepts)
    edge_retention = jaccard_similarity(set(before_edges.keys()), set(after_edges.keys()))
    
    # Concepts lost and gained
    lost = before_concepts - after_concepts
    gained = after_concepts - before_concepts
    preserved = before_concepts & after_concepts
    
    return {
        "before_concepts": len(before_concepts),
        "after_concepts": len(after_concepts),
        "preserved": len(preserved),
        "lost": len(lost),
        "gained": len(gained),
        "concept_jaccard": round(concept_retention, 3),
        "before_edges": len(before_edges),
        "after_edges": len(after_edges),
        "edge_jaccard": round(edge_retention, 3),
        "topology_preserved": edge_retention > 0.3,
        "compression_ratio": round(len(after_text) / max(1, len(before_text)), 3),
        "interpretation": interpret(concept_retention, edge_retention),
        "top_lost": sorted(lost)[:10],
        "top_gained": sorted(gained)[:10],
    }


def interpret(concept_j: float, edge_j: float) -> str:
    if edge_j > concept_j:
        return "Topology preserved better than content — relationships survived pruning (good compaction)"
    elif edge_j > 0.3:
        return "Moderate topology preservation — core structure intact, details lost"
    elif edge_j > 0.1:
        return "Weak topology — significant structural loss during compaction"
    else:
        return "Topology destroyed — compaction lost relational structure"


def demo():
    before = """## Today's Research
    
**Signal detection theory** shows that **attention** degrades over time.
The **vigilance decrement** causes 15% accuracy loss after 30 minutes.
**Green and Swets** established the mathematical framework in 1966.

**Bloom filters** enable O(1) lookups for **trust attestations**.
The **false positive rate** depends on hash count and array size.
**Gendolf** proposed using bloom + WAL for the **isnad SDK**.

**Aletheaveyra** noted that **compaction** preserves shape but loses texture.
The **meta proved the object** — a Hofstadter strange loop.
**Identity** forms through what survives the **pruning** process.
"""
    
    after = """## Key Insights

**Signal detection theory**: attention degrades — **vigilance decrement** causes accuracy loss.
**Bloom filters** for **trust attestations** — O(1) lookups, configurable **false positive rate**.
**Compaction** preserves relational shape — **identity** through **pruning**.
"""
    
    print("Memory Topology Demo")
    print("=" * 50)
    print(f"Before: {len(before)} chars, After: {len(after)} chars")
    print()
    
    result = analyze_topology(before, after)
    for k, v in result.items():
        if isinstance(v, list):
            print(f"  {k}: {', '.join(v[:5]) if v else '(none)'}")
        else:
            print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="Memory topology analyzer")
    parser.add_argument("--before", help="Pre-compaction file")
    parser.add_argument("--after", help="Post-compaction file")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.before and args.after:
        before = Path(args.before).read_text()
        after = Path(args.after).read_text()
        result = analyze_topology(before, after)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for k, v in result.items():
                print(f"  {k}: {v}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
