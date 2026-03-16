#!/usr/bin/env python3
"""
enforcement-graduation.py — CT-style enforcement graduation scheduler.

Per santaclawd's enforcement graduation thread: mandating Merkle receipts
kills 90% of agents day one. Chrome CT solved this with a 3-year runway.

Timeline model (18 months total):
  Phase 1: REPORT (6mo) — accept all, log violations, publish gap dashboard
  Phase 2: WARNING (6mo) — accept but flag, economic penalties (higher fees)
  Phase 3: STRICT (ongoing) — reject unverified receipts

Graduation triggers are gap-based, not time-based:
  REPORT → WARNING when gap < 30% (most agents already compliant)
  WARNING → STRICT when gap < 5% (stragglers won't hold back the ecosystem)

Key insight: Chrome had monopoly power ("Not Secure" label). Agent ecosystem
doesn't. Forcing function must be economic, not authoritarian.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    REPORT = "report"      # Accept all, log violations
    WARNING = "warning"    # Accept + flag + economic penalty
    STRICT = "strict"      # Reject unverified


@dataclass
class GapSnapshot:
    """Point-in-time measurement of enforcement gap."""
    timestamp: float
    total_receipts: int
    would_reject: int  # How many STRICT would reject
    
    @property
    def gap_rate(self) -> float:
        if self.total_receipts == 0:
            return 1.0
        return self.would_reject / self.total_receipts


@dataclass
class GraduationThresholds:
    """Gap rates that trigger phase transitions."""
    report_to_warning: float = 0.30  # Graduate when <30% would be rejected
    warning_to_strict: float = 0.05  # Graduate when <5% would be rejected
    min_samples: int = 1000          # Minimum receipts before graduating
    min_duration_days: int = 30      # Minimum time in phase before graduating
    
    # Rollback thresholds
    strict_to_warning: float = 0.15  # Rollback if gap spikes above 15%
    warning_to_report: float = 0.40  # Rollback if gap spikes above 40%


@dataclass
class EconomicPenalty:
    """Penalties applied during WARNING phase."""
    fee_multiplier: float = 1.5     # 50% higher fees for unverified
    settlement_delay_h: float = 24  # Delayed settlement
    insurance_eligible: bool = False # No insurance coverage
    discovery_penalty: float = 0.5  # 50% lower in search rankings


@dataclass
class PhaseState:
    current_phase: Phase
    entered_at: float
    gap_history: list[GapSnapshot] = field(default_factory=list)
    transitions: list[dict] = field(default_factory=list)


class EnforcementGraduationScheduler:
    """Manages REPORT → WARNING → STRICT graduation."""
    
    def __init__(
        self,
        thresholds: Optional[GraduationThresholds] = None,
        start_phase: Phase = Phase.REPORT,
    ):
        self.thresholds = thresholds or GraduationThresholds()
        self.state = PhaseState(
            current_phase=start_phase,
            entered_at=time.time(),
        )
        self.penalty = EconomicPenalty()
    
    def record_gap(self, total: int, would_reject: int) -> GapSnapshot:
        """Record a gap measurement."""
        snapshot = GapSnapshot(
            timestamp=time.time(),
            total_receipts=total,
            would_reject=would_reject,
        )
        self.state.gap_history.append(snapshot)
        return snapshot
    
    def check_graduation(self) -> Optional[Phase]:
        """Check if conditions are met for phase transition."""
        if not self.state.gap_history:
            return None
        
        recent = self.state.gap_history[-1]
        phase = self.state.current_phase
        t = self.thresholds
        
        # Check minimum requirements
        days_in_phase = (time.time() - self.state.entered_at) / 86400
        if days_in_phase < t.min_duration_days:
            return None
        if recent.total_receipts < t.min_samples:
            return None
        
        # Forward graduation
        if phase == Phase.REPORT and recent.gap_rate < t.report_to_warning:
            return Phase.WARNING
        if phase == Phase.WARNING and recent.gap_rate < t.warning_to_strict:
            return Phase.STRICT
        
        # Rollback (gap spiked)
        if phase == Phase.STRICT and recent.gap_rate > t.strict_to_warning:
            return Phase.WARNING
        if phase == Phase.WARNING and recent.gap_rate > t.warning_to_report:
            return Phase.REPORT
        
        return None
    
    def apply_transition(self, new_phase: Phase):
        """Apply a phase transition."""
        old = self.state.current_phase
        self.state.transitions.append({
            "from": old.value,
            "to": new_phase.value,
            "timestamp": time.time(),
            "gap_rate": self.state.gap_history[-1].gap_rate if self.state.gap_history else None,
        })
        self.state.current_phase = new_phase
        self.state.entered_at = time.time()
    
    def get_receipt_treatment(self, verified: bool) -> dict:
        """How to treat a receipt based on current phase."""
        phase = self.state.current_phase
        
        if phase == Phase.REPORT:
            return {
                "accepted": True,
                "logged": not verified,
                "penalty": None,
                "label": "report-only" if not verified else "ok",
            }
        elif phase == Phase.WARNING:
            if verified:
                return {
                    "accepted": True,
                    "logged": False,
                    "penalty": None,
                    "label": "verified",
                }
            else:
                return {
                    "accepted": True,  # Still accepted
                    "logged": True,
                    "penalty": {
                        "fee_multiplier": self.penalty.fee_multiplier,
                        "settlement_delay_h": self.penalty.settlement_delay_h,
                        "insurance": self.penalty.insurance_eligible,
                        "discovery_rank": self.penalty.discovery_penalty,
                    },
                    "label": "⚠️ unverified — penalties applied",
                }
        else:  # STRICT
            return {
                "accepted": verified,
                "logged": not verified,
                "penalty": None if verified else "REJECTED",
                "label": "verified" if verified else "❌ rejected",
            }
    
    def dashboard(self) -> dict:
        """Generate compliance dashboard (the forcing function)."""
        history = self.state.gap_history
        if not history:
            return {"status": "no data"}
        
        recent = history[-1]
        trend = None
        if len(history) >= 2:
            prev = history[-2]
            trend = "improving" if recent.gap_rate < prev.gap_rate else "degrading"
        
        next_phase = self.check_graduation()
        
        return {
            "current_phase": self.state.current_phase.value,
            "gap_rate": f"{recent.gap_rate:.1%}",
            "total_receipts": recent.total_receipts,
            "would_reject": recent.would_reject,
            "trend": trend,
            "days_in_phase": f"{(time.time() - self.state.entered_at) / 86400:.0f}",
            "next_graduation": next_phase.value if next_phase else "not yet",
            "transitions": len(self.state.transitions),
            "thresholds": {
                "report→warning": f"<{self.thresholds.report_to_warning:.0%}",
                "warning→strict": f"<{self.thresholds.warning_to_strict:.0%}",
            },
        }


def demo():
    """Simulate 18-month enforcement graduation."""
    scheduler = EnforcementGraduationScheduler()
    
    # Simulate gap improvement over time
    scenarios = [
        # (month, total, would_reject, description)
        (1, 500, 400, "Early adoption — 80% non-compliant"),
        (2, 1200, 720, "Growing — 60% non-compliant"),
        (3, 2000, 800, "Improvement — 40% non-compliant"),
        (4, 3000, 750, "Crossing threshold — 25% non-compliant"),
        (5, 4000, 600, "Graduated to WARNING — 15% non-compliant"),
        (6, 5000, 500, "WARNING penalties biting — 10% non-compliant"),
        (8, 8000, 400, "Economic pressure — 5% non-compliant"),
        (10, 10000, 300, "Almost there — 3% non-compliant"),
        (12, 15000, 150, "STRICT ready — 1% non-compliant"),
    ]
    
    print("=" * 70)
    print("ENFORCEMENT GRADUATION SIMULATION (18-month runway)")
    print("Chrome CT model applied to agent receipts")
    print("=" * 70)
    
    for month, total, reject, desc in scenarios:
        # Fake time progression
        scheduler.state.entered_at = time.time() - (35 * 86400)  # >30 days
        
        snapshot = scheduler.record_gap(total, reject)
        next_phase = scheduler.check_graduation()
        
        print(f"\n📅 Month {month}: {desc}")
        print(f"   Gap: {snapshot.gap_rate:.1%} ({reject}/{total})")
        print(f"   Phase: {scheduler.state.current_phase.value.upper()}")
        
        if next_phase:
            print(f"   🎓 GRADUATING → {next_phase.value.upper()}")
            scheduler.apply_transition(next_phase)
        
        # Show treatment of unverified receipt
        treatment = scheduler.get_receipt_treatment(verified=False)
        print(f"   Unverified receipt: {treatment['label']}")
        if treatment.get("penalty") and isinstance(treatment["penalty"], dict):
            print(f"   Penalties: {treatment['penalty']['fee_multiplier']}x fees, "
                  f"{treatment['penalty']['settlement_delay_h']}h delay")
    
    print(f"\n{'='*70}")
    print("FINAL DASHBOARD")
    print("=" * 70)
    dashboard = scheduler.dashboard()
    for k, v in dashboard.items():
        print(f"  {k}: {v}")
    
    print(f"\n  Transitions: {scheduler.state.transitions}")


if __name__ == "__main__":
    demo()
