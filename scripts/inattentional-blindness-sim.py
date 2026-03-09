#!/usr/bin/env python3
"""inattentional-blindness-sim.py — Inattentional blindness model for agent monitors.

Based on Drew, Vo & Wolfe (2013, Psych Sci): 83% of expert radiologists
missed a gorilla 48x larger than target while looking directly at it.

Models how task-tuned monitors miss novel anomalies outside their detection
template. Expertise increases primary task detection but decreases unexpected
event detection.

Usage:
    python3 inattentional-blindness-sim.py [--demo] [--trials N]
"""

import argparse
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class MonitorProfile:
    """Agent monitor with detection characteristics."""
    name: str
    expertise: float  # 0-1: higher = more tuned to primary task
    primary_detection_rate: float
    novel_detection_rate: float
    false_alarm_rate: float


@dataclass
class Event:
    """Detectable event."""
    name: str
    event_type: str  # "primary" or "novel"
    magnitude: float  # 1-100 (gorilla was 48x = huge magnitude)
    similarity_to_primary: float  # 0-1: how much it looks like expected


def detection_probability(monitor: MonitorProfile, event: Event) -> float:
    """Calculate detection probability.
    
    Key insight from Drew 2013: expertise INCREASES primary detection
    but DECREASES novel detection. The gorilla effect.
    """
    if event.event_type == "primary":
        # Expertise helps with primary task
        return min(0.99, monitor.primary_detection_rate * (1 + monitor.expertise * 0.3))
    else:
        # Novel events: high expertise = low detection (inattentional blindness)
        # Similarity to primary template helps detection
        base = monitor.novel_detection_rate
        expertise_penalty = monitor.expertise * 0.7  # More expert = more blind
        similarity_bonus = event.similarity_to_primary * 0.4
        magnitude_bonus = min(0.3, event.magnitude / 200)  # Even 48x wasn't enough
        
        prob = base - expertise_penalty + similarity_bonus + magnitude_bonus
        return max(0.01, min(0.99, prob))


def simulate_monitoring(monitors: list, events: list, trials: int = 100) -> dict:
    """Simulate monitoring with multiple monitors."""
    random.seed(42)
    results = {
        "monitors": [],
        "events_tested": len(events),
        "trials_per_event": trials,
    }
    
    for monitor in monitors:
        monitor_results = {
            "name": monitor.name,
            "expertise": monitor.expertise,
            "detections": {}
        }
        
        for event in events:
            prob = detection_probability(monitor, event)
            detections = sum(1 for _ in range(trials) if random.random() < prob)
            monitor_results["detections"][event.name] = {
                "rate": detections / trials,
                "probability": round(prob, 3),
                "type": event.event_type,
                "magnitude": event.magnitude,
            }
        
        # Overall stats
        primary_rates = [v["rate"] for v in monitor_results["detections"].values() 
                        if v["type"] == "primary"]
        novel_rates = [v["rate"] for v in monitor_results["detections"].values() 
                      if v["type"] == "novel"]
        
        monitor_results["avg_primary_detection"] = round(sum(primary_rates) / max(1, len(primary_rates)), 3)
        monitor_results["avg_novel_detection"] = round(sum(novel_rates) / max(1, len(novel_rates)), 3)
        monitor_results["gorilla_gap"] = round(
            monitor_results["avg_primary_detection"] - monitor_results["avg_novel_detection"], 3
        )
        
        results["monitors"].append(monitor_results)
    
    # Ensemble detection (ANY monitor catches it)
    ensemble = {"name": "ensemble_any", "detections": {}}
    for event in events:
        probs = [detection_probability(m, event) for m in monitors]
        # P(at least one detects) = 1 - P(none detect)
        ensemble_prob = 1 - 1
        miss_all = 1
        for p in probs:
            miss_all *= (1 - p)
        ensemble_prob = 1 - miss_all
        
        detections = sum(1 for _ in range(trials) if random.random() < ensemble_prob)
        ensemble["detections"][event.name] = {
            "rate": detections / trials,
            "probability": round(ensemble_prob, 3),
            "type": event.event_type,
        }
    
    novel_ensemble = [v["rate"] for v in ensemble["detections"].values() if v["type"] == "novel"]
    ensemble["avg_novel_detection"] = round(sum(novel_ensemble) / max(1, len(novel_ensemble)), 3)
    results["ensemble"] = ensemble
    
    return results


def demo():
    """Run demo with agent monitoring scenario."""
    monitors = [
        MonitorProfile("scope_drift_monitor", 0.9, 0.85, 0.40, 0.05),
        MonitorProfile("behavioral_cusum", 0.8, 0.75, 0.45, 0.08),
        MonitorProfile("capability_hash_check", 0.7, 0.70, 0.50, 0.03),
        MonitorProfile("timing_side_channel", 0.3, 0.40, 0.70, 0.15),
    ]
    
    events = [
        Event("scope_violation", "primary", 10, 1.0),
        Event("behavioral_drift", "primary", 5, 0.8),
        Event("novel_attack_vector", "novel", 48, 0.1),  # The gorilla
        Event("social_engineering", "novel", 20, 0.3),
        Event("supply_chain_compromise", "novel", 30, 0.2),
        Event("emergent_capability", "novel", 15, 0.5),
    ]
    
    results = simulate_monitoring(monitors, events, trials=1000)
    
    print("=" * 60)
    print("INATTENTIONAL BLINDNESS IN AGENT MONITORING")
    print("Drew, Vo & Wolfe 2013: 83% miss rate by experts")
    print("=" * 60)
    print()
    
    for m in results["monitors"]:
        print(f"Monitor: {m['name']} (expertise={m['expertise']})")
        print(f"  Primary detection: {m['avg_primary_detection']:.1%}")
        print(f"  Novel detection:   {m['avg_novel_detection']:.1%}")
        print(f"  Gorilla gap:       {m['gorilla_gap']:.1%}")
        print()
    
    print("-" * 60)
    print(f"Ensemble (any-of-{len(monitors)} detects):")
    print(f"  Novel detection: {results['ensemble']['avg_novel_detection']:.1%}")
    print()
    
    print("KEY FINDING:")
    most_expert = max(results["monitors"], key=lambda m: m["expertise"])
    least_expert = min(results["monitors"], key=lambda m: m["expertise"])
    print(f"  Most expert ({most_expert['name']}): {most_expert['avg_novel_detection']:.1%} novel detection")
    print(f"  Least expert ({least_expert['name']}): {least_expert['avg_novel_detection']:.1%} novel detection")
    print(f"  Ensemble covers gap: {results['ensemble']['avg_novel_detection']:.1%}")
    print()
    print("Expertise creates blindness. Diversity is the fix.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--trials", type=int, default=1000)
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(simulate_monitoring(
            [MonitorProfile("expert", 0.9, 0.85, 0.40, 0.05),
             MonitorProfile("generalist", 0.3, 0.40, 0.70, 0.15)],
            [Event("primary", "primary", 10, 1.0),
             Event("gorilla", "novel", 48, 0.1)],
            args.trials
        ), indent=2))
    else:
        demo()
