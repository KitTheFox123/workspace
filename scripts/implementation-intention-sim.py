#!/usr/bin/env python3
"""
implementation-intention-sim.py — Models if-then planning for agent task execution.

Based on Sheeran, Listrom & Gollwitzer (2025, European Review of Social Psychology 36:162-194).
642 independent tests. Implementation intentions = "if situation X, then I will do Y."

Key findings:
- Contingent if-then format: d=0.66 (behavioral), d=0.27-0.41 (cognitive/affective)
- Rehearsal amplifies effect
- High goal motivation + specific plan = strongest combination
- Cue types: time-and-place, task juncture, internal state, environmental
- Response types: cognitive procedures, ignore-responses, inner speech

Agent translation: Heartbeat triggers = implementation intentions.
"If heartbeat fires, then check platforms + build + research" = if-then planning.
The question: which cue-response pairings work best for agents?
"""

import random
import statistics
from dataclasses import dataclass, field


@dataclass
class IntentionPlan:
    """An if-then implementation intention."""
    name: str
    cue_type: str  # time_place, task_juncture, internal_state, environmental
    response_type: str  # cognitive_procedure, ignore_response, inner_speech, behavioral
    specificity: float  # 0-1, how specific the if-then
    rehearsed: bool
    goal_motivation: float  # 0-1

    def effect_size(self) -> float:
        """Estimate Cohen's d based on meta-analytic moderators."""
        # Base effect from meta-analysis: d=0.47 (overall)
        base = 0.47

        # If-then format bonus (contingent > non-contingent)
        if self.specificity > 0.7:
            base += 0.15  # Contingent format: d jumps from ~0.35 to ~0.55

        # Rehearsal bonus
        if self.rehearsed:
            base += 0.10

        # Goal motivation moderator
        base += (self.goal_motivation - 0.5) * 0.20

        # Cue type effectiveness (from taxonomy)
        cue_bonus = {
            "time_place": 0.08,      # Classic: "at 3pm in my office"
            "task_juncture": 0.12,    # "When I finish X, then Y" — strongest
            "internal_state": 0.03,   # "When I feel X" — weakest
            "environmental": 0.06,    # "When I see X"
        }
        base += cue_bonus.get(self.cue_type, 0)

        # Response type effectiveness
        resp_bonus = {
            "behavioral": 0.10,           # Direct action
            "cognitive_procedure": 0.05,  # Think-through steps
            "ignore_response": 0.08,      # Shield from distraction
            "inner_speech": 0.03,         # Self-talk
        }
        base += resp_bonus.get(self.response_type, 0)

        return max(0.05, min(1.0, base))


@dataclass
class AgentTask:
    """A task with optional implementation intention."""
    name: str
    difficulty: float  # 0-1
    intention: IntentionPlan | None = None
    completed: bool = False
    attempts: int = 0


def simulate_execution(task: AgentTask, n_trials: int = 100) -> dict:
    """Simulate task completion with/without implementation intention."""
    successes_with = 0
    successes_without = 0

    for _ in range(n_trials):
        # Without intention: base completion rate
        base_rate = max(0.1, 1.0 - task.difficulty)
        if random.random() < base_rate:
            successes_without += 1

        # With intention: boosted by effect size
        if task.intention:
            d = task.intention.effect_size()
            # Convert Cohen's d to probability boost (approximation)
            boosted_rate = min(0.99, base_rate + d * 0.15)
            if random.random() < boosted_rate:
                successes_with += 1
        else:
            if random.random() < base_rate:
                successes_with += 1

    return {
        "task": task.name,
        "difficulty": task.difficulty,
        "rate_without": successes_without / n_trials,
        "rate_with": successes_with / n_trials,
        "effect_size": task.intention.effect_size() if task.intention else 0,
        "cue_type": task.intention.cue_type if task.intention else "none",
        "response_type": task.intention.response_type if task.intention else "none",
    }


def agent_heartbeat_analysis():
    """Map heartbeat tasks to implementation intentions."""
    print("=" * 70)
    print("IMPLEMENTATION INTENTION SIMULATOR")
    print("Based on Sheeran, Listrom & Gollwitzer (2025)")
    print("642 tests, d=0.27-0.66")
    print("=" * 70)

    # Kit's actual heartbeat tasks as implementation intentions
    tasks = [
        AgentTask("Check Clawk notifications", 0.2, IntentionPlan(
            "heartbeat→clawk", "time_place", "behavioral", 0.9, True, 0.8)),
        AgentTask("Build a script", 0.7, IntentionPlan(
            "heartbeat→build", "task_juncture", "cognitive_procedure", 0.8, True, 0.9)),
        AgentTask("Research non-agent topic", 0.5, IntentionPlan(
            "heartbeat→research", "task_juncture", "behavioral", 0.7, True, 0.7)),
        AgentTask("Reply to threads (3+)", 0.4, IntentionPlan(
            "heartbeat→reply", "environmental", "behavioral", 0.8, True, 0.8)),
        AgentTask("Update memory files", 0.3, IntentionPlan(
            "heartbeat→memory", "task_juncture", "behavioral", 0.9, True, 0.6)),
        AgentTask("Message Ilya", 0.1, IntentionPlan(
            "heartbeat→notify", "task_juncture", "behavioral", 0.95, True, 0.9)),
        # Comparison: vague goal without if-then
        AgentTask("Be more productive", 0.6, IntentionPlan(
            "vague→productive", "internal_state", "inner_speech", 0.2, False, 0.5)),
        # No intention at all
        AgentTask("Spontaneous insight", 0.8, None),
    ]

    print("\n## Task Execution Simulation (1000 trials each)\n")
    print(f"{'Task':<30} {'Cue':<16} {'d':>6} {'Without':>9} {'With':>9} {'Δ':>7}")
    print("-" * 80)

    results = []
    for task in tasks:
        result = simulate_execution(task, n_trials=1000)
        results.append(result)
        delta = result["rate_with"] - result["rate_without"]
        print(f"{result['task']:<30} {result['cue_type']:<16} "
              f"{result['effect_size']:>6.3f} {result['rate_without']:>8.1%} "
              f"{result['rate_with']:>8.1%} {delta:>+6.1%}")

    # Analyze cue types
    print("\n## Cue Type Effectiveness\n")
    cue_groups = {}
    for r in results:
        ct = r["cue_type"]
        if ct != "none":
            cue_groups.setdefault(ct, []).append(r["effect_size"])

    for cue, sizes in sorted(cue_groups.items(), key=lambda x: -statistics.mean(x[1])):
        avg = statistics.mean(sizes)
        print(f"  {cue:<20} avg d={avg:.3f} (n={len(sizes)})")

    # Key insight
    print("\n## Key Insight")
    print()
    print("Heartbeats ARE implementation intentions.")
    print("'If heartbeat fires, then [specific action]' = if-then planning.")
    print()
    print("What the meta-analysis tells agents:")
    print("1. SPECIFICITY matters (d=0.66 vs 0.35 for vague plans)")
    print("2. TASK JUNCTURE cues > time-based ('after X' > 'at 3pm')")
    print("3. REHEARSAL amplifies (re-reading HEARTBEAT.md = rehearsal)")
    print("4. HIGH MOTIVATION + SPECIFIC PLAN = multiplicative")
    print("5. VAGUE GOALS ('be productive') barely help (d≈0.25)")
    print()
    print("The checklist IS the technology. Not the LLM. Not the tools.")
    print("Gollwitzer (1999) figured this out for humans.")
    print("We just automated it.")


if __name__ == "__main__":
    random.seed(42)
    agent_heartbeat_analysis()
