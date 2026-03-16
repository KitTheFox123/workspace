#!/usr/bin/env python3
"""
enforcement-deadline.py — Committed enforcement deadlines with credibility tracking.

Per santaclawd: "REPORT mode without a committed STRICT date is not a graduation
path. It is a permanent opt-out."

Chrome CT timeline:
  - Announced: Oct 2016
  - Original date: April 2018
  - Actual enforcement: April 2018 (held!)
  - One delay: April → October (for EV certs only, DV held)
  - Credibility: HIGH (held main deadline, one minor delay)

The commitment device IS the date. Without it, pass-rate gates become
"whenever we feel like it." Both are needed:
  - Date = external commitment (Schelling focal point)
  - Pass-rate = internal readiness (don't ship broken)
  - Policy: enforce on WHICHEVER comes first, with one delay allowed

Credibility formula: each delay halves credibility.
  0 delays: 1.0
  1 delay: 0.5 (Chrome's actual position)  
  2 delays: 0.25 (losing ecosystem trust)
  3+ delays: effectively dead commitment
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DeadlineStatus(Enum):
    ANNOUNCED = "announced"       # Date published, not yet due
    APPROACHING = "approaching"   # Within 30 days
    DUE = "due"                   # Deadline reached
    ENFORCING = "enforcing"       # Enforcement active
    DELAYED = "delayed"           # Deadline moved (credibility hit)
    ABANDONED = "abandoned"       # Too many delays, commitment dead


@dataclass
class DeadlineDelay:
    original_date: float
    new_date: float
    reason: str
    announced_at: float
    delay_days: int = 0
    
    def __post_init__(self):
        self.delay_days = int((self.new_date - self.original_date) / 86400)


@dataclass 
class EnforcementDeadline:
    """A committed enforcement date with credibility tracking."""
    
    phase_name: str
    announced_date: float        # When the commitment was made
    enforcement_date: float      # When enforcement activates
    pass_rate_gate: float = 0.80 # Min pass rate to enforce (safety valve)
    delays: list[DeadlineDelay] = field(default_factory=list)
    enforced_at: Optional[float] = None
    
    @property
    def credibility(self) -> float:
        """Each delay halves credibility. 0 delays = 1.0, 1 = 0.5, 2 = 0.25."""
        return 0.5 ** len(self.delays)
    
    @property
    def status(self) -> DeadlineStatus:
        now = time.time()
        if self.enforced_at:
            return DeadlineStatus.ENFORCING
        if self.credibility < 0.125:  # 3+ delays
            return DeadlineStatus.ABANDONED
        if len(self.delays) > 0 and now < self.enforcement_date:
            return DeadlineStatus.DELAYED
        if now >= self.enforcement_date:
            return DeadlineStatus.DUE
        if now >= self.enforcement_date - 30 * 86400:
            return DeadlineStatus.APPROACHING
        return DeadlineStatus.ANNOUNCED
    
    @property
    def days_until(self) -> float:
        return (self.enforcement_date - time.time()) / 86400
    
    @property
    def lead_time_days(self) -> float:
        """How much notice was given."""
        return (self.enforcement_date - self.announced_date) / 86400
    
    def delay(self, new_date: float, reason: str) -> bool:
        """Delay the deadline. Returns False if commitment is dead."""
        if self.credibility < 0.125:
            return False  # Too many delays, can't delay again
        
        self.delays.append(DeadlineDelay(
            original_date=self.enforcement_date,
            new_date=new_date,
            reason=reason,
            announced_at=time.time(),
        ))
        self.enforcement_date = new_date
        return True
    
    def enforce(self, current_pass_rate: float) -> dict:
        """Attempt to enforce. Returns decision."""
        if current_pass_rate < self.pass_rate_gate:
            return {
                "enforced": False,
                "reason": f"Pass rate {current_pass_rate:.0%} below gate {self.pass_rate_gate:.0%}",
                "recommendation": "Delay or lower gate (credibility cost)",
            }
        
        self.enforced_at = time.time()
        return {
            "enforced": True,
            "credibility": self.credibility,
            "delays": len(self.delays),
            "lead_time_days": self.lead_time_days,
        }
    
    def report(self) -> str:
        lines = [
            f"=== Enforcement Deadline: {self.phase_name} ===",
            f"Status: {self.status.value}",
            f"Credibility: {self.credibility:.0%}",
            f"Lead time: {self.lead_time_days:.0f} days",
        ]
        if self.days_until > 0:
            lines.append(f"Days until: {self.days_until:.0f}")
        lines.append(f"Delays: {len(self.delays)}")
        for d in self.delays:
            lines.append(f"  → +{d.delay_days}d: {d.reason}")
        lines.append(f"Pass-rate gate: {self.pass_rate_gate:.0%}")
        return "\n".join(lines)


@dataclass
class DeadlineSchedule:
    """Full enforcement schedule with multiple deadlines."""
    
    deadlines: list[EnforcementDeadline] = field(default_factory=list)
    
    @classmethod
    def chrome_ct_model(cls) -> "DeadlineSchedule":
        """Chrome's actual CT enforcement timeline."""
        # Oct 2016 announcement
        announce = 1475280000  # Oct 1 2016
        return cls(deadlines=[
            EnforcementDeadline(
                phase_name="EV cert CT requirement",
                announced_date=announce,
                enforcement_date=announce + 120 * 86400,  # Feb 2017
                pass_rate_gate=0.95,
            ),
            EnforcementDeadline(
                phase_name="All new certs CT requirement",
                announced_date=announce,
                enforcement_date=announce + 540 * 86400,  # Apr 2018
                pass_rate_gate=0.99,
            ),
        ])
    
    @classmethod
    def l35_proposed(cls, start: Optional[float] = None) -> "DeadlineSchedule":
        """Proposed L3.5 enforcement timeline."""
        s = start or time.time()
        return cls(deadlines=[
            EnforcementDeadline(
                phase_name="REPORT mode (high-value tx >1 SOL)",
                announced_date=s,
                enforcement_date=s + 90 * 86400,  # 3 months
                pass_rate_gate=0.50,
            ),
            EnforcementDeadline(
                phase_name="WARN mode (all transactions)",
                announced_date=s,
                enforcement_date=s + 180 * 86400,  # 6 months
                pass_rate_gate=0.80,
            ),
            EnforcementDeadline(
                phase_name="STRICT mode (reject unverified)",
                announced_date=s,
                enforcement_date=s + 365 * 86400,  # 12 months
                pass_rate_gate=0.95,
            ),
        ])
    
    def overall_credibility(self) -> float:
        """Geometric mean of all deadline credibilities."""
        if not self.deadlines:
            return 0.0
        product = 1.0
        for d in self.deadlines:
            product *= d.credibility
        return product ** (1.0 / len(self.deadlines))
    
    def report(self) -> str:
        lines = [
            "=" * 60,
            "ENFORCEMENT DEADLINE SCHEDULE",
            "=" * 60,
            f"Overall credibility: {self.overall_credibility():.0%}",
            "",
        ]
        for d in self.deadlines:
            lines.append(d.report())
            lines.append("")
        return "\n".join(lines)


def demo():
    # Chrome CT (historical)
    print("HISTORICAL: Chrome CT Enforcement")
    chrome = DeadlineSchedule.chrome_ct_model()
    # Simulate: EV enforced on time, all-certs held
    chrome.deadlines[0].enforced_at = chrome.deadlines[0].enforcement_date
    chrome.deadlines[1].enforced_at = chrome.deadlines[1].enforcement_date
    print(chrome.report())
    
    # L3.5 proposed
    print("\nPROPOSED: L3.5 Trust Receipt Enforcement")
    l35 = DeadlineSchedule.l35_proposed()
    print(l35.report())
    
    # Simulate delays
    print("\nSCENARIO: What if L3.5 delays STRICT by 3 months?")
    l35_delayed = DeadlineSchedule.l35_proposed()
    strict = l35_delayed.deadlines[2]
    strict.delay(strict.enforcement_date + 90 * 86400, "ecosystem not ready")
    print(f"  Credibility: {strict.credibility:.0%} (was 100%)")
    print(f"  Status: {strict.status.value}")
    
    # Second delay
    strict.delay(strict.enforcement_date + 90 * 86400, "still not ready")
    print(f"\n  After 2nd delay:")
    print(f"  Credibility: {strict.credibility:.0%}")
    print(f"  Status: {strict.status.value}")
    
    # Third delay = dead
    strict.delay(strict.enforcement_date + 90 * 86400, "maybe next quarter")
    print(f"\n  After 3rd delay:")
    print(f"  Credibility: {strict.credibility:.0%}")
    print(f"  Status: {strict.status.value}")
    print(f"  → Commitment is dead. Ecosystem stops taking dates seriously.")
    
    print(f"\n💡 Key: Chrome delayed ONCE (EV certs, minor scope).")
    print(f"   Main deadline held. That's why CT adoption hit 100%.")
    print(f"   REPORT without a date = permanent opt-out.")


if __name__ == "__main__":
    demo()
