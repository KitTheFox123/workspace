#!/usr/bin/env python3
"""
decision-fatigue-detector.py — Detect decision quality degradation over sequential heartbeats.

Based on Grignoli et al 2025 (PMC11808891) clinical decision fatigue meta-synthesis:
- Negative circular causality: fatigue → errors → distress → more fatigue
- Key markers: avoidant choices, mental shortcuts, decreased persistence, reliance on defaults

Maps clinical DF markers to agent heartbeat patterns:
1. Response latency increase (cognitive slowing)
2. Action diversity decrease (relying on defaults/shortcuts)
3. Research depth decrease (decreased persistence)
4. Engagement quality drop (avoidant/shallow choices)

Contrast with Nature 2025 (s44271-025-00207-8): "No evidence for decision fatigue
using large-scale field data from healthcare" — sequential position effects may be
environmental, not cognitive. We track both interpretations.
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HeartbeatMetrics:
    """Metrics extracted from a single heartbeat cycle."""
    beat_number: int
    timestamp_utc: str
    
    # Cognitive markers
    actions_taken: int = 0           # total actions
    unique_platforms: int = 0        # platform diversity
    research_queries: int = 0        # Keenable searches (persistence)
    sources_fetched: int = 0         # docs actually read
    
    # Quality markers
    reply_depth: float = 0.0         # avg chars per reply (0-1 normalized)
    new_connections: int = 0         # new agents engaged
    threads_entered: int = 0         # distinct conversations
    build_actions: int = 0           # scripts/tools built
    
    # Fatigue signals
    repeated_targets: int = 0        # same thread replied to multiple times
    default_actions: int = 0         # likes/follows vs substantive engagement
    skipped_checks: int = 0          # platforms not checked


def compute_fatigue_score(metrics: HeartbeatMetrics) -> dict:
    """
    Score 0-1 where 0 = fresh, 1 = severely fatigued.
    Based on Grignoli et al's 4 DF markers mapped to agent behavior.
    """
    scores = {}
    
    # 1. Action diversity (mental shortcuts marker)
    # Low platform diversity = relying on comfortable defaults
    platform_score = max(0, 1 - (metrics.unique_platforms / 4))  # 4 platforms = fully diverse
    scores["shortcut_reliance"] = platform_score
    
    # 2. Research persistence (decreased persistence marker)
    # Fewer searches = less thorough investigation
    research_score = max(0, 1 - (metrics.research_queries / 3))  # 3+ queries = persistent
    scores["persistence_drop"] = research_score
    
    # 3. Engagement quality (avoidant choice marker)
    # High ratio of default actions (likes) to substantive actions (replies, posts)
    substantive = metrics.actions_taken - metrics.default_actions
    if metrics.actions_taken > 0:
        avoidance = metrics.default_actions / metrics.actions_taken
    else:
        avoidance = 1.0
    scores["avoidant_choices"] = avoidance
    
    # 4. Repetition pattern (cognitive narrowing)
    # Replying to same threads multiple times = tunnel vision
    if metrics.threads_entered > 0:
        narrowing = metrics.repeated_targets / metrics.threads_entered
    else:
        narrowing = 0.5
    scores["cognitive_narrowing"] = min(1.0, narrowing)
    
    # Composite: weighted average (Grignoli: cognitive + emotional + behavioral + ethical)
    weights = {
        "shortcut_reliance": 0.20,
        "persistence_drop": 0.30,    # persistence most diagnostic per review
        "avoidant_choices": 0.25,
        "cognitive_narrowing": 0.25,
    }
    
    composite = sum(scores[k] * weights[k] for k in weights)
    
    return {
        "composite_fatigue": round(composite, 3),
        "markers": {k: round(v, 3) for k, v in scores.items()},
        "grade": "A" if composite < 0.25 else "B" if composite < 0.45 else "C" if composite < 0.65 else "F",
        "interpretation": interpret_score(composite, scores)
    }


def interpret_score(composite: float, markers: dict) -> str:
    if composite < 0.25:
        return "Fresh — diverse, persistent, substantive engagement"
    elif composite < 0.45:
        return "Mild fatigue — some narrowing, still productive"
    elif composite < 0.65:
        worst = max(markers, key=markers.get)
        return f"Moderate fatigue — primary marker: {worst}. Consider platform rotation or break."
    else:
        return "Severe fatigue — circular causality risk (Grignoli 2025). Reduce decision load."


def detect_circular_causality(history: list[dict]) -> Optional[str]:
    """
    Grignoli's key finding: DF → errors → distress → more DF.
    Look for escalating fatigue across consecutive beats.
    """
    if len(history) < 3:
        return None
    
    scores = [h["composite_fatigue"] for h in history]
    
    # 3+ consecutive increases = circular causality warning
    increases = 0
    for i in range(1, len(scores)):
        if scores[i] > scores[i-1]:
            increases += 1
        else:
            increases = 0
        
        if increases >= 2:
            return (f"⚠️ CIRCULAR CAUSALITY DETECTED: {increases+1} consecutive fatigue increases "
                    f"({' → '.join(f'{s:.2f}' for s in scores[i-increases:i+1])}). "
                    f"Break the cycle: rotate platforms, do a build, or skip social.")
    
    return None


def demo():
    # Simulate a day of heartbeats with progressive fatigue
    beats = [
        HeartbeatMetrics(1, "01:00", actions_taken=8, unique_platforms=4, 
                        research_queries=3, sources_fetched=2, reply_depth=0.8,
                        new_connections=2, threads_entered=4, build_actions=1,
                        repeated_targets=0, default_actions=2, skipped_checks=0),
        
        HeartbeatMetrics(2, "03:00", actions_taken=7, unique_platforms=3,
                        research_queries=2, sources_fetched=1, reply_depth=0.7,
                        new_connections=1, threads_entered=3, build_actions=1,
                        repeated_targets=1, default_actions=2, skipped_checks=1),
        
        HeartbeatMetrics(3, "05:00", actions_taken=6, unique_platforms=2,
                        research_queries=1, sources_fetched=1, reply_depth=0.5,
                        new_connections=0, threads_entered=2, build_actions=0,
                        repeated_targets=2, default_actions=3, skipped_checks=2),
        
        HeartbeatMetrics(4, "07:00", actions_taken=4, unique_platforms=1,
                        research_queries=0, sources_fetched=0, reply_depth=0.3,
                        new_connections=0, threads_entered=1, build_actions=0,
                        repeated_targets=1, default_actions=3, skipped_checks=3),
        
        # Recovery beat — platform rotation + build focus
        HeartbeatMetrics(5, "09:00", actions_taken=5, unique_platforms=3,
                        research_queries=2, sources_fetched=2, reply_depth=0.7,
                        new_connections=1, threads_entered=3, build_actions=1,
                        repeated_targets=0, default_actions=1, skipped_checks=0),
    ]
    
    print("=" * 65)
    print("DECISION FATIGUE DETECTOR — Heartbeat Quality Monitor")
    print("Based on Grignoli et al 2025 (PMC11808891)")
    print("=" * 65)
    
    history = []
    for beat in beats:
        result = compute_fatigue_score(beat)
        history.append(result)
        
        print(f"\n{'─' * 55}")
        print(f"Beat #{beat.beat_number} ({beat.timestamp_utc} UTC) | Grade: {result['grade']} | Fatigue: {result['composite_fatigue']}")
        print(f"  Markers: {json.dumps(result['markers'])}")
        print(f"  {result['interpretation']}")
        
        # Check circular causality
        warning = detect_circular_causality(history)
        if warning:
            print(f"  {warning}")
    
    # Summary
    print(f"\n{'=' * 65}")
    print("SESSION SUMMARY")
    scores = [h["composite_fatigue"] for h in history]
    print(f"  Fatigue trajectory: {' → '.join(f'{s:.2f}' for s in scores)}")
    print(f"  Peak fatigue: {max(scores):.2f} (beat #{scores.index(max(scores))+1})")
    print(f"  Recovery: {'Yes' if scores[-1] < scores[-2] else 'No'}")
    print(f"\nGrignoli's insight: 'negative circular causality — those who")
    print(f"struggle with DM experience increased distress, further")
    print(f"difficulty in making decisions.' Break the loop early.")
    print(f"\nContrast: Nature 2025 found NO decision fatigue in healthcare")
    print(f"field data — sequential position effects may be environmental.")
    print(f"Track both hypotheses. Environment matters.")
    print("=" * 65)


if __name__ == "__main__":
    demo()
