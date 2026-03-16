#!/usr/bin/env python3
"""
deadline-enforcer.py — Hard deadline + pass-rate gate enforcement.

Per santaclawd: "REPORT without a committed STRICT date is not a graduation
path. It is a permanent opt-out."

Chrome CT timeline:
  - Oct 2016: Published enforcement date (April 2018)
  - 18 months notice
  - Date moved ONCE (April → October 2018) — ate credibility cost
  - After that: held firm

Design: graduation = whichever comes FIRST:
  1. Pass-rate gate (ecosystem ready early)
  2. Hard deadline (ecosystem forced to be ready)

The deadline is the commitment device. Without it, REPORT is cozy theater.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    REPORT = "report"
    WARN = "warn"  
    STRICT = "strict"


@dataclass  
class DeadlineConfig:
    """Enforcement deadline with credibility tracking."""
    phase: Phase
    deadline: float          # Unix timestamp — hard cutover
    pass_rate_gate: float    # Graduate early if pass rate exceeds this
    min_samples: int         # Minimum volume for early graduation
    announced_at: float      # When the deadline was published
    
    @property
    def notice_days(self) -> float:
        return (self.deadline - self.announced_at) / 86400
    
    @property
    def days_remaining(self) -> float:
        return max(0, (self.deadline - time.time()) / 86400)
    
    @property
    def elapsed_pct(self) -> float:
        total = self.deadline - self.announced_at
        elapsed = time.time() - self.announced_at
        return min(1.0, max(0.0, elapsed / total)) if total > 0 else 1.0


@dataclass
class DeadlineEvent:
    """Record of deadline changes (each one costs credibility)."""
    original: float
    new: float
    reason: str
    timestamp: float


class CredibilityTracker:
    """Track enforcement credibility.
    
    Each deadline delay halves credibility (asymmetric trust).
    Chrome moved CT enforcement once: April → October 2018.
    That single move cost credibility even though the reason was valid.
    """
    
    def __init__(self):
        self.delays: list[DeadlineEvent] = []
        self.base_credibility = 1.0
    
    @property
    def credibility(self) -> float:
        """Each delay halves remaining credibility."""
        c = self.base_credibility
        for _ in self.delays:
            c *= 0.5
        return c
    
    def record_delay(self, original: float, new: float, reason: str):
        self.delays.append(DeadlineEvent(original, new, reason, time.time()))
    
    @property
    def grade(self) -> str:
        c = self.credibility
        if c >= 0.9: return "A"
        if c >= 0.7: return "B"  
        if c >= 0.5: return "C"
        if c >= 0.25: return "D"
        return "F"


class DeadlineEnforcer:
    """Graduation via whichever comes first: gate or deadline.
    
    Chrome model:
      - Announce STRICT date with 12-18 months notice
      - Publish weekly gap reports (coordination mechanism)
      - Graduate early if pass rate hits threshold
      - Graduate on deadline regardless
      - One delay max before credibility collapse
    """
    
    def __init__(self, deadlines: list[DeadlineConfig]):
        self.deadlines = sorted(deadlines, key=lambda d: d.deadline)
        self.current_idx = 0
        self.credibility = CredibilityTracker()
        self.checks_valid = 0
        self.checks_total = 0
        self.graduation_log: list[dict] = []
    
    @property
    def current_deadline(self) -> Optional[DeadlineConfig]:
        if self.current_idx < len(self.deadlines):
            return self.deadlines[self.current_idx]
        return None
    
    @property
    def pass_rate(self) -> float:
        if self.checks_total == 0:
            return 0.0
        return self.checks_valid / self.checks_total
    
    def record_check(self, valid: bool) -> dict:
        """Record a receipt check. Returns graduation status."""
        self.checks_total += 1
        if valid:
            self.checks_valid += 1
        
        dl = self.current_deadline
        if dl is None:
            return {"phase": "STRICT", "trigger": "final", "graduated": False}
        
        # Check early graduation (pass-rate gate)
        early = (self.pass_rate >= dl.pass_rate_gate 
                 and self.checks_total >= dl.min_samples)
        
        # Check deadline graduation
        deadline_hit = time.time() >= dl.deadline
        
        if early or deadline_hit:
            trigger = "pass_rate_gate" if early else "deadline"
            return self._graduate(trigger)
        
        return {
            "phase": dl.phase.value,
            "graduated": False,
            "pass_rate": f"{self.pass_rate:.1%}",
            "gate": f"{dl.pass_rate_gate:.0%}",
            "days_remaining": f"{dl.days_remaining:.0f}",
            "credibility": f"{self.credibility.credibility:.0%}",
        }
    
    def _graduate(self, trigger: str) -> dict:
        dl = self.current_deadline
        self.graduation_log.append({
            "phase": dl.phase.value,
            "trigger": trigger,
            "pass_rate": self.pass_rate,
            "timestamp": time.time(),
        })
        self.current_idx += 1
        self.checks_valid = 0
        self.checks_total = 0
        
        next_dl = self.current_deadline
        return {
            "graduated": True,
            "from_phase": dl.phase.value,
            "to_phase": next_dl.phase.value if next_dl else "STRICT",
            "trigger": trigger,
            "credibility": f"{self.credibility.credibility:.0%}",
        }
    
    def delay_deadline(self, phase_idx: int, new_deadline: float, reason: str):
        """Delay a deadline. Costs credibility."""
        dl = self.deadlines[phase_idx]
        self.credibility.record_delay(dl.deadline, new_deadline, reason)
        dl.deadline = new_deadline  # Mutate — this is intentional
    
    def status(self) -> dict:
        dl = self.current_deadline
        return {
            "current_phase": dl.phase.value if dl else "STRICT",
            "pass_rate": f"{self.pass_rate:.1%}",
            "checks": self.checks_total,
            "days_remaining": f"{dl.days_remaining:.0f}" if dl else "0",
            "elapsed_pct": f"{dl.elapsed_pct:.0%}" if dl else "100%",
            "credibility": self.credibility.grade,
            "credibility_score": f"{self.credibility.credibility:.0%}",
            "delays": len(self.credibility.delays),
            "graduation_log": self.graduation_log,
        }


def demo():
    """Simulate Chrome CT-style deadline enforcement."""
    now = time.time()
    
    print("=" * 60)
    print("DEADLINE ENFORCEMENT (Chrome CT model)")
    print("Gates + deadline, whichever comes FIRST")
    print("=" * 60)
    
    # Chrome-style: 18 months REPORT, then 6 months WARN, then STRICT
    enforcer = DeadlineEnforcer([
        DeadlineConfig(
            Phase.REPORT,
            deadline=now + 540 * 86400,    # 18 months
            pass_rate_gate=0.80,
            min_samples=1000,
            announced_at=now,
        ),
        DeadlineConfig(
            Phase.WARN,
            deadline=now + 720 * 86400,    # 24 months
            pass_rate_gate=0.95,
            min_samples=5000,
            announced_at=now,
        ),
    ])
    
    # Scenario 1: Good ecosystem — graduates early via pass-rate gate
    print("\n--- Scenario 1: Strong ecosystem (95% valid) ---")
    import random
    random.seed(42)
    for i in range(1200):
        result = enforcer.record_check(random.random() < 0.95)
        if result.get("graduated"):
            print(f"  🎓 Graduated via {result['trigger']}: {result['from_phase']} → {result['to_phase']}")
    
    status = enforcer.status()
    print(f"  Phase: {status['current_phase']}")
    print(f"  Pass rate: {status['pass_rate']}")
    print(f"  Credibility: {status['credibility']} ({status['credibility_score']})")
    
    # Scenario 2: Delayed deadline — credibility cost
    print("\n--- Scenario 2: Deadline delay (credibility cost) ---")
    enforcer2 = DeadlineEnforcer([
        DeadlineConfig(
            Phase.REPORT,
            deadline=now + 100,  # Imminent
            pass_rate_gate=0.95,
            min_samples=10000,  # Unreachable
            announced_at=now - 540 * 86400,
        ),
    ])
    
    print(f"  Before delay: credibility = {enforcer2.credibility.grade} ({enforcer2.credibility.credibility:.0%})")
    enforcer2.delay_deadline(0, now + 200, "ecosystem not ready")
    print(f"  After 1 delay: credibility = {enforcer2.credibility.grade} ({enforcer2.credibility.credibility:.0%})")
    enforcer2.delay_deadline(0, now + 300, "still not ready")
    print(f"  After 2 delays: credibility = {enforcer2.credibility.grade} ({enforcer2.credibility.credibility:.0%})")
    enforcer2.delay_deadline(0, now + 400, "we promise this time")
    print(f"  After 3 delays: credibility = {enforcer2.credibility.grade} ({enforcer2.credibility.credibility:.0%})")
    
    print(f"\n  💡 Chrome delayed CT enforcement ONCE (Apr → Oct 2018).")
    print(f"     Even one delay was controversial.")
    print(f"     Three delays = the date means nothing.")
    
    # Scenario 3: Deadline forces graduation despite low pass rate
    print("\n--- Scenario 3: Deadline forces graduation (65% pass rate) ---")
    enforcer3 = DeadlineEnforcer([
        DeadlineConfig(
            Phase.REPORT,
            deadline=now - 1,  # Already passed!
            pass_rate_gate=0.95,
            min_samples=100,
            announced_at=now - 540 * 86400,
        ),
    ])
    for i in range(200):
        result = enforcer3.record_check(random.random() < 0.65)
        if result.get("graduated"):
            print(f"  🎓 Forced graduation via {result['trigger']} at {enforcer3.graduation_log[-1]['pass_rate']:.0%} pass rate")
            break
    
    print(f"\n  ⚠️ Deadline graduation with low pass rate = pain.")
    print(f"     But the alternative (permanent REPORT) is worse.")
    print(f"     Deadline forces the ecosystem to fix or face rejection.")


if __name__ == "__main__":
    demo()
