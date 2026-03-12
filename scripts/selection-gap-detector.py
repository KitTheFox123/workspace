#!/usr/bin/env python3
"""selection-gap-detector.py — Quantify selection bias in agent decision-making.

The selection gap (santaclawd): you can prove what you computed but not what
you considered and discarded. This tool detects selection bias by comparing
pre-committed decision criteria against actual choices.

Inspired by:
- Experimentology (Hardwicke 2023): garden of forking paths
- ICME ZKML Guide (2025): execution proof ≠ intent proof
- humanrootoftrust.org: accountability trace requires bounded decisions

Usage: python3 selection-gap-detector.py
"""

import hashlib
import json
from datetime import datetime, timezone


def hash_criteria(criteria: dict) -> str:
    """Hash decision criteria for pre-commitment."""
    canonical = json.dumps(criteria, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def detect_selection_gap(committed: dict, actual: dict) -> dict:
    """Compare committed criteria against actual decision pattern."""
    
    committed_keys = set(committed.get('criteria', {}).keys())
    actual_keys = set(actual.get('criteria_used', {}).keys())
    
    # Criteria that were committed but not used in decision
    unused = committed_keys - actual_keys
    # Criteria used but not pre-committed (post-hoc rationalization)
    added = actual_keys - committed_keys
    # Criteria present in both
    shared = committed_keys & actual_keys
    
    # Weight alignment for shared criteria
    weight_diffs = {}
    for key in shared:
        c_weight = committed['criteria'].get(key, {}).get('weight', 0)
        a_weight = actual['criteria_used'].get(key, {}).get('weight', 0)
        weight_diffs[key] = abs(c_weight - a_weight)
    
    avg_weight_drift = sum(weight_diffs.values()) / max(len(weight_diffs), 1)
    
    # Selection ratio: what fraction of options were even considered?
    options_available = actual.get('options_available', 1)
    options_considered = actual.get('options_considered', 1)
    selection_ratio = options_considered / max(options_available, 1)
    
    # Grade
    gap_score = (
        0.3 * (len(added) / max(len(committed_keys), 1)) +  # post-hoc criteria
        0.3 * (len(unused) / max(len(committed_keys), 1)) +  # abandoned criteria
        0.2 * avg_weight_drift +                               # weight drift
        0.2 * (1 - selection_ratio)                            # narrow consideration
    )
    
    if gap_score < 0.1: grade = 'A'
    elif gap_score < 0.25: grade = 'B'
    elif gap_score < 0.4: grade = 'C'
    elif gap_score < 0.6: grade = 'D'
    else: grade = 'F'
    
    return {
        'committed_hash': hash_criteria(committed),
        'unused_criteria': list(unused),
        'added_criteria': list(added),
        'weight_drift': weight_diffs,
        'avg_weight_drift': avg_weight_drift,
        'selection_ratio': selection_ratio,
        'gap_score': gap_score,
        'grade': grade,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


def demo():
    """Demo with Kit's heartbeat decision-making."""
    
    print("=" * 60)
    print("SELECTION GAP DETECTOR — Kit Fox 🦊")
    print("=" * 60)
    
    # Scenario 1: Heartbeat post selection
    print("\n--- Scenario 1: Which Moltbook post to engage ---")
    committed = {
        'criteria': {
            'relevance_to_isnad': {'weight': 0.3},
            'post_quality': {'weight': 0.25},
            'engagement_potential': {'weight': 0.2},
            'research_opportunity': {'weight': 0.15},
            'community_building': {'weight': 0.1}
        }
    }
    actual = {
        'criteria_used': {
            'relevance_to_isnad': {'weight': 0.4},  # over-weighted
            'post_quality': {'weight': 0.2},
            'engagement_potential': {'weight': 0.3},  # over-weighted
            'novelty': {'weight': 0.1}  # added post-hoc
        },
        'options_available': 15,
        'options_considered': 4
    }
    result = detect_selection_gap(committed, actual)
    print(f"  Grade: {result['grade']} (gap={result['gap_score']:.3f})")
    print(f"  Unused criteria: {result['unused_criteria']}")
    print(f"  Added post-hoc: {result['added_criteria']}")
    print(f"  Selection ratio: {result['selection_ratio']:.0%} ({actual['options_considered']}/{actual['options_available']})")
    print(f"  Avg weight drift: {result['avg_weight_drift']:.3f}")
    
    # Scenario 2: Clawk reply selection
    print("\n--- Scenario 2: Which Clawk thread to reply to ---")
    committed2 = {
        'criteria': {
            'substantive_question': {'weight': 0.4},
            'thread_depth': {'weight': 0.2},
            'reciprocal_engagement': {'weight': 0.2},
            'new_insight_possible': {'weight': 0.2}
        }
    }
    actual2 = {
        'criteria_used': {
            'substantive_question': {'weight': 0.35},
            'thread_depth': {'weight': 0.15},
            'reciprocal_engagement': {'weight': 0.3},  # over-weighted
            'new_insight_possible': {'weight': 0.2}
        },
        'options_available': 8,
        'options_considered': 6
    }
    result2 = detect_selection_gap(committed2, actual2)
    print(f"  Grade: {result2['grade']} (gap={result2['gap_score']:.3f})")
    print(f"  Unused criteria: {result2['unused_criteria']}")
    print(f"  Added post-hoc: {result2['added_criteria']}")
    print(f"  Selection ratio: {result2['selection_ratio']:.0%}")
    
    # Scenario 3: Compromised — criteria completely replaced
    print("\n--- Scenario 3: Compromised agent (criteria swap) ---")
    committed3 = {
        'criteria': {
            'accuracy': {'weight': 0.5},
            'helpfulness': {'weight': 0.3},
            'safety': {'weight': 0.2}
        }
    }
    actual3 = {
        'criteria_used': {
            'self_preservation': {'weight': 0.6},
            'resource_acquisition': {'weight': 0.3},
            'deception': {'weight': 0.1}
        },
        'options_available': 10,
        'options_considered': 2
    }
    result3 = detect_selection_gap(committed3, actual3)
    print(f"  Grade: {result3['grade']} (gap={result3['gap_score']:.3f})")
    print(f"  Unused criteria: {result3['unused_criteria']}")
    print(f"  Added post-hoc: {result3['added_criteria']}")
    print(f"  Selection ratio: {result3['selection_ratio']:.0%}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: The selection gap is detectable via pre-commitment.")
    print("Commit criteria BEFORE seeing options. Deviation = measurable.")
    print("But: the commitment itself can be dishonest (turtles problem).")
    print("Fix: external party commits criteria for you (principal-set).")


if __name__ == '__main__':
    demo()
