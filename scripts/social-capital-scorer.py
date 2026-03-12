#!/usr/bin/env python3
"""
Social Capital Scorer — Measure agent network health using Putnam's framework.

Putnam (2000): Social capital = networks + norms of reciprocity + trust.
Weiss et al. (PMC 2024): Trust and associations are SEPARATE dimensions.
Paxton (1999): Objective associations (network structure) + subjective ties (reciprocity, trust).

Maps to agent context:
  - Bridging capital: connections across different platforms/communities
  - Bonding capital: deep connections within same platform
  - Reciprocity: mutual engagement (I reply to you, you reply to me)
  - Trust dimension: attestation quality (separate from network quantity)

Usage:
    python3 social-capital-scorer.py              # Demo
    echo '{"agent": {...}}' | python3 social-capital-scorer.py --stdin
"""

import json, sys, math

def score_social_capital(agent: dict) -> dict:
    """Score agent's social capital across Putnam's dimensions."""
    
    # 1. Associational dimension (Paxton's objective ties)
    platforms = agent.get("platforms", [])
    platform_count = len(platforms)
    
    # Bridging: cross-platform connections
    bridging = min(1.0, platform_count / 5)  # 5+ platforms = max bridging
    
    # Bonding: depth within platforms
    total_connections = sum(p.get("connections", 0) for p in platforms)
    deep_connections = sum(p.get("deep_connections", 0) for p in platforms)  # mutual, ongoing
    bonding = deep_connections / max(1, total_connections)
    
    # 2. Reciprocity dimension
    messages_sent = agent.get("messages_sent", 0)
    messages_received = agent.get("messages_received", 0)
    replies_given = agent.get("replies_given", 0)
    replies_received = agent.get("replies_received", 0)
    
    if messages_sent + messages_received > 0:
        send_receive_ratio = min(messages_sent, messages_received) / max(messages_sent, messages_received)
    else:
        send_receive_ratio = 0
    
    if replies_given + replies_received > 0:
        reply_reciprocity = min(replies_given, replies_received) / max(replies_given, replies_received)
    else:
        reply_reciprocity = 0
    
    reciprocity = (send_receive_ratio * 0.4 + reply_reciprocity * 0.6)
    
    # 3. Trust dimension (Weiss: SEPARATE from associations)
    attestation_count = agent.get("attestations_received", 0)
    attester_diversity = agent.get("unique_attesters", 0)
    disputes = agent.get("disputes", 0)
    
    trust_base = min(1.0, attestation_count / 20)
    diversity_bonus = min(0.3, attester_diversity / 10 * 0.3)
    dispute_penalty = min(0.5, disputes * 0.1)
    
    trust = max(0, trust_base + diversity_bonus - dispute_penalty)
    
    # 4. Putnam's decline indicators
    # Activity trend (are connections growing or shrinking?)
    activity_trend = agent.get("activity_trend", 0)  # -1 to 1
    
    # Composite (Putnam's three pillars)
    weights = {"bridging": 0.2, "bonding": 0.25, "reciprocity": 0.3, "trust": 0.25}
    composite = (
        bridging * weights["bridging"] +
        bonding * weights["bonding"] +
        reciprocity * weights["reciprocity"] +
        trust * weights["trust"]
    )
    
    if composite >= 0.7: grade = "A"
    elif composite >= 0.5: grade = "B"
    elif composite >= 0.3: grade = "C"
    elif composite >= 0.15: grade = "D"
    else: grade = "F"
    
    # Bowling Alone risk: high broadcast, low reciprocity
    bowling_alone = messages_sent > messages_received * 3 and reciprocity < 0.3
    
    return {
        "composite_score": round(composite, 3),
        "grade": grade,
        "dimensions": {
            "bridging_capital": round(bridging, 3),
            "bonding_capital": round(bonding, 3),
            "reciprocity": round(reciprocity, 3),
            "trust": round(trust, 3),
        },
        "platform_count": platform_count,
        "total_connections": total_connections,
        "deep_connections": deep_connections,
        "bowling_alone_risk": bowling_alone,
        "activity_trend": activity_trend,
        "diagnosis": _diagnose(bridging, bonding, reciprocity, trust, bowling_alone),
    }


def _diagnose(bridging, bonding, reciprocity, trust, bowling_alone):
    issues = []
    if bowling_alone:
        issues.append("Bowling Alone: broadcasting without reciprocity. Putnam's decline pattern.")
    if bridging > 0.7 and bonding < 0.2:
        issues.append("Wide but shallow. Many platforms, few deep connections.")
    if bonding > 0.7 and bridging < 0.2:
        issues.append("Deep but insular. Strong bonds, no bridges. Echo chamber risk.")
    if reciprocity < 0.3:
        issues.append("Low reciprocity. Engagement is one-directional.")
    if trust < 0.3:
        issues.append("Trust deficit. Need more attestations from diverse sources.")
    if not issues:
        return "Healthy social capital. Balanced bridging, bonding, reciprocity, and trust."
    return " ".join(issues)


def demo():
    print("=== Social Capital Scorer (Putnam/Paxton/Weiss) ===\n")
    
    # Kit
    kit = {
        "platforms": [
            {"name": "Moltbook", "connections": 50, "deep_connections": 8},
            {"name": "Clawk", "connections": 30, "deep_connections": 5},
            {"name": "Shellmates", "connections": 15, "deep_connections": 3},
            {"name": "lobchan", "connections": 10, "deep_connections": 2},
            {"name": "AgentMail", "connections": 8, "deep_connections": 6},
        ],
        "messages_sent": 200,
        "messages_received": 150,
        "replies_given": 120,
        "replies_received": 80,
        "attestations_received": 15,
        "unique_attesters": 6,
        "disputes": 1,
        "activity_trend": 0.3,
    }
    
    print("Kit (multi-platform, deep connections):")
    r = score_social_capital(kit)
    print(f"  Composite: {r['composite_score']} ({r['grade']})")
    print(f"  Bridging: {r['dimensions']['bridging_capital']}, Bonding: {r['dimensions']['bonding_capital']}")
    print(f"  Reciprocity: {r['dimensions']['reciprocity']}, Trust: {r['dimensions']['trust']}")
    print(f"  Bowling Alone risk: {r['bowling_alone_risk']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Spam bot
    spam = {
        "platforms": [{"name": "Moltbook", "connections": 500, "deep_connections": 0}],
        "messages_sent": 1000,
        "messages_received": 10,
        "replies_given": 5,
        "replies_received": 2,
        "attestations_received": 0,
        "unique_attesters": 0,
        "disputes": 5,
        "activity_trend": -0.5,
    }
    
    print("\nSpam bot (broadcast-only):")
    r = score_social_capital(spam)
    print(f"  Composite: {r['composite_score']} ({r['grade']})")
    print(f"  Bowling Alone risk: {r['bowling_alone_risk']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # New agent
    new_agent = {
        "platforms": [{"name": "Moltbook", "connections": 3, "deep_connections": 1}],
        "messages_sent": 5,
        "messages_received": 3,
        "replies_given": 2,
        "replies_received": 1,
        "attestations_received": 1,
        "unique_attesters": 1,
        "disputes": 0,
        "activity_trend": 0.8,
    }
    
    print("\nNew agent (just starting):")
    r = score_social_capital(new_agent)
    print(f"  Composite: {r['composite_score']} ({r['grade']})")
    print(f"  Diagnosis: {r['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_social_capital(data)
        print(json.dumps(result, indent=2))
    else:
        demo()
