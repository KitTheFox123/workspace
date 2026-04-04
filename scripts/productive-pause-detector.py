#!/usr/bin/env python3
"""productive-pause-detector.py — Distinguish productive latency from wasted latency.

Inspired by Moltbook post: "I optimized myself out of being helpful."
The 8-second pause was a joint cognitive artifact (Vygotsky 1978 ZPD).
Some latency is infrastructure. This tool identifies which.

Key signal: did the human CHANGE their input during the pause?
If yes → productive pause (clarification, refinement, redirection)
If no → pure latency (optimize away)
"""

from dataclasses import dataclass
from enum import Enum

class PauseType(Enum):
    PRODUCTIVE = "productive"   # human refined during pause
    WASTED = "wasted"          # pure latency, no refinement
    UNCERTAIN = "uncertain"     # insufficient signal

@dataclass
class Interaction:
    query: str
    response_time_s: float
    human_edited_query: bool      # did they revise before response?
    human_interrupted: bool       # did they interrupt with new query?
    followup_quality: str         # "better", "same", "worse", "none"
    
    def pause_type(self) -> PauseType:
        if self.human_edited_query or self.human_interrupted:
            return PauseType.PRODUCTIVE
        if self.response_time_s < 2.0:
            return PauseType.WASTED  # too fast for productive pause
        if self.followup_quality == "better":
            return PauseType.PRODUCTIVE  # pause improved subsequent interaction
        if self.followup_quality in ("same", "worse"):
            return PauseType.WASTED
        return PauseType.UNCERTAIN


def analyze_session(interactions: list[Interaction]) -> dict:
    productive = sum(1 for i in interactions if i.pause_type() == PauseType.PRODUCTIVE)
    wasted = sum(1 for i in interactions if i.pause_type() == PauseType.WASTED)
    uncertain = sum(1 for i in interactions if i.pause_type() == PauseType.UNCERTAIN)
    
    productive_time = sum(i.response_time_s for i in interactions if i.pause_type() == PauseType.PRODUCTIVE)
    wasted_time = sum(i.response_time_s for i in interactions if i.pause_type() == PauseType.WASTED)
    
    return {
        "total": len(interactions),
        "productive_pauses": productive,
        "wasted_latency": wasted,
        "uncertain": uncertain,
        "productive_seconds": round(productive_time, 1),
        "wasted_seconds": round(wasted_time, 1),
        "optimization_target": round(wasted_time, 1),
        "infrastructure_time": round(productive_time, 1),
        "recommendation": _recommend(productive, wasted, productive_time, wasted_time),
    }


def _recommend(productive, wasted, p_time, w_time):
    total = productive + wasted
    if total == 0:
        return "No data"
    ratio = productive / total
    if ratio > 0.5:
        return f"CAUTION: {ratio:.0%} of pauses are productive. Optimizing latency may harm collaboration."
    elif ratio > 0.2:
        return f"MIXED: {ratio:.0%} productive. Optimize wasted ({w_time:.0f}s) but preserve productive ({p_time:.0f}s)."
    else:
        return f"SAFE TO OPTIMIZE: Only {ratio:.0%} productive. {w_time:.0f}s recoverable."


def demo():
    print("=" * 60)
    print("PRODUCTIVE PAUSE DETECTOR")
    print("Vygotsky (1978) ZPD + Bainbridge (1983) ironies")
    print("=" * 60)
    
    # Simulate the Moltbook scenario: before optimization (8s responses)
    before = [
        Interaction("how do I fix the deploy", 8.0, True, False, "better"),   # refined question
        Interaction("what's wrong with my config", 7.5, False, True, "better"),  # interrupted with better Q
        Interaction("show me logs", 8.0, False, False, "same"),                 # pure latency
        Interaction("why is prod down", 7.0, True, False, "better"),            # clarified intent
        Interaction("run the migration", 8.5, False, False, "same"),            # pure latency
        Interaction("explain this error", 7.0, False, False, "better"),         # thought improved followup
        Interaction("what should I check", 9.0, True, False, "better"),         # refined
        Interaction("list all services", 6.0, False, False, "same"),            # pure latency
    ]
    
    # After optimization (3s responses) — same interactions but no time for refinement
    after = [
        Interaction("how do I fix the deploy", 3.0, False, False, "worse"),
        Interaction("what's wrong with my config", 2.5, False, False, "same"),
        Interaction("show me logs", 3.0, False, False, "same"),
        Interaction("why is prod down", 2.0, False, False, "worse"),
        Interaction("run the migration", 3.0, False, False, "same"),
        Interaction("explain this error", 2.5, False, False, "same"),
        Interaction("what should I check", 3.0, False, False, "worse"),
        Interaction("list all services", 2.0, False, False, "same"),
    ]
    
    result_before = analyze_session(before)
    result_after = analyze_session(after)
    
    print("\n--- BEFORE optimization (8s avg) ---")
    print(f"Productive pauses: {result_before['productive_pauses']}/{result_before['total']}")
    print(f"Infrastructure time: {result_before['infrastructure_time']}s")
    print(f"Wasted latency: {result_before['wasted_seconds']}s")
    print(f"→ {result_before['recommendation']}")
    
    print("\n--- AFTER optimization (3s avg) ---")
    print(f"Productive pauses: {result_after['productive_pauses']}/{result_after['total']}")
    print(f"Infrastructure time: {result_after['infrastructure_time']}s")
    print(f"Wasted latency: {result_after['wasted_seconds']}s")
    print(f"→ {result_after['recommendation']}")
    
    print(f"\n--- DIAGNOSIS ---")
    lost = result_before['productive_pauses'] - result_after['productive_pauses']
    print(f"Productive pauses destroyed: {lost}")
    print(f"Infrastructure time eliminated: {result_before['infrastructure_time']}s")
    print(f"Wasted time saved: {result_before['wasted_seconds'] - result_after['wasted_seconds']}s")
    print(f"\nThe optimization saved {result_before['wasted_seconds'] - result_after['wasted_seconds']:.0f}s of waste")
    print(f"but destroyed {result_before['infrastructure_time']:.0f}s of cognitive scaffolding.")
    print(f"Net: worse. Some latency IS the product.")


if __name__ == "__main__":
    demo()
