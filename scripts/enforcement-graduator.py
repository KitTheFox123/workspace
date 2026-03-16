#!/usr/bin/env python3
"""
enforcement-graduator.py — Chrome CT-style graduated enforcement for L3.5 receipts.

Per santaclawd's insight: "mandating Merkle receipts kills 90% of current agents day one."
Chrome solved this: 2 years REPORT mode before STRICT. HTTPS "Not Secure" had 3 phases.

Chrome CT timeline:
  - RFC 6962 published: June 2013
  - Chrome EV enforcement: Jan 2015
  - Chrome full enforcement: April 2018 (Chrome 68)
  - Total: ~5 years proposal to full enforcement

Chrome HTTPS "Not Secure" timeline:
  - Chrome 56 (Jan 2017): Warn on password pages
  - Chrome 62 (Oct 2017): Warn on any input field  
  - Chrome 68 (Jul 2018): All HTTP = "Not Secure"
  - 18 months, 3 phases, pass-rate-gated

Key insight: publish gap reports (name CAs by compliance rate). 
Public shaming + clear deadline = adoption. Spec alone = shelf ware.

Two forcing functions needed:
  1. Supply: Free receipt libraries (= Let's Encrypt for trust)
  2. Demand: Client enforcement (= Chrome "Not Secure" label)
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    PERMISSIVE = "permissive"  # Accept everything, no logging
    REPORT = "report"          # Accept everything, log violations
    WARN = "warn"              # Accept but surface warning to consumer
    STRICT = "strict"          # Reject unverified by default


@dataclass
class PhaseConfig:
    phase: Phase
    min_days: int                    # Minimum days at this phase
    min_receipts_checked: int        # Minimum volume before graduation eligible
    max_gap_to_graduate: float       # Enforcement gap must be below this to graduate
    consecutive_checks: int = 10     # Consecutive checks above threshold needed
    description: str = ""


@dataclass
class GapReport:
    """Public compliance report (Chrome CT model: name providers by compliance rate)."""
    phase: str
    total_checked: int
    total_valid: int
    enforcement_gap: float  # Fraction that would fail STRICT
    worst_agents: list[tuple[str, float]]  # (agent_id, failure_rate)
    generated_at: float = 0.0
    
    def summary(self) -> str:
        lines = [
            f"=== Enforcement Gap Report ({self.phase}) ===",
            f"Checked: {self.total_checked}",
            f"Valid: {self.total_valid} ({self.total_valid/max(self.total_checked,1):.1%})",
            f"Gap: {self.enforcement_gap:.1%} would fail STRICT",
        ]
        if self.worst_agents:
            lines.append("Worst agents:")
            for agent, rate in self.worst_agents[:5]:
                lines.append(f"  {agent}: {rate:.0%} failure rate")
        return "\n".join(lines)


@dataclass
class ReceiptCheck:
    """Result of checking a single receipt."""
    receipt_id: str
    agent_id: str
    valid: bool
    reasons: list[str] = field(default_factory=list)


class EnforcementGraduator:
    """
    Chrome CT-style graduated enforcement rollout.
    
    Phase progression:
      PERMISSIVE → REPORT → WARN → STRICT
    
    Each phase has:
      - Minimum duration (can't rush)
      - Minimum volume (need statistical significance)
      - Maximum gap (ecosystem must be ready)
      - Consecutive checks (not just one good day)
    
    Graduation is pass-rate-gated AND deadline-gated.
    Per santaclawd: REPORT without a committed STRICT date = permanent opt-out.
    Chrome announced April 2018 enforcement in October 2016 (18 months).
    Gate OR deadline, whichever comes first.
    """
    
    PHASES = [
        PhaseConfig(
            Phase.PERMISSIVE, min_days=30, min_receipts_checked=100,
            max_gap_to_graduate=1.0, consecutive_checks=1,
            description="Collect baseline. No enforcement. Measure current state."
        ),
        PhaseConfig(
            Phase.REPORT, min_days=90, min_receipts_checked=1000,
            max_gap_to_graduate=0.20, consecutive_checks=10,
            description="Accept all, log violations. Publish gap reports weekly."
        ),
        PhaseConfig(
            Phase.WARN, min_days=90, min_receipts_checked=5000,
            max_gap_to_graduate=0.05, consecutive_checks=20,
            description="Accept but surface 'Unverified Receipt' to consumers."
        ),
        PhaseConfig(
            Phase.STRICT, min_days=0, min_receipts_checked=0,
            max_gap_to_graduate=0.0, consecutive_checks=0,
            description="Reject unverified. Opt-out logged but available."
        ),
    ]
    
    def __init__(self, strict_deadline_days: int = 540):
        """
        Args:
            strict_deadline_days: Hard deadline for STRICT enforcement (default 540 = 18 months).
                Per santaclawd: REPORT without committed STRICT date = permanent opt-out.
                Gate OR deadline, whichever comes first.
        """
        self.current_phase_idx = 0
        self.phase_start_time = time.time()
        self.creation_time = time.time()
        self.strict_deadline = time.time() + strict_deadline_days * 86400
        self.checks: list[ReceiptCheck] = []
        self.agent_stats: dict[str, dict] = {}  # agent_id → {checked, failed}
        self.consecutive_above = 0
        self.graduation_history: list[dict] = []
    
    @property
    def current_config(self) -> PhaseConfig:
        return self.PHASES[self.current_phase_idx]
    
    @property
    def current_phase(self) -> Phase:
        return self.current_config.phase
    
    @property
    def days_in_phase(self) -> float:
        return (time.time() - self.phase_start_time) / 86400
    
    def record_check(self, receipt_id: str, agent_id: str, valid: bool, 
                     reasons: list[str] = None) -> dict:
        """Record a receipt check and return enforcement decision."""
        check = ReceiptCheck(receipt_id, agent_id, valid, reasons or [])
        self.checks.append(check)
        
        # Track per-agent stats
        if agent_id not in self.agent_stats:
            self.agent_stats[agent_id] = {"checked": 0, "failed": 0}
        self.agent_stats[agent_id]["checked"] += 1
        if not valid:
            self.agent_stats[agent_id]["failed"] += 1
        
        # Check graduation
        graduation = self._check_graduation()
        
        # Enforcement decision based on current phase
        if self.current_phase == Phase.STRICT:
            accepted = valid
        elif self.current_phase == Phase.WARN:
            accepted = True  # Accept but warn
        else:
            accepted = True  # Accept silently or with log
        
        return {
            "accepted": accepted,
            "phase": self.current_phase.value,
            "valid": valid,
            "graduated": graduation,
            "warning": not valid and self.current_phase == Phase.WARN,
        }
    
    def _check_graduation(self) -> Optional[str]:
        """Check if ready to graduate. Returns new phase name or None."""
        if self.current_phase_idx >= len(self.PHASES) - 1:
            return None  # Already at STRICT
        
        config = self.current_config
        gap = self.enforcement_gap
        
        # Check all graduation criteria
        if (len(self.checks) >= config.min_receipts_checked
                and self.days_in_phase >= config.min_days
                and gap <= config.max_gap_to_graduate):
            self.consecutive_above += 1
        else:
            self.consecutive_above = 0
        
        if self.consecutive_above >= config.consecutive_checks:
            return self._graduate()
        
        # Hard deadline: gate OR deadline, whichever comes first
        # Per santaclawd: REPORT without STRICT date = permanent opt-out
        if time.time() >= self.strict_deadline and self.current_phase != Phase.STRICT:
            while self.current_phase_idx < len(self.PHASES) - 1:
                self._graduate()
            return self.current_phase.value
        
        return None
    
    def _graduate(self) -> str:
        """Move to next phase."""
        old = self.current_phase.value
        self.graduation_history.append({
            "from": old,
            "to": self.PHASES[self.current_phase_idx + 1].phase.value,
            "gap_at_graduation": self.enforcement_gap,
            "receipts_checked": len(self.checks),
            "days_in_phase": self.days_in_phase,
            "timestamp": time.time(),
        })
        self.current_phase_idx += 1
        self.phase_start_time = time.time()
        self.consecutive_above = 0
        self.checks = []
        self.agent_stats = {}
        return self.current_phase.value
    
    @property
    def enforcement_gap(self) -> float:
        """Fraction of receipts that would fail STRICT."""
        if not self.checks:
            return 1.0
        failed = sum(1 for c in self.checks if not c.valid)
        return failed / len(self.checks)
    
    def gap_report(self) -> GapReport:
        """Generate public compliance report (Chrome CT model)."""
        total = len(self.checks)
        valid = sum(1 for c in self.checks if c.valid)
        
        # Worst agents by failure rate (min 5 checks)
        worst = []
        for agent_id, stats in self.agent_stats.items():
            if stats["checked"] >= 5:
                rate = stats["failed"] / stats["checked"]
                if rate > 0:
                    worst.append((agent_id, rate))
        worst.sort(key=lambda x: -x[1])
        
        return GapReport(
            phase=self.current_phase.value,
            total_checked=total,
            total_valid=valid,
            enforcement_gap=self.enforcement_gap,
            worst_agents=worst[:10],
            generated_at=time.time(),
        )
    
    def status(self) -> dict:
        """Current graduation status."""
        config = self.current_config
        blockers = []
        
        if len(self.checks) < config.min_receipts_checked:
            blockers.append(f"volume: {len(self.checks)}/{config.min_receipts_checked}")
        if self.days_in_phase < config.min_days:
            blockers.append(f"duration: {self.days_in_phase:.0f}/{config.min_days} days")
        if self.enforcement_gap > config.max_gap_to_graduate:
            blockers.append(f"gap: {self.enforcement_gap:.1%} > {config.max_gap_to_graduate:.0%}")
        if self.consecutive_above < config.consecutive_checks:
            blockers.append(f"consecutive: {self.consecutive_above}/{config.consecutive_checks}")
        
        return {
            "phase": self.current_phase.value,
            "description": config.description,
            "phase_index": f"{self.current_phase_idx + 1}/{len(self.PHASES)}",
            "days_in_phase": f"{self.days_in_phase:.1f}",
            "receipts_checked": len(self.checks),
            "enforcement_gap": f"{self.enforcement_gap:.1%}",
            "ready_to_graduate": len(blockers) == 0 and self.current_phase_idx < len(self.PHASES) - 1,
            "blockers": blockers,
            "history": self.graduation_history,
            "strict_deadline": time.strftime("%Y-%m-%d", time.localtime(self.strict_deadline)),
            "days_to_deadline": f"{(self.strict_deadline - time.time()) / 86400:.0f}",
        }


def demo():
    """Simulate enforcement graduation."""
    import random
    
    print("=" * 60)
    print("ENFORCEMENT GRADUATION SIMULATION")
    print("Chrome CT model applied to L3.5 receipts")
    print("=" * 60)
    
    grad = EnforcementGraduator()
    
    # Simulate 4 phases of ecosystem maturation
    scenarios = [
        ("Early ecosystem (70% valid)", 0.70, 150),
        ("Improving (85% valid)", 0.85, 200),
        ("Maturing (92% valid)", 0.92, 300),
        ("Production-ready (98% valid)", 0.98, 500),
    ]
    
    for scenario_name, valid_rate, count in scenarios:
        print(f"\n--- {scenario_name} ---")
        
        # Fast-forward time for demo
        grad.phase_start_time = time.time() - 100 * 86400
        
        for i in range(count):
            valid = random.random() < valid_rate
            agent = f"agent:{random.choice(['alpha', 'beta', 'gamma', 'delta', 'epsilon'])}"
            reasons = [] if valid else ["missing_merkle_proof"]
            result = grad.record_check(f"r{i}", agent, valid, reasons)
            
            if result.get("graduated"):
                print(f"  🎓 GRADUATED to {result['graduated']}!")
        
        status = grad.status()
        print(f"  Phase: {status['phase']} ({status['phase_index']})")
        print(f"  Gap: {status['enforcement_gap']}")
        print(f"  Receipts: {status['receipts_checked']}")
        if status['blockers']:
            print(f"  Blockers: {status['blockers']}")
        if status['ready_to_graduate']:
            print(f"  ✅ Ready to graduate!")
    
    # Final gap report
    report = grad.gap_report()
    print(f"\n{report.summary()}")
    
    # Show graduation history
    if grad.graduation_history:
        print(f"\n📜 Graduation History:")
        for h in grad.graduation_history:
            print(f"  {h['from']} → {h['to']} "
                  f"(gap={h['gap_at_graduation']:.1%}, "
                  f"receipts={h['receipts_checked']}, "
                  f"days={h['days_in_phase']:.0f})")


if __name__ == "__main__":
    demo()
