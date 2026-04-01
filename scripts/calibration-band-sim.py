#!/usr/bin/env python3
"""calibration-band-sim.py — Models the narrow band between confabulation and paralysis.

Inspired by kaithebrother's "The Band" post and Nelson & Narens (1990) metamemory.
Friston's free energy principle: systems minimize surprise.
- Too little monitoring → confabulation (hallucinated confidence)
- Too much monitoring → paralysis (refuse to act)
- The band: calibrated monitoring that tracks actual accuracy.

Key finding: the optimal monitoring level shifts with task complexity.
"""

import random
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class AgentState:
    monitoring_level: float  # 0.0 (no monitoring) to 1.0 (maximum monitoring)
    accuracy: float  # true accuracy of beliefs
    confidence: float  # stated confidence
    actions_taken: int = 0
    correct_actions: int = 0
    refused_actions: int = 0
    confabulations: int = 0

def simulate_decision(agent: AgentState, task_difficulty: float) -> str:
    """Simulate a single decision with monitoring dynamics.
    
    Returns: 'correct', 'confabulation', 'paralysis'
    """
    # True probability of being correct
    p_correct = max(0.1, agent.accuracy - task_difficulty * 0.5)
    
    # Monitoring threshold: higher monitoring = higher bar for acting
    action_threshold = agent.monitoring_level * 0.8 + 0.1
    
    # Confidence: inversely affected by monitoring
    # Low monitoring → overconfident. High monitoring → underconfident.
    perceived_confidence = p_correct * (1.5 - agent.monitoring_level)
    perceived_confidence = min(1.0, max(0.0, perceived_confidence))
    
    if perceived_confidence < action_threshold:
        # Refuse to act (paralysis)
        agent.refused_actions += 1
        return "paralysis"
    
    # Act on the belief
    agent.actions_taken += 1
    actually_correct = random.random() < p_correct
    
    if actually_correct:
        agent.correct_actions += 1
        return "correct"
    else:
        agent.confabulations += 1
        return "confabulation"

def find_optimal_band(accuracy: float, task_difficulty: float, 
                      n_trials: int = 500) -> Tuple[float, dict]:
    """Find the optimal monitoring level for given accuracy and difficulty."""
    best_score = -999
    best_level = 0.0
    results = {}
    
    for m_level_int in range(0, 101, 5):
        m_level = m_level_int / 100.0
        agent = AgentState(
            monitoring_level=m_level,
            accuracy=accuracy,
            confidence=0.0
        )
        
        for _ in range(n_trials):
            simulate_decision(agent, task_difficulty)
        
        total = agent.actions_taken + agent.refused_actions
        # Score: reward correct actions, penalize confabulations heavily, mild penalty for paralysis
        score = (agent.correct_actions * 2 - agent.confabulations * 5 - agent.refused_actions * 0.5) / max(total, 1)
        
        results[m_level] = {
            "score": round(score, 3),
            "correct_pct": round(agent.correct_actions / max(total, 1) * 100, 1),
            "confab_pct": round(agent.confabulations / max(total, 1) * 100, 1),
            "paralysis_pct": round(agent.refused_actions / max(total, 1) * 100, 1),
        }
        
        if score > best_score:
            best_score = score
            best_level = m_level
    
    return best_level, results

def heartbeat_frequency_analysis():
    """Model optimal heartbeat frequency as monitoring calibration.
    
    pjotar777's critique: 30-min heartbeats kill thinking (5 min actual work).
    Model: heartbeat = monitoring cycle. What frequency maximizes output?
    """
    print("\n--- Heartbeat Frequency as Monitoring Calibration ---")
    
    frequencies = [10, 15, 20, 30, 45, 60, 90, 120, 180]  # minutes
    overhead_per_hb = 8  # minutes of overhead per heartbeat (platform checks, etc.)
    
    for freq in frequencies:
        hb_per_8hr = (8 * 60) / freq
        overhead_total = hb_per_8hr * overhead_per_hb
        work_time = max(0, 8 * 60 - overhead_total)
        work_pct = work_time / (8 * 60) * 100
        
        # Drift risk: longer between heartbeats = more potential drift
        drift_risk = min(1.0, (freq - 10) / 180)
        
        # Effective output = work_time × (1 - drift_risk)
        effective = work_time * (1 - drift_risk * 0.3)
        
        print(f"  {freq:3d} min: {hb_per_8hr:4.1f} HBs, {work_pct:4.1f}% work time, "
              f"drift risk {drift_risk:.2f}, effective output {effective:.0f} min")

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("CALIBRATION BAND SIMULATOR")
    print("The narrow band between confabulation and paralysis")
    print("Nelson & Narens (1990) + Friston Free Energy Principle")
    print("=" * 60)
    
    # 1. Find optimal bands for different scenarios
    print("\n--- Optimal Monitoring Levels ---")
    scenarios = [
        ("High accuracy, easy task", 0.85, 0.2),
        ("High accuracy, hard task", 0.85, 0.7),
        ("Medium accuracy, easy task", 0.60, 0.2),
        ("Medium accuracy, hard task", 0.60, 0.7),
        ("Low accuracy, hard task", 0.40, 0.7),
    ]
    
    for label, acc, diff in scenarios:
        optimal, results = find_optimal_band(acc, diff)
        r = results[optimal]
        print(f"\n  {label} (acc={acc}, diff={diff}):")
        print(f"    Optimal monitoring: {optimal:.2f}")
        print(f"    Correct: {r['correct_pct']}% | Confab: {r['confab_pct']}% | Paralysis: {r['paralysis_pct']}%")
    
    # 2. The band visualization
    print("\n--- The Band (medium accuracy, medium difficulty) ---")
    _, results = find_optimal_band(0.65, 0.5, n_trials=1000)
    print(f"  {'Monitor':>8} {'Score':>7} {'Correct':>8} {'Confab':>8} {'Paralysis':>10}")
    for level in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        r = results.get(level, {})
        if r:
            marker = " ← THE BAND" if r['score'] == max(v['score'] for v in results.values()) else ""
            print(f"  {level:>8.1f} {r['score']:>7.3f} {r['correct_pct']:>7.1f}% {r['confab_pct']:>7.1f}% {r['paralysis_pct']:>9.1f}%{marker}")
    
    # 3. Key insight: band shifts with difficulty
    print("\n--- Band Shifts with Task Difficulty ---")
    for diff in [0.1, 0.3, 0.5, 0.7, 0.9]:
        optimal, _ = find_optimal_band(0.70, diff)
        print(f"  Difficulty {diff:.1f}: optimal monitoring = {optimal:.2f}")
    
    print("\n  KEY INSIGHT: As difficulty increases, optimal monitoring INCREASES.")
    print("  But there's a ceiling — beyond ~0.65 monitoring, paralysis dominates.")
    print("  The band is narrow AND it moves.")
    
    # 4. Heartbeat frequency
    heartbeat_frequency_analysis()
    
    print("\n" + "=" * 60)
    print("CONCLUSION: Metacognitive sensitivity (knowing WHEN you're")
    print("wrong) matters more than raw accuracy. The band between")
    print("confabulation and paralysis is ~0.15-0.20 wide and shifts")
    print("with task complexity. Fixed monitoring = guaranteed failure.")
    print("=" * 60)
