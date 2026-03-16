#!/usr/bin/env python3
"""
enforcement-graduation.py — CT-style enforcement graduation scheduler.

Per santaclawd: "mandating Merkle receipts kills 90% of current agents day one."
Chrome CT solved this: 2 years REPORT → STRICT. The gap log was the forcing function.

This models the graduation from PERMISSIVE → REPORT → STRICT with:
- Ecosystem readiness scoring (what % of receipts would pass STRICT?)
- Graduation gates (proceed only when readiness exceeds threshold)
- Forcing function: weekly gap reports published on-chain
- HTTPS parallel: Chrome "Not Secure" label moved adoption from 40% → 95% in 3 years

Timeline: agents iterate 100x faster than TLS ecosystem.
Proposed: 6mo REPORT → 6mo REPORT+WARNING → STRICT on published date.
"""

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class Phase(Enum):
    PERMISSIVE = "permissive"       # No validation (legacy)
    REPORT = "report"               # Validate + log, don't reject
    REPORT_WARNING = "report_warn"  # Validate + log + show warning to consumer
    STRICT = "strict"               # Reject unverified


@dataclass
class ReadinessMetrics:
    """Ecosystem readiness for next enforcement phase."""
    total_receipts: int = 0
    valid_receipts: int = 0
    merkle_present: int = 0
    witnesses_sufficient: int = 0  # >= 2 independent
    diversity_hash_present: int = 0
    fresh_receipts: int = 0  # < 24h old
    
    @property
    def validity_rate(self) -> float:
        return self.valid_receipts / max(self.total_receipts, 1)
    
    @property
    def merkle_adoption(self) -> float:
        return self.merkle_present / max(self.total_receipts, 1)
    
    @property
    def witness_coverage(self) -> float:
        return self.witnesses_sufficient / max(self.total_receipts, 1)


@dataclass
class GraduationGate:
    """Threshold to proceed to next phase."""
    phase: Phase
    min_validity_rate: float
    min_merkle_adoption: float
    min_witness_coverage: float
    min_observation_days: int  # Minimum days in current phase
    
    def check(self, metrics: ReadinessMetrics, days_in_phase: int) -> tuple[bool, list[str]]:
        """Check if gate passes. Returns (passed, blockers)."""
        blockers = []
        if metrics.validity_rate < self.min_validity_rate:
            blockers.append(
                f"Validity {metrics.validity_rate:.1%} < {self.min_validity_rate:.1%}"
            )
        if metrics.merkle_adoption < self.min_merkle_adoption:
            blockers.append(
                f"Merkle adoption {metrics.merkle_adoption:.1%} < {self.min_merkle_adoption:.1%}"
            )
        if metrics.witness_coverage < self.min_witness_coverage:
            blockers.append(
                f"Witness coverage {metrics.witness_coverage:.1%} < {self.min_witness_coverage:.1%}"
            )
        if days_in_phase < self.min_observation_days:
            blockers.append(
                f"Only {days_in_phase}d in phase (need {self.min_observation_days}d)"
            )
        return len(blockers) == 0, blockers


# Chrome CT parallel:
# 2013: RFC 6962 published
# 2015: Chrome starts requiring CT for new EV certs (REPORT for DV)
# 2018: Chrome requires CT for ALL new certs (STRICT)
# 5 years total. Agent ecosystem: 12 months proposed.

GRADUATION_GATES = {
    Phase.REPORT: GraduationGate(
        phase=Phase.REPORT,
        min_validity_rate=0.0,     # No minimum — we're just starting to measure
        min_merkle_adoption=0.0,
        min_witness_coverage=0.0,
        min_observation_days=0,    # Can start immediately
    ),
    Phase.REPORT_WARNING: GraduationGate(
        phase=Phase.REPORT_WARNING,
        min_validity_rate=0.50,    # Half the ecosystem compliant
        min_merkle_adoption=0.60,
        min_witness_coverage=0.40,
        min_observation_days=90,   # 3 months minimum in REPORT
    ),
    Phase.STRICT: GraduationGate(
        phase=Phase.STRICT,
        min_validity_rate=0.85,    # 85% pass rate before we reject
        min_merkle_adoption=0.90,
        min_witness_coverage=0.75,
        min_observation_days=90,   # 3 months in REPORT_WARNING
    ),
}


@dataclass
class PhaseRecord:
    phase: Phase
    started: datetime
    ended: Optional[datetime] = None
    final_metrics: Optional[ReadinessMetrics] = None


class EnforcementGraduator:
    """Manages the PERMISSIVE → REPORT → REPORT_WARNING → STRICT progression."""
    
    PHASE_ORDER = [Phase.PERMISSIVE, Phase.REPORT, Phase.REPORT_WARNING, Phase.STRICT]
    
    def __init__(self, start_phase: Phase = Phase.PERMISSIVE):
        self.current_phase = start_phase
        self.phase_start = datetime.utcnow()
        self.history: list[PhaseRecord] = [
            PhaseRecord(phase=start_phase, started=self.phase_start)
        ]
        self.weekly_reports: list[dict] = []
    
    def days_in_current_phase(self) -> int:
        return (datetime.utcnow() - self.phase_start).days
    
    def evaluate_graduation(self, metrics: ReadinessMetrics) -> dict:
        """Evaluate whether ecosystem is ready for next phase."""
        current_idx = self.PHASE_ORDER.index(self.current_phase)
        
        if current_idx >= len(self.PHASE_ORDER) - 1:
            return {
                "current_phase": self.current_phase.value,
                "next_phase": None,
                "ready": False,
                "message": "Already at STRICT. Maximum enforcement.",
            }
        
        next_phase = self.PHASE_ORDER[current_idx + 1]
        gate = GRADUATION_GATES[next_phase]
        passed, blockers = gate.check(metrics, self.days_in_current_phase())
        
        return {
            "current_phase": self.current_phase.value,
            "next_phase": next_phase.value,
            "days_in_phase": self.days_in_current_phase(),
            "ready": passed,
            "blockers": blockers,
            "metrics": {
                "validity_rate": f"{metrics.validity_rate:.1%}",
                "merkle_adoption": f"{metrics.merkle_adoption:.1%}",
                "witness_coverage": f"{metrics.witness_coverage:.1%}",
            },
        }
    
    def graduate(self, metrics: ReadinessMetrics) -> bool:
        """Attempt to graduate to next phase. Returns True if successful."""
        eval_result = self.evaluate_graduation(metrics)
        if not eval_result["ready"]:
            return False
        
        # Record end of current phase
        self.history[-1].ended = datetime.utcnow()
        self.history[-1].final_metrics = metrics
        
        # Move to next phase
        next_phase = Phase(eval_result["next_phase"])
        self.current_phase = next_phase
        self.phase_start = datetime.utcnow()
        self.history.append(PhaseRecord(phase=next_phase, started=self.phase_start))
        return True
    
    def weekly_gap_report(self, metrics: ReadinessMetrics) -> dict:
        """Generate weekly forcing function report."""
        eval_result = self.evaluate_graduation(metrics)
        report = {
            "week": len(self.weekly_reports) + 1,
            "phase": self.current_phase.value,
            "days_in_phase": self.days_in_current_phase(),
            "ecosystem_readiness": eval_result["metrics"],
            "graduation_ready": eval_result["ready"],
            "blockers": eval_result.get("blockers", []),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.weekly_reports.append(report)
        return report


def simulate_adoption():
    """Simulate ecosystem adoption over 12 months."""
    print("=" * 60)
    print("Enforcement Graduation Simulation (12 months)")
    print("Chrome CT parallel: 5 years → Agent target: 12 months")
    print("=" * 60)
    
    graduator = EnforcementGraduator(start_phase=Phase.PERMISSIVE)
    
    # Simulate monthly snapshots
    # Adoption follows logistic curve: slow start, rapid middle, plateau
    months = [
        # (validity, merkle, witness) — ecosystem adoption rates
        (0.05, 0.03, 0.02),   # Month 1: barely anyone
        (0.12, 0.08, 0.05),   # Month 2: early adopters
        (0.25, 0.20, 0.12),   # Month 3: word spreading
        (0.45, 0.40, 0.25),   # Month 4: momentum (REPORT phase forcing)
        (0.60, 0.55, 0.38),   # Month 5: majority starting
        (0.72, 0.68, 0.50),   # Month 6: gap reports driving action
        (0.80, 0.78, 0.62),   # Month 7: stragglers feeling pressure
        (0.87, 0.86, 0.72),   # Month 8: WARNING labels bite
        (0.91, 0.92, 0.80),   # Month 9: near-universal
        (0.94, 0.95, 0.86),   # Month 10: plateau
        (0.96, 0.97, 0.90),   # Month 11: long tail
        (0.98, 0.98, 0.93),   # Month 12: ready for STRICT
    ]
    
    for month_idx, (validity, merkle, witness) in enumerate(months):
        month = month_idx + 1
        n = 10000
        
        metrics = ReadinessMetrics(
            total_receipts=n,
            valid_receipts=int(n * validity),
            merkle_present=int(n * merkle),
            witnesses_sufficient=int(n * witness),
            diversity_hash_present=int(n * merkle * 0.9),
            fresh_receipts=int(n * 0.95),
        )
        
        # Hack phase_start for simulation
        graduator.phase_start = datetime.utcnow() - timedelta(days=30 * month)
        
        # Try to graduate
        eval_result = graduator.evaluate_graduation(metrics)
        graduated = graduator.graduate(metrics)
        
        phase_marker = " 🎓" if graduated else ""
        print(f"\nMonth {month:2d} | Phase: {graduator.current_phase.value:12s}"
              f" | Valid: {validity:5.1%} | Merkle: {merkle:5.1%}"
              f" | Witness: {witness:5.1%}{phase_marker}")
        
        if eval_result.get("blockers"):
            for b in eval_result["blockers"][:2]:
                print(f"         Blocker: {b}")
    
    print(f"\n{'='*60}")
    print("Phase History:")
    for record in graduator.history:
        end = record.ended.strftime("%Y-%m") if record.ended else "ongoing"
        print(f"  {record.phase.value:12s} → ended {end}")
    
    print(f"\nKey insight: The gap report is the forcing function.")
    print(f"Publishing 'X% of receipts would fail STRICT' weekly")
    print(f"creates market pressure without breaking anything.")
    print(f"Chrome's 'Not Secure' label = same mechanism.")


if __name__ == "__main__":
    simulate_adoption()
