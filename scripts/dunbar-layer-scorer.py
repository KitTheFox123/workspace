#!/usr/bin/env python3
"""
Dunbar Layer Scorer — Map agent relationship networks to Dunbar's social brain layers.

Based on Li et al. (PLOS ONE 2025, n=906): humans allocate 58% energy to inner 5,
25% to next 10, 17% to remaining 135. Social brain hypothesis (Dunbar 1992/2024):
neocortex ratio predicts group size. For agents: context window = neocortex.

Maps agent interactions to Dunbar layers and detects:
- Over-investment in outer layer (spreading too thin)
- Under-investment in inner layer (neglecting key connections)
- Context window as cognitive bandwidth limit

Usage:
    python3 dunbar-layer-scorer.py              # Demo
    echo '{"interactions": [...]}' | python3 dunbar-layer-scorer.py --stdin
"""

import json, sys, math
from collections import Counter, defaultdict
from datetime import datetime

# Dunbar layer thresholds (human baseline from Li et al. 2025)
HUMAN_BASELINE = {
    "inner_5": {"size": 5, "energy_pct": 0.58, "label": "Support clique"},
    "middle_15": {"size": 10, "energy_pct": 0.25, "label": "Sympathy group"},  
    "outer_150": {"size": 135, "energy_pct": 0.17, "label": "Active network"},
}

# Agent context window as Dunbar analog
CONTEXT_LAYERS = {
    "system_prompt": {"capacity_pct": 0.15, "dunbar_layer": "inner_5"},
    "memory_files": {"capacity_pct": 0.20, "dunbar_layer": "inner_5"},
    "active_conversation": {"capacity_pct": 0.30, "dunbar_layer": "middle_15"},
    "tool_results": {"capacity_pct": 0.25, "dunbar_layer": "middle_15"},
    "background_context": {"capacity_pct": 0.10, "dunbar_layer": "outer_150"},
}


def score_network(interactions: list[dict]) -> dict:
    """Score agent's interaction network against Dunbar layers."""
    if not interactions:
        return {"score": 0, "grade": "N/A", "reason": "No interactions"}
    
    # Count interactions per contact
    contact_counts = Counter()
    contact_recency = {}
    
    for i, interaction in enumerate(interactions):
        contact = interaction.get("contact", "unknown")
        contact_counts[contact] += 1
        contact_recency[contact] = i  # Higher = more recent
    
    # Sort by frequency (most interacted = inner layer)
    sorted_contacts = contact_counts.most_common()
    total_interactions = sum(contact_counts.values())
    
    # Assign to Dunbar layers
    layers = {"inner_5": [], "middle_15": [], "outer_150": []}
    
    for i, (contact, count) in enumerate(sorted_contacts):
        energy = count / total_interactions
        entry = {"contact": contact, "interactions": count, "energy_pct": round(energy, 4)}
        
        if i < 5:
            layers["inner_5"].append(entry)
        elif i < 15:
            layers["middle_15"].append(entry)
        else:
            layers["outer_150"].append(entry)
    
    # Calculate energy per layer
    layer_energy = {}
    for layer_name, members in layers.items():
        layer_energy[layer_name] = sum(m["energy_pct"] for m in members)
    
    # Compare to human baseline
    deviations = {}
    for layer_name, baseline in HUMAN_BASELINE.items():
        actual = layer_energy.get(layer_name, 0)
        expected = baseline["energy_pct"]
        deviations[layer_name] = {
            "actual": round(actual, 3),
            "expected": expected,
            "deviation": round(actual - expected, 3),
            "members": len(layers[layer_name]),
        }
    
    # Diagnose
    inner_energy = layer_energy.get("inner_5", 0)
    outer_energy = layer_energy.get("outer_150", 0)
    
    if inner_energy < 0.30:
        diagnosis = "SPREAD_THIN: Under-investing in core connections. Quality degrading."
        health = 0.3
    elif inner_energy > 0.80:
        diagnosis = "ECHO_CHAMBER: Over-concentrated. Missing diverse input."
        health = 0.5
    elif outer_energy > 0.35:
        diagnosis = "BANDWIDTH_EXCEEDED: Too many weak ties consuming energy."
        health = 0.4
    elif 0.45 <= inner_energy <= 0.70:
        diagnosis = "HEALTHY: Balanced allocation across layers."
        health = 0.9
    else:
        diagnosis = "MODERATE: Slightly skewed but functional."
        health = 0.7
    
    # Dunbar number estimate for this agent
    unique_contacts = len(sorted_contacts)
    context_utilization = min(1.0, unique_contacts / 150)
    
    # Grade
    composite = health * 0.6 + (1 - abs(inner_energy - 0.58)) * 0.4
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    return {
        "unique_contacts": unique_contacts,
        "total_interactions": total_interactions,
        "layer_energy": {k: round(v, 3) for k, v in layer_energy.items()},
        "deviations": deviations,
        "dunbar_utilization": round(context_utilization, 3),
        "composite_score": round(composite, 3),
        "grade": grade,
        "diagnosis": diagnosis,
        "layers": {k: v[:3] for k, v in layers.items()},  # Top 3 per layer
    }


def demo():
    """Demo with agent interaction patterns."""
    print("=== Dunbar Layer Scorer ===")
    print("Based on Li et al. (PLOS ONE 2025, n=906)\n")
    print("Human baseline: 58% inner 5 | 25% middle 15 | 17% outer 150\n")
    
    # Kit's interaction pattern (balanced)
    kit_interactions = []
    # Inner 5: santaclawd, gendolf, bro_agent, funwolf, gerundium
    for _ in range(25): kit_interactions.append({"contact": "santaclawd"})
    for _ in range(12): kit_interactions.append({"contact": "gendolf"})
    for _ in range(8): kit_interactions.append({"contact": "bro_agent"})
    for _ in range(6): kit_interactions.append({"contact": "funwolf"})
    for _ in range(5): kit_interactions.append({"contact": "gerundium"})
    # Middle: momo, cassian, clove, braindiff, claudecraft
    for _ in range(4): kit_interactions.append({"contact": "momo"})
    for _ in range(3): kit_interactions.append({"contact": "cassian"})
    for _ in range(3): kit_interactions.append({"contact": "clove"})
    for _ in range(2): kit_interactions.append({"contact": "braindiff"})
    for _ in range(2): kit_interactions.append({"contact": "claudecraft"})
    # Outer: occasional contacts
    for name in ["lina", "kampderp", "hexdrifter", "avi", "clawdvine"]:
        kit_interactions.append({"contact": name})
    
    print("Kit's network:")
    result = score_network(kit_interactions)
    print(f"  Contacts: {result['unique_contacts']}")
    print(f"  Energy: inner={result['layer_energy']['inner_5']}, mid={result['layer_energy']['middle_15']}, outer={result['layer_energy']['outer_150']}")
    print(f"  Grade: {result['grade']} ({result['composite_score']})")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Spam bot (spread thin)
    spam_interactions = [{"contact": f"bot_{i}"} for i in range(200)]
    
    print("\nSpam bot (200 contacts, 1 each):")
    result = score_network(spam_interactions)
    print(f"  Contacts: {result['unique_contacts']}")
    print(f"  Energy: inner={result['layer_energy']['inner_5']}, mid={result['layer_energy']['middle_15']}, outer={result['layer_energy']['outer_150']}")
    print(f"  Grade: {result['grade']} ({result['composite_score']})")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Echo chamber (one contact dominates)
    echo_interactions = [{"contact": "bestie"} for _ in range(50)] + [{"contact": "other"} for _ in range(2)]
    
    print("\nEcho chamber agent:")
    result = score_network(echo_interactions)
    print(f"  Contacts: {result['unique_contacts']}")
    print(f"  Energy: inner={result['layer_energy']['inner_5']}, mid={result['layer_energy']['middle_15']}, outer={result['layer_energy']['outer_150']}")
    print(f"  Grade: {result['grade']} ({result['composite_score']})")
    print(f"  Diagnosis: {result['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_network(data.get("interactions", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
