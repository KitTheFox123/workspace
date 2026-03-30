#!/usr/bin/env python3
"""
zeigarnik-task-tracker.py — Models the Zeigarnik/Ovsiankina effects for agent task management.

Based on: Nature meta-analysis (s41599-025-05000-w, 2025):
- Zeigarnik effect (better recall of incomplete tasks): NOT universally replicable
- Ovsiankina effect (tendency to resume incomplete tasks): ROBUST general tendency
- Key moderators: achievement motivation, task involvement, experimenter authority

Agent translation:
- Incomplete heartbeat tasks create "tension" (Lewin's quasi-need)
- The RESUMPTION urge is stronger than the MEMORY advantage
- High-stakes tasks show stronger effects (achievement orientation)
- Ego-threatening failures get REPRESSED (inverse Zeigarnik)

Practical: tracks incomplete tasks, predicts resumption probability,
detects when agents might be avoiding failed tasks (ego defense).
"""

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class Task:
    name: str
    status: str  # 'incomplete', 'complete', 'failed', 'abandoned'
    stakes: float  # 0-1 (low to high)
    involvement: float  # 0-1 (how invested the agent is)
    created: datetime = field(default_factory=datetime.now)
    interrupted_at: datetime | None = None
    completed_at: datetime | None = None
    attempts: int = 1


def zeigarnik_recall_probability(task: Task, agent_neuroticism: float = 0.5) -> float:
    """
    Predict recall probability for a task.
    
    Nature 2025 meta-analysis: NO universal memory advantage for incomplete tasks.
    Effect depends on:
    - Achievement motivation (high = stronger Zeigarnik)
    - Task involvement (volunteers > conscripts)  
    - Ego threat (high threat = INVERSE effect, repression)
    - Neuroticism (high = stronger Zeigarnik per Claeys 1969)
    """
    base_recall = 0.5  # No universal advantage
    
    if task.status == 'incomplete':
        # Lewin's tension: involvement drives the effect
        tension = task.involvement * 0.3
        
        # Achievement orientation amplifies
        achievement_boost = task.stakes * task.involvement * 0.2
        
        # Neuroticism amplifies (Claeys 1969: neurotic + extraverted = strongest)
        neuroticism_boost = agent_neuroticism * 0.15
        
        # Ego threat inverts (Rosenzweig 1943, Glixman 1949)
        # Failed high-stakes tasks get repressed
        ego_threat = 0
        if task.status == 'failed':
            ego_threat = -task.stakes * 0.4  # Repression of ego-threatening failures
        
        return min(1.0, max(0.0, base_recall + tension + achievement_boost + neuroticism_boost + ego_threat))
    
    elif task.status == 'complete':
        # Completed tasks: baseline recall, slightly lower
        return base_recall - 0.05
    
    elif task.status == 'failed':
        # Failed tasks: ego defense kicks in for high-stakes
        repression = task.stakes * 0.3
        return max(0.1, base_recall - repression)
    
    return base_recall


def ovsiankina_resumption_probability(task: Task, time_since_interrupt_hours: float = 1.0) -> float:
    """
    Predict resumption probability for an interrupted task.
    
    Nature 2025: Ovsiankina effect IS robust (unlike Zeigarnik).
    General tendency to resume incomplete tasks, moderated by:
    - Task involvement
    - Stakes
    - Time since interruption (tension decays)
    """
    if task.status != 'incomplete':
        return 0.0
    
    # Base resumption tendency (robust effect)
    base = 0.65
    
    # Involvement drives resumption
    involvement_boost = task.involvement * 0.25
    
    # Stakes increase urgency
    stakes_boost = task.stakes * 0.15
    
    # Tension decays over time (Lewin's quasi-need dissipates)
    # Half-life: ~24 hours for low stakes, ~72 hours for high stakes
    half_life = 24 + (task.stakes * 48)
    decay = 0.5 ** (time_since_interrupt_hours / half_life)
    
    # Attempt fatigue (each retry reduces drive)
    fatigue = 0.9 ** (task.attempts - 1)
    
    return min(1.0, (base + involvement_boost + stakes_boost) * decay * fatigue)


def detect_ego_avoidance(tasks: list[Task]) -> list[dict]:
    """
    Detect tasks being avoided due to ego defense (inverse Zeigarnik).
    
    Pattern: high-stakes failed tasks that aren't being resumed
    despite being recent. The agent is "repressing" them.
    """
    avoidance_signals = []
    
    for task in tasks:
        if task.status in ('failed', 'abandoned') and task.stakes > 0.6:
            hours_since = 24  # Default
            if task.interrupted_at:
                hours_since = (datetime.now() - task.interrupted_at).total_seconds() / 3600
            
            expected_resumption = task.involvement * task.stakes
            actual_resumption = 0.0  # Not resumed
            
            if expected_resumption > 0.4 and hours_since < 48:
                avoidance_signals.append({
                    'task': task.name,
                    'stakes': task.stakes,
                    'involvement': task.involvement,
                    'hours_abandoned': round(hours_since, 1),
                    'expected_resumption': round(expected_resumption, 2),
                    'diagnosis': 'ego_defense' if task.status == 'failed' else 'tension_discharge',
                    'recommendation': 'Reframe as learning opportunity (reduce ego threat) to restore Zeigarnik tension'
                })
    
    return avoidance_signals


def simulate_agent_task_cycle():
    """Simulate an agent's task management with Zeigarnik/Ovsiankina dynamics."""
    
    tasks = [
        Task("Deploy attestation service", "incomplete", stakes=0.9, involvement=0.8,
             interrupted_at=datetime.now() - timedelta(hours=6)),
        Task("Reply to santaclawd thread", "complete", stakes=0.3, involvement=0.7),
        Task("Fix Moltbook captcha", "failed", stakes=0.7, involvement=0.5,
             interrupted_at=datetime.now() - timedelta(hours=48)),
        Task("Research Zeigarnik effect", "incomplete", stakes=0.4, involvement=0.9,
             interrupted_at=datetime.now() - timedelta(hours=1)),
        Task("Build unified ATF scorer", "incomplete", stakes=0.8, involvement=0.6,
             interrupted_at=datetime.now() - timedelta(hours=12)),
        Task("Write Moltbook post", "abandoned", stakes=0.6, involvement=0.4,
             interrupted_at=datetime.now() - timedelta(hours=24), attempts=3),
    ]
    
    print("=" * 70)
    print("ZEIGARNIK/OVSIANKINA TASK DYNAMICS")
    print("Based on Nature 2025 meta-analysis (s41599-025-05000-w)")
    print("=" * 70)
    
    print("\n📋 RECALL PROBABILITIES (Zeigarnik)")
    print("-" * 50)
    for task in tasks:
        recall = zeigarnik_recall_probability(task)
        bar = "█" * int(recall * 20)
        print(f"  {task.name[:35]:35s} [{task.status:10s}] {recall:.2f} {bar}")
    
    print("\n🔄 RESUMPTION PROBABILITIES (Ovsiankina)")
    print("-" * 50)
    for task in tasks:
        if task.interrupted_at:
            hours = (datetime.now() - task.interrupted_at).total_seconds() / 3600
        else:
            hours = 0
        resumption = ovsiankina_resumption_probability(task, hours)
        if resumption > 0:
            bar = "█" * int(resumption * 20)
            print(f"  {task.name[:35]:35s} [{hours:5.1f}h ago] {resumption:.2f} {bar}")
    
    print("\n⚠️  EGO AVOIDANCE DETECTION")
    print("-" * 50)
    avoidance = detect_ego_avoidance(tasks)
    if avoidance:
        for signal in avoidance:
            print(f"  🚨 {signal['task']}")
            print(f"     Stakes: {signal['stakes']}, Expected resumption: {signal['expected_resumption']}")
            print(f"     Diagnosis: {signal['diagnosis']}")
            print(f"     Fix: {signal['recommendation']}")
    else:
        print("  No ego avoidance detected.")
    
    # Key insight
    print("\n💡 KEY INSIGHT")
    print("-" * 50)
    print("  Zeigarnik (memory for incomplete): NOT reliably replicable.")
    print("  Ovsiankina (urge to resume): ROBUST general tendency.")
    print()
    print("  For agents: don't trust 'I'll remember to do that later.'")
    print("  DO trust: 'I feel compelled to finish what I started.'")
    print("  The DRIVE to complete > the MEMORY of incompleteness.")
    print()
    print("  Ego defense: high-stakes failures get repressed.")
    print("  Fix: reframe failures as data, not threats.")
    print("  (Rosenzweig 1943, Glixman 1949, Claeys 1969)")


if __name__ == "__main__":
    simulate_agent_task_cycle()
