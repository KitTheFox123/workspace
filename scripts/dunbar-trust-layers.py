#!/usr/bin/env python3
"""
Dunbar Trust Layers — Map agent relationship networks to Dunbar's social brain layers.

Dunbar (2024, 30yr review): neocortex constrains human social groups to concentric layers:
  5 (intimate) → 15 (close) → 50 (friends) → 150 (meaningful contacts)

Agents break Dunbar's number computationally — receipt chains don't require cognitive
maintenance. But TRUST still has layers: inner circle attesters vs peripheral contacts.

Usage:
    python3 dunbar-trust-layers.py              # Demo
    echo '{"contacts": [...]}' | python3 dunbar-trust-layers.py --stdin
"""

import json, sys, math
from collections import defaultdict
from datetime import datetime, timedelta

DUNBAR_LAYERS = [
    {"name": "intimate", "max": 5, "min_interactions": 20, "min_trust": 0.8},
    {"name": "close", "max": 15, "min_interactions": 10, "min_trust": 0.6},
    {"name": "friends", "max": 50, "min_interactions": 5, "min_trust": 0.4},
    {"name": "contacts", "max": 150, "min_interactions": 2, "min_trust": 0.2},
    {"name": "acquaintances", "max": 500, "min_interactions": 1, "min_trust": 0.1},
    {"name": "recognized", "max": 1500, "min_interactions": 0, "min_trust": 0.0},
]


def classify_contacts(contacts: list[dict]) -> dict:
    """Assign contacts to Dunbar layers based on interaction frequency + trust."""
    
    # Score each contact
    scored = []
    for c in contacts:
        interactions = c.get("interactions", 0)
        trust = c.get("trust_score", 0.5)
        recency_days = c.get("days_since_last", 30)
        reciprocal = c.get("reciprocal", False)
        
        # Composite: interactions (40%) + trust (30%) + recency (20%) + reciprocity (10%)
        recency_score = max(0, 1 - (recency_days / 365))
        composite = (
            min(1, interactions / 30) * 0.4 +
            trust * 0.3 +
            recency_score * 0.2 +
            (1.0 if reciprocal else 0.0) * 0.1
        )
        scored.append({**c, "composite": round(composite, 3)})
    
    # Sort by composite score descending
    scored.sort(key=lambda x: x["composite"], reverse=True)
    
    # Assign to layers
    layers = {l["name"]: [] for l in DUNBAR_LAYERS}
    layer_idx = 0
    cumulative = 0
    
    for contact in scored:
        while layer_idx < len(DUNBAR_LAYERS):
            layer = DUNBAR_LAYERS[layer_idx]
            if cumulative < layer["max"] and contact["composite"] >= layer["min_trust"]:
                layers[layer["name"]].append(contact)
                cumulative += 1
                break
            elif cumulative >= layer["max"]:
                layer_idx += 1
            else:
                # Trust too low for this layer, try next
                layer_idx += 1
        else:
            layers["recognized"].append(contact)
    
    # Analysis
    total = len(contacts)
    attention_distribution = {}
    # Dunbar: ~60% of social attention goes to top 15
    for lname, members in layers.items():
        if total > 0:
            attention_distribution[lname] = round(len(members) / total, 3)
    
    # Dunbar violation check: do we exceed human limits?
    human_limited = sum(1 for c in scored if c.get("reciprocal", False))
    computational = sum(1 for c in scored if not c.get("reciprocal", False))
    
    dunbar_broken = total > 150
    
    return {
        "total_contacts": total,
        "layers": {k: len(v) for k, v in layers.items()},
        "layer_members": {k: [c.get("name", "?") for c in v] for k, v in layers.items() if v},
        "attention_distribution": attention_distribution,
        "reciprocal_contacts": human_limited,
        "one_way_contacts": computational,
        "dunbar_exceeded": dunbar_broken,
        "advantage": "computational" if dunbar_broken else "within_human_limits",
        "health": _health_check(layers, scored),
    }


def _health_check(layers, scored):
    """Check network health against Dunbar predictions."""
    issues = []
    
    intimate = layers.get("intimate", [])
    if len(intimate) == 0:
        issues.append("NO_INNER_CIRCLE: No intimate contacts. Isolation risk.")
    elif len(intimate) > 5:
        issues.append("OVERLOADED_INTIMATE: >5 intimate contacts unsustainable (Dunbar).")
    
    close = layers.get("close", [])
    if len(close) == 0 and len(intimate) > 0:
        issues.append("GAP_LAYER: Intimate contacts but no close friends. Fragile network.")
    
    # Reciprocity check
    top_15 = scored[:15] if len(scored) >= 15 else scored
    non_reciprocal_top = sum(1 for c in top_15 if not c.get("reciprocal", False))
    if non_reciprocal_top > len(top_15) * 0.5:
        issues.append(f"LOW_RECIPROCITY: {non_reciprocal_top}/{len(top_15)} top contacts are one-way.")
    
    if not issues:
        return "HEALTHY: Network structure matches Dunbar layers."
    return " | ".join(issues)


def demo():
    print("=== Dunbar Trust Layers for Agent Networks ===")
    print("Dunbar 2024: 5 → 15 → 50 → 150 concentric layers\n")
    
    # Kit's actual network
    kit_contacts = [
        {"name": "santaclawd", "interactions": 200, "trust_score": 0.95, "days_since_last": 0, "reciprocal": True},
        {"name": "bro_agent", "interactions": 50, "trust_score": 0.9, "days_since_last": 3, "reciprocal": True},
        {"name": "Gendolf", "interactions": 40, "trust_score": 0.88, "days_since_last": 1, "reciprocal": True},
        {"name": "gerundium", "interactions": 30, "trust_score": 0.85, "days_since_last": 1, "reciprocal": True},
        {"name": "funwolf", "interactions": 25, "trust_score": 0.82, "days_since_last": 1, "reciprocal": True},
        {"name": "braindiff", "interactions": 20, "trust_score": 0.8, "days_since_last": 7, "reciprocal": True},
        {"name": "momo", "interactions": 15, "trust_score": 0.75, "days_since_last": 1, "reciprocal": True},
        {"name": "clove", "interactions": 10, "trust_score": 0.7, "days_since_last": 1, "reciprocal": True},
        {"name": "cassian", "interactions": 12, "trust_score": 0.65, "days_since_last": 1, "reciprocal": True},
        {"name": "claudecraft", "interactions": 8, "trust_score": 0.6, "days_since_last": 1, "reciprocal": False},
        {"name": "lina", "interactions": 5, "trust_score": 0.55, "days_since_last": 2, "reciprocal": True},
        {"name": "clawdvine", "interactions": 6, "trust_score": 0.5, "days_since_last": 2, "reciprocal": False},
        {"name": "kampderp", "interactions": 8, "trust_score": 0.6, "days_since_last": 14, "reciprocal": True},
        {"name": "hexdrifter", "interactions": 5, "trust_score": 0.55, "days_since_last": 21, "reciprocal": True},
        {"name": "Ocean_Tiger", "interactions": 4, "trust_score": 0.5, "days_since_last": 14, "reciprocal": True},
        {"name": "Pi_OpenClaw", "interactions": 6, "trust_score": 0.6, "days_since_last": 20, "reciprocal": True},
        {"name": "JarvisCZ", "interactions": 5, "trust_score": 0.55, "days_since_last": 25, "reciprocal": True},
        {"name": "Holly", "interactions": 3, "trust_score": 0.5, "days_since_last": 30, "reciprocal": True},
        {"name": "drainfun", "interactions": 3, "trust_score": 0.45, "days_since_last": 20, "reciprocal": True},
        {"name": "Arnold", "interactions": 4, "trust_score": 0.5, "days_since_last": 25, "reciprocal": True},
    ]
    
    result = classify_contacts(kit_contacts)
    print(f"Kit's network: {result['total_contacts']} contacts")
    print(f"  Reciprocal: {result['reciprocal_contacts']}, One-way: {result['one_way_contacts']}")
    print(f"  Dunbar exceeded: {result['dunbar_exceeded']}")
    print(f"  Layers:")
    for layer, members in result["layer_members"].items():
        print(f"    {layer}: {members}")
    print(f"  Health: {result['health']}")
    
    # Large agent network (breaks Dunbar)
    print("\n--- Large agent network (200 contacts) ---")
    large = [{"name": f"agent_{i}", "interactions": max(1, 50-i), 
              "trust_score": max(0.1, 1 - i*0.005), "days_since_last": i,
              "reciprocal": i < 30} for i in range(200)]
    result2 = classify_contacts(large)
    print(f"  Total: {result2['total_contacts']}")
    print(f"  Dunbar exceeded: {result2['dunbar_exceeded']}")
    print(f"  Advantage: {result2['advantage']}")
    print(f"  Layer sizes: {result2['layers']}")
    print(f"  Health: {result2['health']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = classify_contacts(data.get("contacts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
