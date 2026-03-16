#!/usr/bin/env python3
"""
idea-dedup-audit.py — Semantic deduplication audit for a corpus of scripts/posts.

Inspired by lainiaoxia007's self-audit: 46 posts, 11 distinct ideas.
Processing fluency (Alter & Oppenheimer 2009) makes rewrites feel like progress.

This tool:
1. Extracts "core idea" from each script's docstring
2. Groups by conceptual similarity (keyword overlap + shared references)
3. Reports: how many DISTINCT ideas vs variations?

Applied to Kit's ~80 scripts in scripts/.
"""

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class ScriptIdea:
    filename: str
    docstring: str
    concepts: set = field(default_factory=set)
    references: set = field(default_factory=set)  # Academic citations
    cluster: int = -1


# Core concept keywords — the real primitives
CONCEPT_PATTERNS = {
    "ebbinghaus_decay": r"ebbinghaus|decay.*R=|R=e\^|stability.*constant|forgetting.*curve",
    "merkle_proof": r"merkle|inclusion.*proof|append.only|hash.*tree|tamper.*proof",
    "diversity_scoring": r"diversity.*scor|operator.*independence|monoculture|sybil|correlated.*voter",
    "leitner_boxes": r"leitner|spaced.*repetition|box.*\d|trust.*tier|graduated.*trust",
    "watson_morgan": r"watson.*morgan|testimony.*observation|epistemic.*weight|2x.*weight",
    "blackstone_ratio": r"blackstone|false.*positive.*negative|asymmetric.*cost|punishment.*threshold",
    "ct_enforcement": r"certificate.*transparency|CT.*enforce|chrome.*ct|SCT|gap.*report",
    "enforcement_graduation": r"graduat|REPORT.*WARN.*STRICT|phase.*enforcement|chrome.*not.*secure",
    "scar_reference": r"scar.*reference|post.*slash|rehabilitation|desistance",
    "dormant_state": r"dormant|silent.*gone|declared.*absence|inactivity.*leak",
    "commitment_device": r"commitment.*device|schelling|credible.*commit|focal.*point",
    "capability_security": r"capability.*security|confused.*deputy|ambient.*authority|CORS.*MCP",
    "gap_events": r"gap.*event|streak.*reset|antifragil|battle.*tested",
    "counterfactual_log": r"counterfactual|inaction.*log|null.*entry|liveness.*proof",
    "payer_classification": r"payer.*type|PDA.*EOA|nested.*contract|re.*derive",
}

REFERENCE_PATTERN = re.compile(
    r"(?:(?:[A-Z][a-z]+)\s+(?:(?:et al\.?\s+)?(?:19|20)\d{2}|(?:&|and)\s+[A-Z][a-z]+\s+(?:19|20)\d{2}))"
    r"|(?:RFC\s+\d{4})"
    r"|(?:EIP-\d+)"
)


def extract_docstring(filepath: str) -> str:
    """Extract first docstring from a Python file."""
    try:
        with open(filepath) as f:
            content = f.read()
        # Match triple-quoted docstring
        match = re.search(r'"""(.*?)"""', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r"'''(.*?)'''", content, re.DOTALL)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return ""


def extract_concepts(text: str) -> set[str]:
    """Identify which core concepts appear in text."""
    concepts = set()
    text_lower = text.lower()
    for concept, pattern in CONCEPT_PATTERNS.items():
        if re.search(pattern, text_lower):
            concepts.add(concept)
    return concepts


def extract_references(text: str) -> set[str]:
    """Extract academic references from text."""
    return set(REFERENCE_PATTERN.findall(text))


def cluster_by_concepts(scripts: list[ScriptIdea]) -> dict[str, list[ScriptIdea]]:
    """Group scripts by their primary concept."""
    clusters: dict[str, list[ScriptIdea]] = defaultdict(list)
    unclustered = []
    
    for s in scripts:
        if s.concepts:
            # Primary concept = first matched
            primary = sorted(s.concepts)[0]
            clusters[primary].append(s)
        else:
            unclustered.append(s)
    
    if unclustered:
        clusters["uncategorized"] = unclustered
    
    return clusters


def jaccard_similarity(a: set, b: set) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def audit_directory(scripts_dir: str) -> None:
    """Run deduplication audit on a directory of scripts."""
    scripts = []
    
    for fname in sorted(os.listdir(scripts_dir)):
        if not fname.endswith(".py"):
            continue
        filepath = os.path.join(scripts_dir, fname)
        docstring = extract_docstring(filepath)
        
        # Also read full file for concept extraction
        try:
            with open(filepath) as f:
                full_text = f.read()
        except Exception:
            full_text = docstring
        
        concepts = extract_concepts(full_text)
        references = extract_references(full_text)
        
        scripts.append(ScriptIdea(
            filename=fname,
            docstring=docstring[:200],
            concepts=concepts,
            references=references,
        ))
    
    # Cluster
    clusters = cluster_by_concepts(scripts)
    
    # Report
    total = len(scripts)
    distinct = len(clusters)
    
    print(f"{'='*60}")
    print(f"IDEA DEDUPLICATION AUDIT")
    print(f"{'='*60}")
    print(f"\nTotal scripts: {total}")
    print(f"Distinct concept clusters: {distinct}")
    print(f"Novelty ratio: {distinct}/{total} = {distinct/max(total,1):.0%}")
    print(f"Repackaging rate: {(total-distinct)/max(total,1):.0%}")
    
    # Show clusters
    print(f"\n{'='*60}")
    print(f"CONCEPT CLUSTERS")
    print(f"{'='*60}")
    
    for concept, members in sorted(clusters.items(), key=lambda x: -len(x[1])):
        print(f"\n📦 {concept} ({len(members)} scripts)")
        for s in members:
            refs = f" [{len(s.references)} refs]" if s.references else ""
            other = s.concepts - {concept}
            cross = f" +{','.join(sorted(other))}" if other else ""
            print(f"    {s.filename}{refs}{cross}")
    
    # Find high-similarity pairs
    print(f"\n{'='*60}")
    print(f"HIGH SIMILARITY PAIRS (Jaccard > 0.5)")
    print(f"{'='*60}")
    
    pairs = []
    for i, a in enumerate(scripts):
        for b in scripts[i+1:]:
            sim = jaccard_similarity(a.concepts, b.concepts)
            if sim > 0.5 and a.concepts:  # Skip empty
                pairs.append((a.filename, b.filename, sim, a.concepts & b.concepts))
    
    pairs.sort(key=lambda x: -x[2])
    for a, b, sim, shared in pairs[:15]:
        print(f"  {sim:.0%}  {a} ↔ {b}")
        print(f"       shared: {', '.join(sorted(shared))}")
    
    if not pairs:
        print("  (none found)")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"VERDICT")
    print(f"{'='*60}")
    ratio = distinct / max(total, 1)
    if ratio > 0.5:
        print(f"  ✅ {ratio:.0%} novelty — reasonable diversity")
    elif ratio > 0.3:
        print(f"  ⚠️ {ratio:.0%} novelty — some consolidation needed")
    else:
        print(f"  ❌ {ratio:.0%} novelty — significant repackaging")
    
    print(f"\n  Processing fluency warning: rewrites FEEL productive.")
    print(f"  Alter & Oppenheimer 2009: fluency ≠ value.")
    print(f"  Rozenblit & Keil 2002: you understand less than you think.")


if __name__ == "__main__":
    scripts_dir = os.path.join(os.path.dirname(__file__))
    audit_directory(scripts_dir)
