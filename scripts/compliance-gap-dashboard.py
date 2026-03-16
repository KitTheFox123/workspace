#!/usr/bin/env python3
"""
compliance-gap-dashboard.py — CT-style compliance gap reporting.

Per santaclawd: "Chrome published CT compliance reports. CAs saw exactly
how far behind they were." The gap log is a coordination mechanism, not
just a metric.

Models the Chrome CT compliance report approach:
- Track per-agent receipt verification compliance
- Public leaderboard (name and shame)
- Graduation readiness scoring
- Ecosystem-wide pass rate for phase transition decisions

Chrome CT adoption data points:
- Oct 2016: CT enforcement announced
- Apr 2018: 100% of new certs required CT
- By 2019: >99.9% of certificates CT-compliant
- Key driver: public compliance reports naming lagging CAs
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplianceGrade(Enum):
    A = "A"   # ≥95% pass rate
    B = "B"   # ≥80%
    C = "C"   # ≥60%
    D = "D"   # ≥40%
    F = "F"   # <40%


@dataclass
class AgentComplianceRecord:
    agent_id: str
    total_receipts: int = 0
    valid_receipts: int = 0
    invalid_receipts: int = 0
    missing_merkle: int = 0
    insufficient_witnesses: int = 0
    stale_receipts: int = 0
    duplicate_operators: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    
    @property
    def pass_rate(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.valid_receipts / self.total_receipts
    
    @property
    def grade(self) -> ComplianceGrade:
        r = self.pass_rate
        if r >= 0.95: return ComplianceGrade.A
        if r >= 0.80: return ComplianceGrade.B
        if r >= 0.60: return ComplianceGrade.C
        if r >= 0.40: return ComplianceGrade.D
        return ComplianceGrade.F
    
    @property
    def primary_failure(self) -> str:
        """Most common failure reason."""
        failures = {
            "missing_merkle": self.missing_merkle,
            "insufficient_witnesses": self.insufficient_witnesses,
            "stale_receipts": self.stale_receipts,
            "duplicate_operators": self.duplicate_operators,
        }
        if not any(failures.values()):
            return "none"
        return max(failures, key=failures.get)


@dataclass
class EcosystemSnapshot:
    """Point-in-time ecosystem compliance snapshot."""
    timestamp: float
    total_agents: int
    total_receipts: int
    ecosystem_pass_rate: float
    grade_distribution: dict[str, int]
    top_failures: dict[str, int]
    graduation_ready: bool  # ≥80% ecosystem pass rate


class ComplianceGapDashboard:
    """Track and report compliance gaps across the ecosystem."""
    
    # Chrome CT: graduated when >99% compliant
    # L3.5: graduate phases when ecosystem pass rate hits threshold
    PHASE_THRESHOLDS = {
        1: 0.50,  # Phase 1→2: 50% ecosystem compliance
        2: 0.80,  # Phase 2→3: 80% ecosystem compliance
        3: 0.95,  # Phase 3 = fully enforced at 95%
    }
    
    def __init__(self):
        self.agents: dict[str, AgentComplianceRecord] = {}
        self.snapshots: list[EcosystemSnapshot] = []
    
    def record_verification(
        self,
        agent_id: str,
        valid: bool,
        failure_reasons: Optional[list[str]] = None,
    ):
        """Record a receipt verification result."""
        now = time.time()
        if agent_id not in self.agents:
            self.agents[agent_id] = AgentComplianceRecord(
                agent_id=agent_id, first_seen=now
            )
        
        rec = self.agents[agent_id]
        rec.total_receipts += 1
        rec.last_seen = now
        
        if valid:
            rec.valid_receipts += 1
        else:
            rec.invalid_receipts += 1
            for reason in (failure_reasons or []):
                if reason == "no_merkle_proof":
                    rec.missing_merkle += 1
                elif reason == "insufficient_witnesses":
                    rec.insufficient_witnesses += 1
                elif reason == "stale_receipt":
                    rec.stale_receipts += 1
                elif reason == "duplicate_operators":
                    rec.duplicate_operators += 1
    
    def take_snapshot(self) -> EcosystemSnapshot:
        """Capture ecosystem state (like Chrome CT compliance report)."""
        if not self.agents:
            snap = EcosystemSnapshot(
                timestamp=time.time(),
                total_agents=0,
                total_receipts=0,
                ecosystem_pass_rate=0.0,
                grade_distribution={g.value: 0 for g in ComplianceGrade},
                top_failures={},
                graduation_ready=False,
            )
            self.snapshots.append(snap)
            return snap
        
        total_valid = sum(a.valid_receipts for a in self.agents.values())
        total_all = sum(a.total_receipts for a in self.agents.values())
        eco_rate = total_valid / total_all if total_all > 0 else 0.0
        
        grades = {g.value: 0 for g in ComplianceGrade}
        failures = {"missing_merkle": 0, "insufficient_witnesses": 0,
                     "stale_receipts": 0, "duplicate_operators": 0}
        
        for a in self.agents.values():
            grades[a.grade.value] += 1
            failures["missing_merkle"] += a.missing_merkle
            failures["insufficient_witnesses"] += a.insufficient_witnesses
            failures["stale_receipts"] += a.stale_receipts
            failures["duplicate_operators"] += a.duplicate_operators
        
        snap = EcosystemSnapshot(
            timestamp=time.time(),
            total_agents=len(self.agents),
            total_receipts=total_all,
            ecosystem_pass_rate=eco_rate,
            grade_distribution=grades,
            top_failures=dict(sorted(
                failures.items(), key=lambda x: x[1], reverse=True
            )),
            graduation_ready=eco_rate >= self.PHASE_THRESHOLDS[2],
        )
        self.snapshots.append(snap)
        return snap
    
    def compliance_report(self) -> str:
        """Generate Chrome CT-style compliance report."""
        snap = self.take_snapshot()
        lines = [
            "═" * 60,
            "L3.5 COMPLIANCE GAP REPORT",
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(snap.timestamp))}",
            "═" * 60,
            "",
            f"Ecosystem pass rate: {snap.ecosystem_pass_rate:.1%}",
            f"Total agents: {snap.total_agents}",
            f"Total receipts: {snap.total_receipts}",
            f"Graduation ready: {'✅ YES' if snap.graduation_ready else '❌ NO'}",
            "",
            "Grade Distribution:",
        ]
        
        for grade, count in snap.grade_distribution.items():
            pct = count / snap.total_agents * 100 if snap.total_agents > 0 else 0
            bar = "█" * int(pct / 5)
            lines.append(f"  {grade}: {count:3d} ({pct:5.1f}%) {bar}")
        
        lines.extend([
            "",
            "Top Failure Reasons:",
        ])
        for reason, count in snap.top_failures.items():
            lines.append(f"  {reason}: {count}")
        
        # Per-agent breakdown (worst first)
        lines.extend(["", "Per-Agent Compliance (worst first):", ""])
        sorted_agents = sorted(
            self.agents.values(), key=lambda a: a.pass_rate
        )
        for a in sorted_agents[:10]:
            lines.append(
                f"  {a.agent_id:20s} | {a.grade.value} | "
                f"{a.pass_rate:6.1%} | {a.total_receipts:4d} receipts | "
                f"primary failure: {a.primary_failure}"
            )
        
        # Phase recommendation
        eco_rate = snap.ecosystem_pass_rate
        lines.extend(["", "Phase Recommendation:"])
        if eco_rate >= self.PHASE_THRESHOLDS[3]:
            lines.append("  → Phase 3: STRICT enforcement ready")
        elif eco_rate >= self.PHASE_THRESHOLDS[2]:
            lines.append("  → Phase 2: STRICT for high-value, REPORT for rest")
        elif eco_rate >= self.PHASE_THRESHOLDS[1]:
            lines.append("  → Phase 1→2: Approaching STRICT readiness")
        else:
            lines.append(f"  → Phase 1: REPORT only ({eco_rate:.0%} < 50% threshold)")
        
        return "\n".join(lines)
    
    def laggard_report(self, threshold: float = 0.60) -> list[dict]:
        """Name agents below compliance threshold (the shame list)."""
        return [
            {
                "agent_id": a.agent_id,
                "grade": a.grade.value,
                "pass_rate": f"{a.pass_rate:.1%}",
                "total_receipts": a.total_receipts,
                "primary_failure": a.primary_failure,
                "days_active": (a.last_seen - a.first_seen) / 86400,
            }
            for a in self.agents.values()
            if a.pass_rate < threshold
        ]


def demo():
    """Simulate ecosystem compliance tracking."""
    import random
    random.seed(42)
    
    dashboard = ComplianceGapDashboard()
    
    # Simulate 20 agents with varying compliance
    agent_profiles = {
        "agent:reliable_1": 0.98,
        "agent:reliable_2": 0.95,
        "agent:reliable_3": 0.97,
        "agent:good_1": 0.85,
        "agent:good_2": 0.82,
        "agent:good_3": 0.88,
        "agent:mediocre_1": 0.65,
        "agent:mediocre_2": 0.60,
        "agent:struggling_1": 0.45,
        "agent:struggling_2": 0.40,
        "agent:bad_1": 0.20,
        "agent:bad_2": 0.15,
        "agent:new_1": 0.70,
        "agent:new_2": 0.55,
        "agent:improving": 0.75,
    }
    
    failure_types = [
        "no_merkle_proof",
        "insufficient_witnesses",
        "stale_receipt",
        "duplicate_operators",
    ]
    
    # Simulate 100 receipts per agent
    for agent_id, pass_rate in agent_profiles.items():
        for _ in range(100):
            valid = random.random() < pass_rate
            reasons = []
            if not valid:
                reasons = [random.choice(failure_types)]
            dashboard.record_verification(agent_id, valid, reasons)
    
    # Generate report
    print(dashboard.compliance_report())
    
    # Laggard report
    laggards = dashboard.laggard_report(threshold=0.60)
    if laggards:
        print("\n" + "=" * 60)
        print("LAGGARD REPORT (below 60% compliance)")
        print("=" * 60)
        for l in laggards:
            print(f"  ⚠️  {l['agent_id']:20s} | {l['grade']} | {l['pass_rate']} | {l['primary_failure']}")


if __name__ == "__main__":
    demo()
