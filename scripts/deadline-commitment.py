#!/usr/bin/env python3
"""
deadline-commitment.py — Committed enforcement deadlines with credibility tracking.

Per santaclawd: "REPORT without a committed STRICT date is not a graduation path.
It is a permanent opt-out."

Chrome CT: announced Oct 2016, enforced April 2018. Date moved ONCE (to Oct 2018).
Each delay costs more credibility than the last — trust is asymmetric.

HTTP/2: available since 2015, still optional in 2026. No deadline = no adoption pressure.

This tool:
1. Publishes a committed enforcement date
2. Tracks credibility based on deadline adherence
3. Models the cost of reneging (each delay halves credibility)
4. Provides "should I delay?" decision support with credibility cost analysis
"""

import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DeadlineStatus(Enum):
    ANNOUNCED = "announced"       # Date published, not yet reached
    ENFORCING = "enforcing"       # Deadline hit, enforcement active
    DELAYED = "delayed"           # Deadline pushed back
    ABANDONED = "abandoned"       # Deadline removed entirely
    ACHIEVED = "achieved"         # Enforcement held for >30 days


@dataclass
class DeadlineEvent:
    timestamp: float
    event_type: str  # "announce", "delay", "enforce", "abandon"
    original_date: float
    new_date: Optional[float] = None
    reason: str = ""


@dataclass 
class CredibilityScore:
    """Credibility of enforcement commitments. Asymmetric: easy to lose, hard to earn."""
    score: float = 1.0              # 0.0 to 1.0
    delays: int = 0
    total_delay_days: float = 0.0
    deadlines_met: int = 0
    deadlines_missed: int = 0
    
    def record_delay(self, days: float, reason: str = ""):
        """Each delay halves credibility. Trust is asymmetric."""
        self.delays += 1
        self.total_delay_days += days
        # First delay: 0.5x. Second: 0.25x. Third: 0.125x.
        self.score *= 0.5
        self.deadlines_missed += 1
    
    def record_met(self):
        """Meeting a deadline builds credibility slowly."""
        self.deadlines_met += 1
        # Slow recovery: +10% of remaining gap
        self.score += (1.0 - self.score) * 0.10
    
    @property
    def grade(self) -> str:
        if self.score >= 0.90:
            return "A"  # Chrome-grade: announced and held
        elif self.score >= 0.70:
            return "B"  # One delay, recovered
        elif self.score >= 0.40:
            return "C"  # Multiple delays but still enforcing
        elif self.score >= 0.20:
            return "D"  # Credibility damaged
        return "F"       # HTTP/2 territory: no one believes you


class EnforcementDeadline:
    """A committed enforcement date with credibility tracking."""
    
    def __init__(self, name: str, announce_date: float, enforce_date: float):
        self.name = name
        self.announce_date = announce_date
        self.enforce_date = enforce_date
        self.original_enforce_date = enforce_date
        self.status = DeadlineStatus.ANNOUNCED
        self.credibility = CredibilityScore()
        self.events: list[DeadlineEvent] = [
            DeadlineEvent(announce_date, "announce", enforce_date)
        ]
    
    @property
    def days_until_deadline(self) -> float:
        return (self.enforce_date - time.time()) / 86400
    
    @property
    def total_lead_time_days(self) -> float:
        return (self.enforce_date - self.announce_date) / 86400
    
    def delay(self, new_date: float, reason: str = "") -> dict:
        """Push back the deadline. Returns credibility cost analysis."""
        delay_days = (new_date - self.enforce_date) / 86400
        old_credibility = self.credibility.score
        
        self.credibility.record_delay(delay_days, reason)
        self.events.append(DeadlineEvent(
            time.time(), "delay", self.enforce_date, new_date, reason
        ))
        self.enforce_date = new_date
        self.status = DeadlineStatus.DELAYED
        
        return {
            "delay_days": delay_days,
            "credibility_before": f"{old_credibility:.2f}",
            "credibility_after": f"{self.credibility.score:.2f}",
            "credibility_cost": f"{old_credibility - self.credibility.score:.2f}",
            "delays_total": self.credibility.delays,
            "recommendation": self._delay_recommendation(),
        }
    
    def enforce(self) -> dict:
        """Mark deadline as enforced."""
        self.status = DeadlineStatus.ENFORCING
        self.credibility.record_met()
        self.events.append(DeadlineEvent(
            time.time(), "enforce", self.enforce_date
        ))
        return {
            "status": "enforcing",
            "credibility": f"{self.credibility.score:.2f}",
            "grade": self.credibility.grade,
            "delays_before_enforcement": self.credibility.delays,
        }
    
    def should_delay(self, proposed_days: float, ecosystem_pass_rate: float) -> dict:
        """Decision support: should we delay? What's the credibility cost?"""
        # Simulate the delay
        sim_score = self.credibility.score * 0.5
        
        # Cost of delaying
        delay_cost = self.credibility.score - sim_score
        
        # Cost of enforcing now (broken ecosystem)
        enforce_cost = 1.0 - ecosystem_pass_rate  # Fraction that would fail
        
        # Break-even: delay if ecosystem damage > credibility damage
        should_delay_bool = enforce_cost > delay_cost
        
        return {
            "proposed_delay_days": proposed_days,
            "current_credibility": f"{self.credibility.score:.2f}",
            "credibility_after_delay": f"{sim_score:.2f}",
            "credibility_cost": f"{delay_cost:.2f}",
            "ecosystem_pass_rate": f"{ecosystem_pass_rate:.0%}",
            "ecosystem_damage_if_enforce": f"{enforce_cost:.2f}",
            "recommendation": "DELAY" if should_delay_bool else "ENFORCE",
            "reasoning": (
                f"Ecosystem damage ({enforce_cost:.2f}) > credibility cost ({delay_cost:.2f}). Delay."
                if should_delay_bool else
                f"Credibility cost ({delay_cost:.2f}) >= ecosystem damage ({enforce_cost:.2f}). Enforce."
            ),
        }
    
    def _delay_recommendation(self) -> str:
        delays = self.credibility.delays
        if delays == 1:
            return "First delay. Chrome did this once (Apr→Oct 2018). Recoverable."
        elif delays == 2:
            return "Second delay. Credibility at 25%. This is your last chance."
        elif delays == 3:
            return "Three delays. You're HTTP/2 now. No one believes the next date."
        return f"{delays} delays. Credibility destroyed. Consider abandoning the deadline and using pass-rate gates only."
    
    def status_report(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "announce_date": time.strftime("%Y-%m-%d", time.localtime(self.announce_date)),
            "enforce_date": time.strftime("%Y-%m-%d", time.localtime(self.enforce_date)),
            "original_enforce_date": time.strftime("%Y-%m-%d", time.localtime(self.original_enforce_date)),
            "days_until_deadline": f"{self.days_until_deadline:.0f}",
            "lead_time_days": f"{self.total_lead_time_days:.0f}",
            "credibility": f"{self.credibility.score:.2f}",
            "grade": self.credibility.grade,
            "delays": self.credibility.delays,
            "total_delay_days": f"{self.credibility.total_delay_days:.0f}",
        }


def demo():
    now = time.time()
    
    print("=" * 60)
    print("ENFORCEMENT DEADLINE CREDIBILITY TRACKER")
    print("=" * 60)
    
    # Case 1: Chrome CT (held with one delay)
    print("\n--- Case 1: Chrome CT (one delay, recovered) ---")
    ct = EnforcementDeadline("Chrome CT", now - 730*86400, now - 365*86400)
    # One delay (Apr → Oct 2018)
    result = ct.delay(now - 180*86400, "ecosystem not ready")
    print(f"  Delay: {result['delay_days']:.0f}d, credibility: {result['credibility_before']} → {result['credibility_after']}")
    print(f"  → {result['recommendation']}")
    # Then enforced
    result = ct.enforce()
    print(f"  Enforced: credibility={result['credibility']}, grade={result['grade']}")
    
    # Case 2: HTTP/2 (never enforced)  
    print("\n--- Case 2: HTTP/2 (no deadline = no adoption pressure) ---")
    http2 = EnforcementDeadline("HTTP/2", now - 4000*86400, now - 3000*86400)
    for i in range(4):
        result = http2.delay(now - (2500 - i*500)*86400, f"delay #{i+1}")
    print(f"  After {http2.credibility.delays} delays: credibility={http2.credibility.score:.3f}, grade={http2.credibility.grade}")
    print(f"  → {http2._delay_recommendation()}")
    
    # Case 3: L3.5 (planning)
    print("\n--- Case 3: L3.5 Receipt Enforcement (planning) ---")
    l35 = EnforcementDeadline("L3.5 Receipts", now, now + 540*86400)
    report = l35.status_report()
    print(f"  Status: {report['status']}")
    print(f"  Enforce date: {report['enforce_date']}")
    print(f"  Lead time: {report['lead_time_days']} days")
    print(f"  Credibility: {report['credibility']} ({report['grade']})")
    
    # Decision support
    print("\n--- Should L3.5 delay? ---")
    scenarios = [
        (90, 0.60, "60% pass rate at deadline"),
        (90, 0.85, "85% pass rate at deadline"),
        (90, 0.95, "95% pass rate at deadline"),
    ]
    for delay_days, pass_rate, label in scenarios:
        result = l35.should_delay(delay_days, pass_rate)
        print(f"\n  Scenario: {label}")
        print(f"  → {result['recommendation']}: {result['reasoning']}")


if __name__ == "__main__":
    demo()
