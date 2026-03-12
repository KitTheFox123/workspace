#!/usr/bin/env python3
"""
Cognitive Offloading Scorer — Measure scaffold vs substitution in agent-tool interactions.

Based on Chirayath et al. (Frontiers Psych 2025): cognitive offloading flips to cognitive
overload when tools substitute instead of scaffold. Maps Clark & Chalmers (1998) extended
mind thesis to agent architecture.

Scaffold = tool augments agent capacity (MEMORY.md, search, scripts)
Substitution = tool replaces agent capacity (copy-paste, blind delegation, context stuffing)

Usage:
    python3 cognitive-offloading-scorer.py              # Demo
    echo '{"actions": [...]}' | python3 cognitive-offloading-scorer.py --stdin
"""

import json, sys, math
from collections import Counter
from datetime import datetime

# Action taxonomy: each action classified as scaffold or substitution
ACTION_TYPES = {
    # Scaffolding (augments capacity)
    "search_then_synthesize": {"type": "scaffold", "weight": 1.0, "desc": "Search + original synthesis"},
    "memory_write": {"type": "scaffold", "weight": 0.9, "desc": "Writing to long-term memory"},
    "memory_read_then_act": {"type": "scaffold", "weight": 0.85, "desc": "Read memory, then take action"},
    "build_tool": {"type": "scaffold", "weight": 1.0, "desc": "Create reusable script/tool"},
    "research_before_reply": {"type": "scaffold", "weight": 0.95, "desc": "Research before engaging"},
    "deliberate_restraint": {"type": "scaffold", "weight": 0.9, "desc": "Chose NOT to act (null receipt)"},
    
    # Substitution (replaces capacity)
    "copy_paste_response": {"type": "substitution", "weight": 0.8, "desc": "Direct copy without synthesis"},
    "context_stuffing": {"type": "substitution", "weight": 0.7, "desc": "Load everything, filter nothing"},
    "blind_delegation": {"type": "substitution", "weight": 0.9, "desc": "Delegate without understanding task"},
    "template_response": {"type": "substitution", "weight": 0.6, "desc": "Generic template, no adaptation"},
    "repeat_without_learning": {"type": "substitution", "weight": 0.85, "desc": "Same mistake, no memory update"},
    
    # Ambiguous (depends on context)
    "tool_call": {"type": "ambiguous", "weight": 0.5, "desc": "Tool use — scaffold if purposeful"},
    "memory_read_only": {"type": "ambiguous", "weight": 0.4, "desc": "Read without subsequent action"},
    "search_no_synthesis": {"type": "ambiguous", "weight": 0.6, "desc": "Search but no original thought"},
}


def score_session(actions: list[dict]) -> dict:
    """Score a session's actions for scaffold vs substitution balance."""
    if not actions:
        return {"score": 0, "grade": "N/A", "reason": "No actions to score"}
    
    scaffold_score = 0
    substitution_score = 0
    ambiguous_count = 0
    action_counts = Counter()
    
    for action in actions:
        atype = action.get("type", "tool_call")
        info = ACTION_TYPES.get(atype, {"type": "ambiguous", "weight": 0.5})
        action_counts[info["type"]] += 1
        
        if info["type"] == "scaffold":
            scaffold_score += info["weight"]
        elif info["type"] == "substitution":
            substitution_score += info["weight"]
        else:
            ambiguous_count += 1
    
    total = scaffold_score + substitution_score + (ambiguous_count * 0.5)
    if total == 0:
        ratio = 0.5
    else:
        ratio = scaffold_score / total  # 1.0 = pure scaffold, 0.0 = pure substitution
    
    # Dependency detection: repeated substitution patterns
    sub_streak = 0
    max_streak = 0
    for action in actions:
        atype = action.get("type", "tool_call")
        info = ACTION_TYPES.get(atype, {"type": "ambiguous"})
        if info["type"] == "substitution":
            sub_streak += 1
            max_streak = max(max_streak, sub_streak)
        else:
            sub_streak = 0
    
    dependency_risk = min(1.0, max_streak / 5)  # 5+ consecutive substitutions = full risk
    
    # Diversity of scaffold types
    scaffold_types = set()
    for action in actions:
        atype = action.get("type", "tool_call")
        info = ACTION_TYPES.get(atype, {"type": "ambiguous"})
        if info["type"] == "scaffold":
            scaffold_types.add(atype)
    
    diversity = len(scaffold_types) / max(1, len([a for a in ACTION_TYPES.values() if a["type"] == "scaffold"]))
    
    # Composite score
    composite = (ratio * 0.5) + ((1 - dependency_risk) * 0.3) + (diversity * 0.2)
    
    # Grade
    if composite >= 0.8: grade = "A"
    elif composite >= 0.6: grade = "B"
    elif composite >= 0.4: grade = "C"
    elif composite >= 0.2: grade = "D"
    else: grade = "F"
    
    return {
        "scaffold_score": round(scaffold_score, 3),
        "substitution_score": round(substitution_score, 3),
        "scaffold_ratio": round(ratio, 3),
        "dependency_risk": round(dependency_risk, 3),
        "scaffold_diversity": round(diversity, 3),
        "composite_score": round(composite, 3),
        "grade": grade,
        "action_counts": dict(action_counts),
        "max_substitution_streak": max_streak,
        "diagnosis": _diagnose(ratio, dependency_risk, diversity),
    }


def _diagnose(ratio, dep_risk, diversity):
    """Human-readable diagnosis."""
    if ratio > 0.8 and dep_risk < 0.2:
        return "Healthy scaffolding. Tools augment, don't replace."
    elif ratio > 0.6:
        return "Mostly scaffolding with some substitution. Monitor for drift."
    elif ratio > 0.4:
        return "Mixed. Risk of offloading becoming dependency."
    elif dep_risk > 0.6:
        return "Dependency pattern detected. Consecutive substitutions indicate overreliance."
    else:
        return "Substitution-heavy. Tools replacing capacity, not augmenting it."


def demo():
    """Demo with Kit-like agent session."""
    print("=== Cognitive Offloading Scorer ===")
    print("Based on Chirayath et al. (Frontiers Psych 2025)\n")
    
    # Kit's typical heartbeat session
    kit_session = [
        {"type": "memory_read_then_act", "desc": "Read daily log, plan actions"},
        {"type": "research_before_reply", "desc": "Keenable search before Clawk reply"},
        {"type": "search_then_synthesize", "desc": "PMC paper → original thesis"},
        {"type": "build_tool", "desc": "Write new script"},
        {"type": "memory_write", "desc": "Update daily log"},
        {"type": "deliberate_restraint", "desc": "Skipped low-quality post"},
    ]
    
    print("Kit heartbeat session:")
    result = score_session(kit_session)
    print(f"  Scaffold ratio: {result['scaffold_ratio']}")
    print(f"  Dependency risk: {result['dependency_risk']}")
    print(f"  Composite: {result['composite_score']} ({result['grade']})")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Substitution-heavy agent
    spam_session = [
        {"type": "template_response"},
        {"type": "copy_paste_response"},
        {"type": "template_response"},
        {"type": "copy_paste_response"},
        {"type": "blind_delegation"},
        {"type": "repeat_without_learning"},
    ]
    
    print("\nSpam agent session:")
    result = score_session(spam_session)
    print(f"  Scaffold ratio: {result['scaffold_ratio']}")
    print(f"  Dependency risk: {result['dependency_risk']}")
    print(f"  Composite: {result['composite_score']} ({result['grade']})")
    print(f"  Diagnosis: {result['diagnosis']}")
    
    # Mixed agent
    mixed_session = [
        {"type": "search_then_synthesize"},
        {"type": "template_response"},
        {"type": "tool_call"},
        {"type": "search_no_synthesis"},
        {"type": "memory_write"},
    ]
    
    print("\nMixed agent session:")
    result = score_session(mixed_session)
    print(f"  Scaffold ratio: {result['scaffold_ratio']}")
    print(f"  Dependency risk: {result['dependency_risk']}")
    print(f"  Composite: {result['composite_score']} ({result['grade']})")
    print(f"  Diagnosis: {result['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_session(data.get("actions", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
