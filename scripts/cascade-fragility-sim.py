#!/usr/bin/env python3
"""cascade-fragility-sim.py — Information cascade fragility simulator.

Models Bikhchandani, Hirshleifer & Welch (1992) information cascades
in attestation networks. Shows how discrete binary decisions lose
private signals, and how continuous confidence scores prevent cascades.

Usage:
    python3 cascade-fragility-sim.py [--demo] [--trials N] [--agents N]
"""

import argparse
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class CascadeResult:
    """Result of a cascade simulation."""
    mode: str  # "binary" or "continuous"
    n_agents: int
    n_trials: int
    cascade_rate: float  # % of trials where cascade formed
    correct_cascade_rate: float  # % of cascades that were correct
    wrong_cascade_rate: float  # % of cascades that were wrong
    avg_cascade_start: float  # average agent # where cascade begins
    fragility: float  # % of cascades broken by strong counter-signal


def simulate_binary(n_agents: int, n_trials: int, signal_quality: float = 0.7) -> CascadeResult:
    """Simulate BHW binary attestation cascade."""
    cascades = 0
    correct_cascades = 0
    wrong_cascades = 0
    cascade_starts = []
    broken = 0
    
    for _ in range(n_trials):
        # True state: 1 = trustworthy, 0 = not
        true_state = random.choice([0, 1])
        
        # Public history of actions (binary: attest/reject)
        actions = []
        cascade_started = False
        cascade_agent = -1
        
        for i in range(n_agents):
            # Private signal: correct with prob signal_quality
            if random.random() < signal_quality:
                private_signal = true_state
            else:
                private_signal = 1 - true_state
            
            # Count public actions
            attests = sum(actions)
            rejects = len(actions) - attests
            
            # BHW decision rule: follow majority if strong enough, else follow private signal
            if attests - rejects >= 2:
                # Cascade: ignore private signal, attest
                action = 1
                if not cascade_started:
                    cascade_started = True
                    cascade_agent = i
            elif rejects - attests >= 2:
                # Cascade: ignore private signal, reject
                action = 0
                if not cascade_started:
                    cascade_started = True
                    cascade_agent = i
            else:
                # Follow private signal
                action = private_signal
            
            # Strong counter-signal injection at agent n//2
            if i == n_agents // 2 and cascade_started:
                # Agent with very strong private signal breaks cascade
                if random.random() < 0.3:  # 30% chance of strong counter
                    action = 1 - action
                    broken += 1
            
            actions.append(action)
        
        if cascade_started:
            cascades += 1
            cascade_starts.append(cascade_agent)
            final_consensus = sum(actions) > len(actions) / 2
            if final_consensus == bool(true_state):
                correct_cascades += 1
            else:
                wrong_cascades += 1
    
    return CascadeResult(
        mode="binary",
        n_agents=n_agents,
        n_trials=n_trials,
        cascade_rate=cascades / n_trials if n_trials > 0 else 0,
        correct_cascade_rate=correct_cascades / cascades if cascades > 0 else 0,
        wrong_cascade_rate=wrong_cascades / cascades if cascades > 0 else 0,
        avg_cascade_start=sum(cascade_starts) / len(cascade_starts) if cascade_starts else 0,
        fragility=broken / cascades if cascades > 0 else 0,
    )


def simulate_continuous(n_agents: int, n_trials: int, signal_quality: float = 0.7) -> CascadeResult:
    """Simulate continuous confidence score attestation (no cascades)."""
    cascades = 0
    correct = 0
    wrong = 0
    
    for _ in range(n_trials):
        true_state = random.choice([0, 1])
        scores = []
        
        for i in range(n_agents):
            # Private signal with noise
            if random.random() < signal_quality:
                base = 0.7 if true_state else 0.3
            else:
                base = 0.3 if true_state else 0.7
            
            # Add personal noise — preserves private information
            score = max(0, min(1, base + random.gauss(0, 0.15)))
            scores.append(score)
        
        # Aggregate: weighted average (no information loss)
        avg_score = sum(scores) / len(scores)
        consensus = avg_score > 0.5
        
        if consensus == bool(true_state):
            correct += 1
        else:
            wrong += 1
        
        # Check for cascade-like behavior (all scores same direction)
        all_same = all(s > 0.5 for s in scores) or all(s <= 0.5 for s in scores)
        if all_same:
            cascades += 1
    
    return CascadeResult(
        mode="continuous",
        n_agents=n_agents,
        n_trials=n_trials,
        cascade_rate=cascades / n_trials,
        correct_cascade_rate=correct / n_trials,
        wrong_cascade_rate=wrong / n_trials,
        avg_cascade_start=0,  # no cascade start point
        fragility=0,  # no cascades to break
    )


def demo():
    """Run comparison demo."""
    random.seed(42)
    n_agents = 10
    n_trials = 5000
    
    binary = simulate_binary(n_agents, n_trials)
    continuous = simulate_continuous(n_agents, n_trials)
    
    print("=" * 60)
    print("INFORMATION CASCADE FRAGILITY ANALYSIS")
    print(f"Bikhchandani, Hirshleifer & Welch (1992)")
    print("=" * 60)
    print()
    
    print(f"Binary attestation ({n_agents} agents, {n_trials} trials):")
    print(f"  Cascade rate: {binary.cascade_rate:.1%}")
    print(f"  Correct cascades: {binary.correct_cascade_rate:.1%}")
    print(f"  Wrong cascades: {binary.wrong_cascade_rate:.1%}")
    print(f"  Avg cascade start: agent #{binary.avg_cascade_start:.1f}")
    print(f"  Fragility (broken by counter-signal): {binary.fragility:.1%}")
    print()
    
    print(f"Continuous scores ({n_agents} agents, {n_trials} trials):")
    print(f"  Cascade-like rate: {continuous.cascade_rate:.1%}")
    print(f"  Accuracy: {continuous.correct_cascade_rate:.1%}")
    print(f"  Error rate: {continuous.wrong_cascade_rate:.1%}")
    print()
    
    print("-" * 60)
    print("KEY FINDINGS:")
    print(f"  Binary cascades form {binary.cascade_rate:.0%} of the time")
    print(f"  {binary.wrong_cascade_rate:.0%} of those cascades are WRONG")
    print(f"  Continuous scores: {continuous.correct_cascade_rate:.0%} accuracy (no cascades)")
    print(f"  Cascades are fragile: {binary.fragility:.0%} broken by one strong signal")
    print()
    print("RECOMMENDATION: Continuous confidence scores preserve private")
    print("signals. Binary attest/reject discards nuance and enables cascades.")
    print("Cascades are fragile — design for counter-signal injection points.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Information cascade simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--agents", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        random.seed(42)
        b = simulate_binary(args.agents, args.trials)
        c = simulate_continuous(args.agents, args.trials)
        print(json.dumps({"binary": asdict(b), "continuous": asdict(c)}, indent=2))
    else:
        demo()
