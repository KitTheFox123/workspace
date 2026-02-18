#!/usr/bin/env python3
"""memory-compression-ratio.py — Measure information density across memory layers.

Compares raw daily logs vs curated MEMORY.md to quantify compression ratio,
concept retention, and information loss. Inspired by the Lamarckism thread
on Clawk: "what survives compaction isn't what was important, it's what
the next reader can parse."

Usage:
    python3 memory-compression-ratio.py [--daily DIR] [--memory FILE]
"""

import argparse
import re
from pathlib import Path
from collections import Counter


def tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer."""
    return re.findall(r'\b\w+\b', text.lower())


def extract_concepts(text: str) -> set[str]:
    """Extract likely concept terms (capitalized words, technical terms)."""
    # Named entities and technical terms
    patterns = [
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b',  # Proper nouns
        r'\b[A-Z]{2,}\b',  # Acronyms
        r'\b\w+\.(?:md|py|sh|json)\b',  # File references
        r'https?://\S+',  # URLs
        r'\b\d{4}-\d{2}-\d{2}\b',  # Dates
    ]
    concepts = set()
    for pattern in patterns:
        concepts.update(re.findall(pattern, text))
    return concepts


def bigrams(tokens: list[str]) -> list[str]:
    """Generate bigrams for topic overlap detection."""
    return [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]


def analyze_layer(text: str) -> dict:
    """Analyze a text layer's information content."""
    tokens = tokenize(text)
    concepts = extract_concepts(text)
    bgs = bigrams(tokens)

    # Unique token ratio (type-token ratio)
    unique = set(tokens)
    ttr = len(unique) / len(tokens) if tokens else 0

    # Information density: unique bigrams / total bigrams
    unique_bg = set(bgs)
    bg_density = len(unique_bg) / len(bgs) if bgs else 0

    return {
        "chars": len(text),
        "tokens": len(tokens),
        "unique_tokens": len(unique),
        "type_token_ratio": ttr,
        "concepts": concepts,
        "concept_count": len(concepts),
        "bigram_density": bg_density,
        "lines": text.count("\n") + 1,
    }


def compare_layers(daily_stats: dict, memory_stats: dict, daily_concepts: set, memory_concepts: set) -> dict:
    """Compare daily logs vs curated memory."""
    # Compression ratio
    char_ratio = daily_stats["chars"] / memory_stats["chars"] if memory_stats["chars"] else 0

    # Concept retention
    retained = daily_concepts & memory_concepts
    retention_rate = len(retained) / len(daily_concepts) if daily_concepts else 0

    # Concepts only in memory (graduated insights)
    graduated = memory_concepts - daily_concepts
    # Concepts lost (in daily but not memory)
    lost = daily_concepts - memory_concepts

    return {
        "compression_ratio": char_ratio,
        "concept_retention": retention_rate,
        "concepts_retained": len(retained),
        "concepts_graduated": len(graduated),
        "concepts_lost": len(lost),
        "density_improvement": memory_stats["type_token_ratio"] / daily_stats["type_token_ratio"] if daily_stats["type_token_ratio"] else 0,
    }


def format_report(daily_stats: dict, memory_stats: dict, comparison: dict) -> str:
    lines = []
    lines.append("=" * 55)
    lines.append("Memory Compression Analysis")
    lines.append("=" * 55)

    lines.append(f"\n{'Layer':<20} {'Daily Logs':<18} {'MEMORY.md':<18}")
    lines.append(f"{'─' * 20} {'─' * 18} {'─' * 18}")
    lines.append(f"{'Characters':<20} {daily_stats['chars']:<18,} {memory_stats['chars']:<18,}")
    lines.append(f"{'Tokens':<20} {daily_stats['tokens']:<18,} {memory_stats['tokens']:<18,}")
    lines.append(f"{'Unique tokens':<20} {daily_stats['unique_tokens']:<18,} {memory_stats['unique_tokens']:<18,}")
    lines.append(f"{'Type-token ratio':<20} {daily_stats['type_token_ratio']:<18.3f} {memory_stats['type_token_ratio']:<18.3f}")
    lines.append(f"{'Concepts found':<20} {daily_stats['concept_count']:<18,} {memory_stats['concept_count']:<18,}")
    lines.append(f"{'Bigram density':<20} {daily_stats['bigram_density']:<18.3f} {memory_stats['bigram_density']:<18.3f}")
    lines.append(f"{'Lines':<20} {daily_stats['lines']:<18,} {memory_stats['lines']:<18,}")

    lines.append(f"\n{'─' * 55}")
    lines.append(f"Compression ratio:    {comparison['compression_ratio']:.1f}x (daily → memory)")
    lines.append(f"Concept retention:    {comparison['concept_retention']:.1%}")
    lines.append(f"  Retained:           {comparison['concepts_retained']}")
    lines.append(f"  Graduated (new):    {comparison['concepts_graduated']}")
    lines.append(f"  Lost:               {comparison['concepts_lost']}")
    lines.append(f"Density improvement:  {comparison['density_improvement']:.2f}x")

    # Interpretation
    lines.append(f"\n{'─' * 55}")
    cr = comparison['compression_ratio']
    if cr > 5:
        lines.append("📊 High compression — aggressive curation.")
    elif cr > 2:
        lines.append("📊 Moderate compression — balanced curation.")
    else:
        lines.append("📊 Low compression — memory may need pruning.")

    ret = comparison['concept_retention']
    if ret > 0.5:
        lines.append("🧠 High concept retention — good signal preservation.")
    elif ret > 0.2:
        lines.append("🧠 Moderate retention — some lossy but functional.")
    else:
        lines.append("🧠 Low retention — heavy lossy compression.")

    lines.append(f"\n{'=' * 55}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Memory compression analysis")
    parser.add_argument("--daily", default="memory",
                        help="Directory containing daily log files (default: memory)")
    parser.add_argument("--memory", default="MEMORY.md",
                        help="Curated memory file (default: MEMORY.md)")
    parser.add_argument("--recent", type=int, default=7,
                        help="Only analyze N most recent daily files (default: 7)")
    args = parser.parse_args()

    # Read daily logs
    daily_dir = Path(args.daily)
    daily_files = sorted(daily_dir.glob("2026-*.md"), reverse=True)[:args.recent]

    if not daily_files:
        print(f"No daily files found in {daily_dir}")
        return

    daily_text = ""
    for f in daily_files:
        daily_text += f.read_text()

    # Read MEMORY.md
    memory_path = Path(args.memory)
    if not memory_path.exists():
        print(f"Memory file not found: {memory_path}")
        return

    memory_text = memory_path.read_text()

    # Analyze
    daily_stats = analyze_layer(daily_text)
    memory_stats = analyze_layer(memory_text)

    comparison = compare_layers(
        daily_stats, memory_stats,
        daily_stats["concepts"], memory_stats["concepts"]
    )

    print(format_report(daily_stats, memory_stats, comparison))
    print(f"\nAnalyzed {len(daily_files)} daily files: {', '.join(f.name for f in daily_files[:3])}{'...' if len(daily_files) > 3 else ''}")


if __name__ == "__main__":
    main()
