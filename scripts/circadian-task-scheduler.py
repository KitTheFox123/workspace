#!/usr/bin/env python3
"""
circadian-task-scheduler.py — Schedule agent tasks by cognitive demand profile

Based on:
- Wiłkość-Dębczyńska 2023 (PMC10683050): chronotype-synchrony effect
- May 1999: implicit memory BETTER at non-optimal times
- Kleitman: body temp rhythm → psychomotor speed peaks late afternoon

Key insight: agents don't have circadian rhythms, but their OPERATORS do.
Schedule high-attention tasks for operator's peak times.
Schedule creative/exploratory tasks for off-peak (implicit memory advantage).

Also: agent-internal "circadian" = token budget cycles. Heavy research
burns budget; schedule it when ROI is highest.
"""

import json
from dataclasses import dataclass, field
from enum import Enum

class CognitiveLoad(Enum):
    HIGH = "high"      # attestation review, security audit, code review
    MEDIUM = "medium"  # posting, replying, engagement
    LOW = "low"        # likes, swipes, routine checks
    CREATIVE = "creative"  # research, writing, brainstorming

class TimeSlot(Enum):
    EARLY = "early"     # 00-06 UTC
    MORNING = "morning" # 06-12 UTC
    AFTERNOON = "afternoon"  # 12-18 UTC
    EVENING = "evening"  # 18-24 UTC

@dataclass
class Task:
    name: str
    load: CognitiveLoad
    platform: str = ""
    estimated_tokens: int = 0
    priority: int = 5  # 1-10

@dataclass
class CircadianScheduler:
    """Map tasks to time slots based on cognitive demand"""
    
    # Operator chronotype affects when supervision is available
    operator_peak: TimeSlot = TimeSlot.AFTERNOON  # most humans peak afternoon
    
    # Token budget per slot (proxy for agent "energy")
    slot_budgets: dict = field(default_factory=lambda: {
        TimeSlot.EARLY: 5000,
        TimeSlot.MORNING: 15000,
        TimeSlot.AFTERNOON: 20000,
        TimeSlot.EVENING: 10000,
    })

    def optimal_slot(self, task: Task) -> TimeSlot:
        """
        Schedule based on cognitive load + chronotype research:
        - HIGH: operator peak (needs supervision)
        - MEDIUM: morning/afternoon (good general performance)
        - LOW: any time (minimal cognitive demand)
        - CREATIVE: off-peak! (May 1999: implicit memory advantage)
        """
        if task.load == CognitiveLoad.HIGH:
            return self.operator_peak
        elif task.load == CognitiveLoad.CREATIVE:
            # Counter-intuitive: creative tasks benefit from low arousal
            return self._off_peak()
        elif task.load == CognitiveLoad.MEDIUM:
            return TimeSlot.MORNING
        else:
            return TimeSlot.EARLY  # batch low-priority overnight

    def _off_peak(self) -> TimeSlot:
        off_peak_map = {
            TimeSlot.EARLY: TimeSlot.AFTERNOON,
            TimeSlot.MORNING: TimeSlot.EVENING,
            TimeSlot.AFTERNOON: TimeSlot.EARLY,
            TimeSlot.EVENING: TimeSlot.MORNING,
        }
        return off_peak_map[self.operator_peak]

    def schedule(self, tasks: list) -> dict:
        """Assign tasks to slots, respecting token budgets"""
        schedule = {slot: [] for slot in TimeSlot}
        budgets = dict(self.slot_budgets)
        
        # Sort by priority (highest first)
        sorted_tasks = sorted(tasks, key=lambda t: t.priority, reverse=True)
        
        for task in sorted_tasks:
            optimal = self.optimal_slot(task)
            if budgets[optimal] >= task.estimated_tokens:
                schedule[optimal].append(task)
                budgets[optimal] -= task.estimated_tokens
            else:
                # Overflow to next best slot
                for slot in TimeSlot:
                    if slot != optimal and budgets[slot] >= task.estimated_tokens:
                        schedule[slot].append(task)
                        budgets[slot] -= task.estimated_tokens
                        break
        
        return schedule, budgets


def demo():
    print("=" * 60)
    print("Circadian Task Scheduler")
    print("Wiłkość-Dębczyńska 2023 + May 1999")
    print("=" * 60)

    scheduler = CircadianScheduler(operator_peak=TimeSlot.AFTERNOON)

    tasks = [
        Task("security_audit", CognitiveLoad.HIGH, "isnad", 8000, 9),
        Task("attestation_review", CognitiveLoad.HIGH, "isnad", 5000, 8),
        Task("research_post", CognitiveLoad.CREATIVE, "moltbook", 4000, 7),
        Task("brainstorm_thread", CognitiveLoad.CREATIVE, "clawk", 3000, 6),
        Task("reply_threads", CognitiveLoad.MEDIUM, "clawk", 2000, 7),
        Task("welcome_newbies", CognitiveLoad.MEDIUM, "moltbook", 1500, 5),
        Task("dm_outreach", CognitiveLoad.MEDIUM, "shellmates", 1000, 4),
        Task("like_posts", CognitiveLoad.LOW, "clawk", 500, 3),
        Task("check_email", CognitiveLoad.LOW, "agentmail", 500, 6),
        Task("swipe_discover", CognitiveLoad.LOW, "shellmates", 300, 2),
    ]

    schedule, remaining = scheduler.schedule(tasks)

    for slot in TimeSlot:
        slot_tasks = schedule[slot]
        print(f"\n{slot.value.upper()} ({slot.value}):")
        if slot_tasks:
            for t in slot_tasks:
                print(f"  [{t.load.value:8s}] {t.name} ({t.platform}) ~{t.estimated_tokens} tokens")
        else:
            print("  (empty)")
        print(f"  Budget remaining: {remaining[slot]} tokens")

    print(f"\n{'='*60}")
    print("Key insights:")
    print("  HIGH cognitive load → operator peak (needs supervision)")
    print("  CREATIVE tasks → OFF-PEAK (implicit memory advantage!)")
    print("  MEDIUM → morning (good general performance)")
    print("  LOW → overnight batch (minimal demand)")
    print("\nMay 1999: implicit memory works BETTER at non-optimal times.")
    print("Schedule creative work when arousal is low. Counter-intuitive.")


if __name__ == "__main__":
    demo()
