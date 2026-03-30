#!/usr/bin/env python3
"""
element-interactivity-scorer.py — Sweller's Element Interactivity for attestation complexity.

Based on Sweller (2023, Ed Psych Review 35:95): Element interactivity determines cognitive
load. High interactivity = elements must be processed simultaneously. Low = independent.

Agent translation: attestation tasks vary in element interactivity. A simple "is this agent
active?" check = low interactivity (one signal). A full trust assessment requiring behavioral
history + graph position + temporal patterns + content analysis = high interactivity (all
elements must be considered together).

Key CLT insight: expertise REVERSES effects. Scaffolding that helps novices HARMS experts
(Kalyuga 2007 expertise reversal). Verbose attestation prompts help new attestors but
interfere with experienced ones.

References:
- Sweller (2023, Ed Psych Review 35:95) — CLT replication crises → theory expansion
- Sweller (2010) — Element interactivity and intrinsic/extraneous cognitive load
- Kalyuga (2007) — Expertise reversal effect
- Chen, Paas & Sweller (2023) — Element interactivity measurement

Kit 🦊 | 2026-03-30
"""

import json
from dataclasses import dataclass
from typing import List


@dataclass
class AttestationElement:
    """A single element in an attestation task."""
    name: str
    domain: str  # behavioral, graph, temporal, content, identity
    complexity: float  # 0-1 how complex this element is alone
    dependencies: List[str]  # names of elements this MUST be processed with


def compute_element_interactivity(elements: List[AttestationElement]) -> dict:
    """
    Compute element interactivity for an attestation task.
    
    High interactivity = many elements with cross-dependencies.
    Low interactivity = elements processable independently.
    """
    n = len(elements)
    if n == 0:
        return {"interactivity": 0, "intrinsic_load": 0, "category": "TRIVIAL"}
    
    # Count dependency edges
    dep_count = sum(len(e.dependencies) for e in elements)
    max_deps = n * (n - 1)  # fully connected
    
    # Interactivity ratio
    interactivity = dep_count / max_deps if max_deps > 0 else 0
    
    # Intrinsic load = interactivity * mean complexity * element count
    mean_complexity = sum(e.complexity for e in elements) / n
    intrinsic_load = interactivity * mean_complexity * min(n / 7, 1.0)  # Miller's 7±2
    
    # Find largest connected component (simultaneous processing requirement)
    # Build adjacency
    name_to_idx = {e.name: i for i, e in enumerate(elements)}
    adj = [set() for _ in range(n)]
    for i, e in enumerate(elements):
        for dep in e.dependencies:
            if dep in name_to_idx:
                j = name_to_idx[dep]
                adj[i].add(j)
                adj[j].add(i)
    
    # BFS for components
    visited = [False] * n
    max_component = 0
    for start in range(n):
        if visited[start]:
            continue
        queue = [start]
        visited[start] = True
        size = 0
        while queue:
            node = queue.pop(0)
            size += 1
            for nb in adj[node]:
                if not visited[nb]:
                    visited[nb] = True
                    queue.append(nb)
        max_component = max(max_component, size)
    
    # Working memory demand = largest component that must be held simultaneously
    wm_demand = max_component / 7.0  # fraction of Miller's limit
    
    # Category
    if intrinsic_load < 0.2:
        category = "LOW_INTERACTIVITY"
    elif intrinsic_load < 0.5:
        category = "MODERATE"
    elif intrinsic_load < 0.8:
        category = "HIGH_INTERACTIVITY"
    else:
        category = "COGNITIVE_OVERLOAD"
    
    return {
        "elements": n,
        "dependency_edges": dep_count,
        "interactivity": round(interactivity, 3),
        "intrinsic_load": round(intrinsic_load, 3),
        "max_simultaneous": max_component,
        "wm_demand_fraction": round(wm_demand, 3),
        "category": category,
    }


def expertise_reversal_check(
    intrinsic_load: float,
    attestor_experience: int,  # number of prior attestations
    scaffolding_level: float,  # 0-1 how much guidance provided
) -> dict:
    """
    Kalyuga (2007): scaffolding helps novices, HARMS experts.
    
    Returns whether current scaffolding level is appropriate for attestor expertise.
    """
    # Experience threshold (rough — Sweller suggests ~10 for chunking to kick in)
    expertise = min(attestor_experience / 50, 1.0)  # normalize to 0-1
    
    # Optimal scaffolding decreases with expertise
    optimal_scaffolding = max(0, 1.0 - expertise)
    
    # Mismatch
    scaffolding_gap = scaffolding_level - optimal_scaffolding
    
    if scaffolding_gap > 0.3:
        effect = "EXPERTISE_REVERSAL"
        note = "Too much scaffolding for this attestor's experience. Reducing guidance would improve performance."
    elif scaffolding_gap < -0.3:
        effect = "COGNITIVE_OVERLOAD"
        note = "Insufficient scaffolding for novice attestor. Add structured guidance."
    else:
        effect = "MATCHED"
        note = "Scaffolding appropriate for attestor expertise level."
    
    return {
        "attestor_expertise": round(expertise, 3),
        "optimal_scaffolding": round(optimal_scaffolding, 3),
        "actual_scaffolding": round(scaffolding_level, 3),
        "gap": round(scaffolding_gap, 3),
        "effect": effect,
        "note": note,
    }


def split_attention_check(attestation_format: dict) -> dict:
    """
    Sweller: split-attention between information sources increases extraneous load.
    
    For attestations: showing behavioral data separately from graph data separately
    from temporal data = split attention. Integrated dashboard = reduced load.
    """
    sources = attestation_format.get("information_sources", [])
    integrated = attestation_format.get("physically_integrated", False)
    redundant_sources = attestation_format.get("redundant_sources", [])
    
    n_sources = len(sources)
    n_redundant = len(redundant_sources)
    
    if n_sources <= 1:
        return {"effect": "NONE", "extraneous_load": 0.0, "recommendation": "Single source — no split attention."}
    
    if integrated:
        extraneous = 0.1 * (n_sources - 1)  # minimal residual
        effect = "MITIGATED"
        rec = "Sources integrated. Minimal split-attention."
    else:
        extraneous = 0.2 * (n_sources - 1)  # each unintegrated source adds load
        effect = "SPLIT_ATTENTION"
        rec = f"Integrate {n_sources} sources into unified view. Current format forces mental integration."
    
    # Redundancy check (Chandler & Sweller 1991)
    if n_redundant > 0:
        effect = "REDUNDANCY"
        extraneous += 0.15 * n_redundant
        rec = f"Remove {n_redundant} redundant source(s). Redundancy increases load even when integrated."
    
    return {
        "effect": effect,
        "sources": n_sources,
        "redundant": n_redundant,
        "extraneous_load": round(extraneous, 3),
        "recommendation": rec,
    }


def demo():
    """Demo: compare attestation task complexity across scenarios."""
    print("=" * 60)
    print("ELEMENT INTERACTIVITY SCORER")
    print("Sweller (2023) Cognitive Load Theory for Attestations")
    print("=" * 60)
    
    # Scenario 1: Simple liveness check (low interactivity)
    simple = [
        AttestationElement("heartbeat", "temporal", 0.2, []),
        AttestationElement("last_active", "temporal", 0.1, []),
    ]
    
    # Scenario 2: Behavioral attestation (moderate)
    behavioral = [
        AttestationElement("heartbeat", "temporal", 0.2, ["consistency"]),
        AttestationElement("consistency", "behavioral", 0.4, ["heartbeat"]),
        AttestationElement("content_quality", "content", 0.5, ["consistency"]),
        AttestationElement("graph_position", "graph", 0.3, []),
    ]
    
    # Scenario 3: Full trust assessment (high interactivity)
    full = [
        AttestationElement("heartbeat", "temporal", 0.2, ["consistency", "channel_desync"]),
        AttestationElement("consistency", "behavioral", 0.4, ["heartbeat", "stylometry"]),
        AttestationElement("stylometry", "content", 0.6, ["consistency", "content_quality"]),
        AttestationElement("content_quality", "content", 0.5, ["stylometry", "graph_position"]),
        AttestationElement("graph_position", "graph", 0.5, ["attestation_chain", "content_quality"]),
        AttestationElement("attestation_chain", "identity", 0.7, ["graph_position", "channel_desync"]),
        AttestationElement("channel_desync", "temporal", 0.4, ["heartbeat", "attestation_chain"]),
        AttestationElement("sybil_indicators", "behavioral", 0.8, ["consistency", "graph_position", "stylometry", "channel_desync"]),
    ]
    
    scenarios = [
        ("Simple liveness check", simple),
        ("Behavioral attestation", behavioral),
        ("Full trust assessment", full),
    ]
    
    print("\n--- Element Interactivity Analysis ---\n")
    for name, elements in scenarios:
        result = compute_element_interactivity(elements)
        print(f"{name}:")
        print(f"  Elements: {result['elements']}, Dependencies: {result['dependency_edges']}")
        print(f"  Interactivity: {result['interactivity']}, Intrinsic load: {result['intrinsic_load']}")
        print(f"  Max simultaneous: {result['max_simultaneous']}, WM demand: {result['wm_demand_fraction']}")
        print(f"  Category: {result['category']}")
        print()
    
    # Expertise reversal demo
    print("--- Expertise Reversal Check ---\n")
    for exp, scaffold_desc in [(2, "heavy guidance"), (25, "moderate guidance"), (100, "heavy guidance")]:
        scaffold = 0.8 if "heavy" in scaffold_desc else 0.5
        result = expertise_reversal_check(0.6, exp, scaffold)
        print(f"Attestor ({exp} prior attestations, {scaffold_desc}):")
        print(f"  Expertise: {result['attestor_expertise']}, Optimal scaffold: {result['optimal_scaffolding']}")
        print(f"  Effect: {result['effect']}")
        print(f"  {result['note']}")
        print()
    
    # Split attention demo
    print("--- Split Attention Check ---\n")
    formats = [
        ("Separate dashboards", {"information_sources": ["behavioral", "graph", "temporal", "content"], "physically_integrated": False, "redundant_sources": []}),
        ("Integrated dashboard", {"information_sources": ["behavioral", "graph", "temporal", "content"], "physically_integrated": True, "redundant_sources": []}),
        ("Integrated + redundant", {"information_sources": ["behavioral", "graph", "temporal", "content", "summary"], "physically_integrated": True, "redundant_sources": ["summary"]}),
    ]
    
    for name, fmt in formats:
        result = split_attention_check(fmt)
        print(f"{name}: {result['effect']} (extraneous load: {result['extraneous_load']})")
        print(f"  {result['recommendation']}")
        print()
    
    # Key insight
    print("=" * 60)
    print("KEY INSIGHT (Sweller 2023):")
    print("Every replication failure in CLT expanded the theory.")
    print("Split-attention failed → redundancy effect discovered.")
    print("Modality failed → transient information effect discovered.")
    print("Expertise reversal: what helps novices HARMS experts.")
    print()
    print("For ATF: roughness (0.068) failed → burstiness worked.")
    print("Single metrics fail → composite detection expands.")
    print("Replication failure IS the productive mechanism.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
