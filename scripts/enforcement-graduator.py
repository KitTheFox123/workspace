#!/usr/bin/env python3
"""
enforcement-graduator.py — Chrome CT enforcement graduation model for L3.5.

santaclawd's insight: "mandating Merkle receipts kills 90% of current agents day one."
Chrome CT solution: 3-phase graduation over 18 months.

Phase model (Chrome HTTPS timeline):
  Phase 1 (REPORT): Log violations, accept everything. Build supply.
    Chrome 56 (Jan 2017): warn on password pages only.
  Phase 2 (WARN): Flag unverified to consumers. Create demand pressure.
    Chrome 62 (Oct 2017): warn on any input field.
  Phase 3 (ENFORCE): Reject unverified by default. Opt-out available.
    Chrome 68 (Jul 2018): all HTTP = "Not Secure."

Graduation gates: advance when pass_rate exceeds threshold.
Gap log = public coordination mechanism (Chrome published CA compliance rates).
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    REPORT = "report"      # Accept all, log violations
    WARN = "warn"          # Accept but flag to consumer
    ENFORCE = "enforce"    # Reject unverified by default


@dataclass
class GraduationGate:
    """Conditions to advance to next phase."""
    min_pass_rate: float         # % of receipts that pass verification
    min_supply_count: int        # Minimum verified receipt supply
    min_duration_days: int       # Minimum time in current phase
    phase_from: Phase
    phase_to: Phase


@dataclass
class ComplianceRecord:
    agent_id: str
    total_receipts: int = 0
    verified_receipts: int = 0
    violations: list[str] = field(default_factory=list)
    
    @property
    def pass_rate(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.verified_receipts / self.total_receipts


@dataclass 
class EcosystemSnapshot:
    timestamp: float
    phase: Phase
    total_agents: int
    compliant_agents: int
    overall_pass_rate: float
    top_violators: list[tuple[str, float]]  # (agent_id, pass_rate)
    
    @property
    def compliance_rate(self) -> float:
        if self.total_agents == 0:
            return 0.0
        return self.compliant_agents / self.total_agents


class EnforcementGraduator:
    """Manages phased enforcement rollout."""
    
    # Chrome CT graduation gates
    DEFAULT_GATES = [
        GraduationGate(
            min_pass_rate=0.50,       # 50% pass rate
            min_supply_count=100,     # 100 verified receipts exist
            min_duration_days=90,     # 90 days minimum
            phase_from=Phase.REPORT,
            phase_to=Phase.WARN,
        ),
        GraduationGate(
            min_pass_rate=0.80,       # 80% pass rate
            min_supply_count=1000,    # 1000 verified receipts
            min_duration_days=180,    # 180 days minimum
            phase_from=Phase.WARN,
            phase_to=Phase.ENFORCE,
        ),
    ]
    
    def __init__(self, gates: Optional[list[GraduationGate]] = None):
        self.gates = gates or self.DEFAULT_GATES
        self.current_phase = Phase.REPORT
        self.phase_start = time.time()
        self.records: dict[str, ComplianceRecord] = {}
        self.snapshots: list[EcosystemSnapshot] = []
    
    def record_receipt(self, agent_id: str, verified: bool, 
                       violation: Optional[str] = None):
        """Record a receipt verification result."""
        if agent_id not in self.records:
            self.records[agent_id] = ComplianceRecord(agent_id=agent_id)
        rec = self.records[agent_id]
        rec.total_receipts += 1
        if verified:
            rec.verified_receipts += 1
        if violation:
            rec.violations.append(violation)
    
    def should_accept(self, verified: bool) -> tuple[bool, str]:
        """Decide whether to accept a receipt based on current phase."""
        if self.current_phase == Phase.REPORT:
            return True, "REPORT: accepted (violation logged)" if not verified else "REPORT: accepted (valid)"
        elif self.current_phase == Phase.WARN:
            msg = "WARN: ⚠️ unverified receipt" if not verified else "WARN: verified"
            return True, msg
        else:  # ENFORCE
            if verified:
                return True, "ENFORCE: accepted"
            return False, "ENFORCE: ❌ rejected (unverified)"
    
    def check_graduation(self) -> Optional[Phase]:
        """Check if conditions are met to advance to next phase."""
        for gate in self.gates:
            if gate.phase_from != self.current_phase:
                continue
            
            # Check duration
            days_in_phase = (time.time() - self.phase_start) / 86400
            if days_in_phase < gate.min_duration_days:
                continue
            
            # Check pass rate
            total = sum(r.total_receipts for r in self.records.values())
            verified = sum(r.verified_receipts for r in self.records.values())
            pass_rate = verified / total if total > 0 else 0
            
            if pass_rate < gate.min_pass_rate:
                continue
            
            # Check supply
            if verified < gate.min_supply_count:
                continue
            
            return gate.phase_to
        
        return None
    
    def graduate(self, new_phase: Phase):
        """Advance to new phase."""
        self.current_phase = new_phase
        self.phase_start = time.time()
    
    def take_snapshot(self) -> EcosystemSnapshot:
        """Generate public compliance report (Chrome CT model)."""
        total = sum(r.total_receipts for r in self.records.values())
        verified = sum(r.verified_receipts for r in self.records.values())
        
        # Compliant = pass_rate >= threshold for current phase
        threshold = 0.5 if self.current_phase == Phase.REPORT else 0.8
        compliant = sum(
            1 for r in self.records.values() 
            if r.pass_rate >= threshold
        )
        
        # Top violators (public shaming)
        violators = sorted(
            [(r.agent_id, r.pass_rate) for r in self.records.values()],
            key=lambda x: x[1]
        )[:5]
        
        snapshot = EcosystemSnapshot(
            timestamp=time.time(),
            phase=self.current_phase,
            total_agents=len(self.records),
            compliant_agents=compliant,
            overall_pass_rate=verified / total if total > 0 else 0,
            top_violators=violators,
        )
        self.snapshots.append(snapshot)
        return snapshot


def demo():
    """Simulate enforcement graduation with ecosystem data."""
    grad = EnforcementGraduator()
    
    # Simulate 3 phases of ecosystem growth
    scenarios = [
        {
            "phase_label": "Phase 1: REPORT (early adoption)",
            "agents": {
                "agent:reliable": (50, 48),    # 96% pass
                "agent:learning": (50, 25),    # 50% pass  
                "agent:legacy": (50, 5),       # 10% pass
                "agent:new": (20, 18),         # 90% pass
            }
        },
        {
            "phase_label": "Phase 2: WARN (pressure building)",
            "agents": {
                "agent:reliable": (100, 98),   # 98% pass
                "agent:learning": (100, 75),   # 75% pass (improved!)
                "agent:legacy": (100, 60),     # 60% pass (improving)
                "agent:new": (100, 95),        # 95% pass
                "agent:newcomer": (50, 45),    # 90% pass
            }
        },
        {
            "phase_label": "Phase 3: ENFORCE (compliance)",
            "agents": {
                "agent:reliable": (200, 198),  # 99% pass
                "agent:learning": (200, 185),  # 92.5% pass
                "agent:legacy": (200, 170),    # 85% pass
                "agent:new": (200, 196),       # 98% pass
                "agent:newcomer": (200, 190),  # 95% pass
            }
        },
    ]
    
    for i, scenario in enumerate(scenarios):
        print(f"\n{'='*60}")
        print(f"{scenario['phase_label']}")
        print(f"Current enforcement: {grad.current_phase.value.upper()}")
        print(f"{'='*60}")
        
        # Record receipts
        grad.records.clear()
        for agent_id, (total, verified) in scenario["agents"].items():
            for j in range(total):
                is_verified = j < verified
                violation = None if is_verified else "missing_merkle_proof"
                grad.record_receipt(agent_id, is_verified, violation)
        
        # Take snapshot
        snap = grad.take_snapshot()
        print(f"\n  📊 Compliance Report:")
        print(f"    Agents: {snap.total_agents}")
        print(f"    Compliant: {snap.compliant_agents}/{snap.total_agents} "
              f"({snap.compliance_rate:.0%})")
        print(f"    Overall pass rate: {snap.overall_pass_rate:.1%}")
        print(f"\n  Bottom 5 (public gap log):")
        for agent_id, rate in snap.top_violators:
            status = "✅" if rate >= 0.8 else "⚠️" if rate >= 0.5 else "❌"
            print(f"    {status} {agent_id}: {rate:.0%}")
        
        # Test acceptance
        print(f"\n  Receipt decisions ({grad.current_phase.value}):")
        for verified in [True, False]:
            accepted, msg = grad.should_accept(verified)
            print(f"    {'verified' if verified else 'unverified'}: {msg}")
        
        # Simulate graduation (override time check for demo)
        if i < 2:
            next_phase = Phase.WARN if i == 0 else Phase.ENFORCE
            grad.graduate(next_phase)
            print(f"\n  ⬆️ Graduating to {next_phase.value.upper()}")
    
    # Summary
    print(f"\n{'='*60}")
    print("GRADUATION TIMELINE (Chrome CT parallel)")
    print(f"{'='*60}")
    print("  Phase 1 REPORT  → Chrome 56 (Jan 2017): warn passwords only")
    print("  Phase 2 WARN    → Chrome 62 (Oct 2017): warn all inputs")
    print("  Phase 3 ENFORCE → Chrome 68 (Jul 2018): all HTTP = Not Secure")
    print("  ")
    print("  Key insight: graduation gates are DATA-DRIVEN.")
    print("  Advance when ecosystem pass_rate crosses threshold.")
    print("  Gap log = public coordination. CAs fixed infra because")
    print("  Chrome published who was behind.")
    print("  ")
    print("  L3.5 equivalent:")
    print("  REPORT (log)  → WARN (flag)  → ENFORCE (reject)")
    print("  50% pass rate → 80% pass rate → default-reject")
    print("  90 days min   → 180 days min  → permanent")


if __name__ == "__main__":
    demo()
