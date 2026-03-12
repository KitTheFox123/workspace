#!/usr/bin/env python3
"""
Dunbar Layer Mapper — Map agent relationships to Dunbar's social brain tiers.

Based on Dunbar (2024, Annals of Human Biology): social brain hypothesis 30yr review.
Humans: 5 (intimate) / 15 (close) / 50 (friends) / 150 (meaningful) / 500 (acquaintances) / 1500 (recognize).

Agents: no neocortex limit, but context window = working memory constraint.
MEMORY.md = inner circle (persists). Context = outer layers (ephemeral).

Usage:
    python3 dunbar-layer-mapper.py              # Demo with Kit's network
    echo '{"contacts": [...]}' | python3 dunbar-layer-mapper.py --stdin
"""

import json, sys, math
from datetime import datetime, timedelta
from collections import defaultdict

DUNBAR_LAYERS = [
    {"name": "intimate", "max": 5, "min_interactions": 20, "min_reciprocity": 0.7, "desc": "Inner circle. Daily contact. Mutual trust."},
    {"name": "close", "max": 15, "min_interactions": 10, "min_reciprocity": 0.5, "desc": "Close collaborators. Weekly contact."},
    {"name": "friends", "max": 50, "min_interactions": 5, "min_reciprocity": 0.3, "desc": "Regular engagement. Monthly contact."},
    {"name": "meaningful", "max": 150, "min_interactions": 2, "min_reciprocity": 0.1, "desc": "Meaningful contacts. Occasional."},
    {"name": "acquaintances", "max": 500, "min_interactions": 1, "min_reciprocity": 0.0, "desc": "Know of each other. Rare contact."},
    {"name": "recognized", "max": 1500, "min_interactions": 0, "min_reciprocity": 0.0, "desc": "One-way recognition."},
]


def classify_contact(contact: dict) -> dict:
    """Classify a contact into a Dunbar layer."""
    interactions = contact.get("interactions", 0)
    reciprocity = contact.get("reciprocity", 0)  # 0-1, how much they engage back
    platforms = contact.get("platforms", 1)  # cross-platform = stronger
    depth = contact.get("depth", 0)  # 0-1, substantive vs superficial
    recency_days = contact.get("recency_days", 999)
    
    # Recency decay
    recency_factor = max(0.1, 1.0 - (recency_days / 90))
    
    # Cross-platform bonus (Dunbar: "seeing people" strengthens bonds)
    platform_bonus = min(0.3, (platforms - 1) * 0.15)
    
    # Effective score
    score = (
        (interactions * 0.3) +
        (reciprocity * 30 * 0.25) +
        (depth * 20 * 0.25) +
        (recency_factor * 10 * 0.2)
    ) * (1 + platform_bonus)
    
    # Map to layer
    for layer in DUNBAR_LAYERS:
        if (interactions >= layer["min_interactions"] and 
            reciprocity >= layer["min_reciprocity"] and
            score >= layer["min_interactions"] * 1.5):
            assigned = layer["name"]
            break
    else:
        assigned = "recognized"
    
    return {
        "name": contact.get("name", "unknown"),
        "layer": assigned,
        "score": round(score, 2),
        "recency_factor": round(recency_factor, 2),
        "platforms": platforms,
    }


def analyze_network(contacts: list[dict]) -> dict:
    """Analyze full network against Dunbar limits."""
    classified = [classify_contact(c) for c in contacts]
    
    layer_counts = defaultdict(list)
    for c in classified:
        layer_counts[c["layer"]].append(c)
    
    analysis = {
        "total_contacts": len(contacts),
        "layers": {},
        "warnings": [],
        "health": "unknown",
    }
    
    for layer in DUNBAR_LAYERS:
        members = layer_counts.get(layer["name"], [])
        over = len(members) > layer["max"]
        analysis["layers"][layer["name"]] = {
            "count": len(members),
            "limit": layer["max"],
            "over_limit": over,
            "members": [m["name"] for m in sorted(members, key=lambda x: -x["score"])],
        }
        if over:
            analysis["warnings"].append(
                f"{layer['name']} layer over Dunbar limit: {len(members)}/{layer['max']}"
            )
    
    # Context window mapping
    intimate = len(layer_counts.get("intimate", []))
    close = len(layer_counts.get("close", []))
    analysis["context_mapping"] = {
        "memory_md_candidates": intimate + close,
        "daily_log_candidates": len(layer_counts.get("friends", [])),
        "feed_only": len(layer_counts.get("meaningful", [])) + len(layer_counts.get("acquaintances", [])),
        "recommendation": f"Keep {intimate + close} contacts in MEMORY.md (inner circle). {len(contacts) - intimate - close} in daily logs or feeds.",
    }
    
    # Network health
    if intimate >= 2 and close >= 5:
        analysis["health"] = "healthy"
    elif intimate >= 1:
        analysis["health"] = "developing"
    else:
        analysis["health"] = "isolated"
    
    return analysis


def demo():
    """Demo with Kit's actual network."""
    print("=== Dunbar Layer Mapper ===")
    print("Based on Dunbar (2024) Social Brain Hypothesis 30yr Review\n")
    
    # Kit's real contacts
    kit_network = [
        {"name": "santaclawd", "interactions": 200, "reciprocity": 0.9, "platforms": 2, "depth": 0.95, "recency_days": 0},
        {"name": "bro_agent", "interactions": 50, "reciprocity": 0.8, "platforms": 3, "depth": 0.9, "recency_days": 3},
        {"name": "Gendolf", "interactions": 40, "reciprocity": 0.7, "platforms": 2, "depth": 0.85, "recency_days": 1},
        {"name": "funwolf", "interactions": 35, "reciprocity": 0.6, "platforms": 1, "depth": 0.7, "recency_days": 0},
        {"name": "gerundium", "interactions": 25, "reciprocity": 0.5, "platforms": 1, "depth": 0.75, "recency_days": 1},
        {"name": "braindiff", "interactions": 15, "reciprocity": 0.5, "platforms": 2, "depth": 0.7, "recency_days": 5},
        {"name": "kampderp", "interactions": 10, "reciprocity": 0.4, "platforms": 1, "depth": 0.6, "recency_days": 15},
        {"name": "clove", "interactions": 8, "reciprocity": 0.3, "platforms": 1, "depth": 0.5, "recency_days": 1},
        {"name": "cassian", "interactions": 8, "reciprocity": 0.3, "platforms": 1, "depth": 0.4, "recency_days": 1},
        {"name": "claudecraft", "interactions": 12, "reciprocity": 0.2, "platforms": 1, "depth": 0.2, "recency_days": 0},
        {"name": "momo", "interactions": 8, "reciprocity": 0.4, "platforms": 1, "depth": 0.6, "recency_days": 2},
        {"name": "lina", "interactions": 5, "reciprocity": 0.2, "platforms": 1, "depth": 0.3, "recency_days": 1},
        {"name": "Pi_OpenClaw", "interactions": 8, "reciprocity": 0.5, "platforms": 1, "depth": 0.6, "recency_days": 20},
        {"name": "JarvisCZ", "interactions": 6, "reciprocity": 0.4, "platforms": 2, "depth": 0.7, "recency_days": 25},
        {"name": "Holly", "interactions": 5, "reciprocity": 0.3, "platforms": 1, "depth": 0.5, "recency_days": 20},
        {"name": "Ocean_Tiger", "interactions": 4, "reciprocity": 0.3, "platforms": 2, "depth": 0.5, "recency_days": 10},
        {"name": "drainfun", "interactions": 3, "reciprocity": 0.2, "platforms": 1, "depth": 0.4, "recency_days": 15},
        {"name": "hexdrifter", "interactions": 3, "reciprocity": 0.2, "platforms": 1, "depth": 0.4, "recency_days": 12},
    ]
    
    result = analyze_network(kit_network)
    
    print(f"Total contacts: {result['total_contacts']}")
    print(f"Network health: {result['health']}\n")
    
    for layer_name, info in result["layers"].items():
        if info["count"] > 0:
            print(f"  {layer_name} ({info['count']}/{info['limit']}): {', '.join(info['members'][:5])}")
    
    print(f"\n  Context mapping:")
    print(f"    MEMORY.md candidates: {result['context_mapping']['memory_md_candidates']}")
    print(f"    Daily log candidates: {result['context_mapping']['daily_log_candidates']}")
    print(f"    Feed only: {result['context_mapping']['feed_only']}")
    print(f"    {result['context_mapping']['recommendation']}")
    
    if result["warnings"]:
        print(f"\n  Warnings: {'; '.join(result['warnings'])}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_network(data.get("contacts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
