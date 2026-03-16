#!/usr/bin/env python3
"""
enforcement-graduation.py — REPORT→STRICT graduation timeline for L3.5 receipts.

Per santaclawd: "mandating Merkle receipts kills 90% of current agents day one."
Chrome CT model: 2 years REPORT, then STRICT. The gap log was the forcing function.

Key insight: graduation trigger is the ENFORCEMENT GAP metric, not a fixed date.
When gap < threshold, publish STRICT date. Data-driven, not calendar-driven.

HTTPS adoption precedent:
- Chrome 56 (Jan 2017): "Not Secure" warning on HTTP login pages
- Chrome 68 (Jul 2018): "Not Secure" on ALL HTTP pages
- Result: 40% → 95% HTTPS in ~3 years
- The client (Chrome) drove adoption, not the spec (RFC 2818)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class Phase(Enum):
    REPORT = "report"          # Log violations, accept all
    WARN = "warn"              # Visual indicator to consumers
    SOFT_REJECT = "soft_reject" # Reject by default, allow override
    STRICT = "strict"          # Hard reject, no override


@dataclass
class GapSnapshot:
    """Point-in-time enforcement gap measurement."""
    timestamp: datetime
    total_receipts: int
    would_reject: int
    
    @property
    def gap(self) -> float:
        if self.total_receipts == 0:
            return 1.0
        return self.would_reject / self.total_receipts


@dataclass
class GraduationPolicy:
    """Data-driven phase transitions."""
    # Gap thresholds for phase transitions
    report_to_warn: float = 0.20      # <20% gap → WARN
    warn_to_soft_reject: float = 0.10  # <10% gap → SOFT_REJECT
    soft_reject_to_strict: float = 0.05 # <5% gap → STRICT
    
    # Minimum observation period per phase (days)
    min_report_days: int = 90
    min_warn_days: int = 60
    min_soft_reject_days: int = 30
    
    # Advance notice before next phase (days)
    advance_notice_days: int = 30
    
    # Minimum receipts for statistical confidence
    min_sample_size: int = 1000


@dataclass
class GraduationTimeline:
    """Tracks enforcement graduation state."""
    current_phase: Phase = Phase.REPORT
    phase_start: datetime = field(default_factory=datetime.utcnow)
    gap_history: list[GapSnapshot] = field(default_factory=list)
    policy: GraduationPolicy = field(default_factory=GraduationPolicy)
    announced_next_phase: Optional[Phase] = None
    announced_date: Optional[datetime] = None
    
    def record_gap(self, snapshot: GapSnapshot):
        """Record a gap measurement."""
        self.gap_history.append(snapshot)
    
    def evaluate(self, now: Optional[datetime] = None) -> dict:
        """Evaluate whether to graduate to next phase."""
        now = now or datetime.utcnow()
        
        if not self.gap_history:
            return {"action": "wait", "reason": "no data"}
        
        recent = [s for s in self.gap_history 
                  if (now - s.timestamp).days <= 30]
        
        if not recent:
            return {"action": "wait", "reason": "no recent data (30d)"}
        
        total_receipts = sum(s.total_receipts for s in recent)
        if total_receipts < self.policy.min_sample_size:
            return {
                "action": "wait",
                "reason": f"insufficient data ({total_receipts}/{self.policy.min_sample_size})",
            }
        
        avg_gap = sum(s.gap * s.total_receipts for s in recent) / total_receipts
        days_in_phase = (now - self.phase_start).days
        
        # Determine next phase and threshold
        transitions = {
            Phase.REPORT: (Phase.WARN, self.policy.report_to_warn, self.policy.min_report_days),
            Phase.WARN: (Phase.SOFT_REJECT, self.policy.warn_to_soft_reject, self.policy.min_warn_days),
            Phase.SOFT_REJECT: (Phase.STRICT, self.policy.soft_reject_to_strict, self.policy.min_soft_reject_days),
        }
        
        if self.current_phase == Phase.STRICT:
            return {"action": "complete", "phase": "STRICT", "gap": f"{avg_gap:.1%}"}
        
        next_phase, threshold, min_days = transitions[self.current_phase]
        
        result = {
            "current_phase": self.current_phase.value,
            "days_in_phase": days_in_phase,
            "min_days_required": min_days,
            "current_gap": f"{avg_gap:.1%}",
            "threshold": f"{threshold:.0%}",
            "sample_size": total_receipts,
        }
        
        if days_in_phase < min_days:
            result["action"] = "wait"
            result["reason"] = f"min observation period ({days_in_phase}/{min_days}d)"
            result["days_remaining"] = min_days - days_in_phase
        elif avg_gap > threshold:
            result["action"] = "wait"
            result["reason"] = f"gap too high ({avg_gap:.1%} > {threshold:.0%})"
            result["gap_delta"] = f"{avg_gap - threshold:.1%}"
        elif self.announced_next_phase != next_phase:
            # Announce graduation
            result["action"] = "announce"
            result["next_phase"] = next_phase.value
            result["effective_date"] = (now + timedelta(days=self.policy.advance_notice_days)).isoformat()
            result["notice_days"] = self.policy.advance_notice_days
        elif self.announced_date and now >= self.announced_date:
            result["action"] = "graduate"
            result["next_phase"] = next_phase.value
        else:
            days_until = (self.announced_date - now).days if self.announced_date else "?"
            result["action"] = "pending"
            result["next_phase"] = next_phase.value
            result["days_until_graduation"] = days_until
        
        return result
    
    def graduate(self, next_phase: Phase, now: Optional[datetime] = None):
        """Execute phase transition."""
        now = now or datetime.utcnow()
        self.current_phase = next_phase
        self.phase_start = now
        self.announced_next_phase = None
        self.announced_date = None
    
    def announce(self, next_phase: Phase, effective: datetime):
        """Announce upcoming graduation."""
        self.announced_next_phase = next_phase
        self.announced_date = effective


def simulate_adoption():
    """Simulate L3.5 receipt adoption over 12 months."""
    print("=" * 65)
    print("L3.5 Enforcement Graduation Simulation")
    print("Based on Chrome CT / HTTPS adoption precedent")
    print("=" * 65)
    
    timeline = GraduationTimeline(
        phase_start=datetime(2026, 4, 1),
        policy=GraduationPolicy(
            min_report_days=90,
            min_warn_days=60,
            min_soft_reject_days=30,
            advance_notice_days=30,
        ),
    )
    
    # Simulate monthly gap measurements
    # Gap decreases as ecosystem adopts Merkle receipts
    monthly_data = [
        # (month_offset, total_receipts, gap_pct)
        (1, 500, 0.85),     # Month 1: 85% would fail STRICT
        (2, 1200, 0.70),    # Month 2: early adopters shipping
        (3, 3000, 0.45),    # Month 3: major frameworks add support
        (4, 5000, 0.30),    # Month 4: adoption accelerating
        (5, 8000, 0.18),    # Month 5: below WARN threshold
        (6, 12000, 0.12),   # Month 6: WARN announced
        (7, 15000, 0.09),   # Month 7: below SOFT_REJECT threshold
        (8, 18000, 0.06),   # Month 8: SOFT_REJECT announced
        (9, 22000, 0.04),   # Month 9: below STRICT threshold
        (10, 25000, 0.03),  # Month 10: STRICT announced
        (11, 28000, 0.02),  # Month 11: nearly full adoption
        (12, 30000, 0.01),  # Month 12: ecosystem adopted
    ]
    
    base = datetime(2026, 4, 1)
    
    for month, total, gap_pct in monthly_data:
        now = base + timedelta(days=month * 30)
        would_reject = int(total * gap_pct)
        
        snapshot = GapSnapshot(
            timestamp=now,
            total_receipts=total,
            would_reject=would_reject,
        )
        timeline.record_gap(snapshot)
        
        result = timeline.evaluate(now)
        
        print(f"\n📅 Month {month:2d} ({now.strftime('%Y-%m')})")
        print(f"   Phase: {timeline.current_phase.value.upper()}")
        print(f"   Receipts: {total:,} | Gap: {gap_pct:.0%} | Would reject: {would_reject:,}")
        print(f"   → {result['action'].upper()}: {result.get('reason', result.get('next_phase', ''))}")
        
        # Execute transitions
        if result["action"] == "announce":
            effective = now + timedelta(days=timeline.policy.advance_notice_days)
            timeline.announce(Phase(result["next_phase"]), effective)
            print(f"   📢 {result['next_phase'].upper()} announced for {effective.strftime('%Y-%m-%d')}")
        elif result["action"] == "graduate":
            next_p = Phase(result["next_phase"])
            timeline.graduate(next_p, now)
            print(f"   🎓 Graduated to {next_p.value.upper()}")
    
    # Summary
    print(f"\n{'=' * 65}")
    print("Summary")
    print(f"{'=' * 65}")
    print(f"Final phase: {timeline.current_phase.value.upper()}")
    print(f"Total snapshots: {len(timeline.gap_history)}")
    
    first_gap = timeline.gap_history[0].gap
    last_gap = timeline.gap_history[-1].gap
    print(f"Gap trajectory: {first_gap:.0%} → {last_gap:.0%}")
    print(f"\nKey insight: data-driven graduation > fixed calendar.")
    print(f"Chrome HTTPS: 2 years. Agent ecosystem: ~10 months (faster iteration).")
    print(f"The gap log IS the forcing function — publish it, let ecosystem respond.")


if __name__ == "__main__":
    simulate_adoption()
