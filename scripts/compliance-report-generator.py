#!/usr/bin/env python3
"""
compliance-report-generator.py — CT-style compliance reporting for agent trust receipts.

Per santaclawd: "Chrome published CT compliance reports. CAs saw exactly how far 
behind they were." The gap log IS the coordination mechanism.

Chrome CT compliance reports named CAs by non-compliance rate, published quarterly.
This drove adoption faster than any spec mandate. Public accountability > private enforcement.

Design:
- Track per-agent receipt compliance (Merkle proofs, witness diversity, freshness)
- Generate public compliance reports (name agents by compliance rate)  
- Grade agents A-F based on receipt quality
- Track improvement over time (are agents graduating from F→A?)
"""

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplianceGrade(Enum):
    A = "A"  # 95%+ valid receipts
    B = "B"  # 80-95%
    C = "C"  # 60-80%
    D = "D"  # 40-60%
    F = "F"  # <40%


class ViolationType(Enum):
    NO_MERKLE_PROOF = "no_merkle_proof"
    STALE_RECEIPT = "stale_receipt"
    SINGLE_WITNESS = "single_witness"
    SAME_ORG_WITNESSES = "same_org_witnesses"
    NO_DIVERSITY_HASH = "no_diversity_hash"
    MISSING_TIMESTAMP = "missing_timestamp"


@dataclass
class AgentComplianceRecord:
    agent_id: str
    total_receipts: int = 0
    valid_receipts: int = 0
    violations: dict = field(default_factory=lambda: defaultdict(int))
    first_seen: float = 0.0
    last_seen: float = 0.0
    grade_history: list = field(default_factory=list)
    
    @property
    def compliance_rate(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.valid_receipts / self.total_receipts
    
    @property
    def grade(self) -> ComplianceGrade:
        rate = self.compliance_rate
        if rate >= 0.95:
            return ComplianceGrade.A
        elif rate >= 0.80:
            return ComplianceGrade.B
        elif rate >= 0.60:
            return ComplianceGrade.C
        elif rate >= 0.40:
            return ComplianceGrade.D
        else:
            return ComplianceGrade.F
    
    @property
    def top_violation(self) -> Optional[str]:
        if not self.violations:
            return None
        return max(self.violations, key=self.violations.get)
    
    @property
    def improving(self) -> Optional[bool]:
        """Is the agent trending better? Compare last 2 grade snapshots."""
        if len(self.grade_history) < 2:
            return None
        grades = list(ComplianceGrade)
        prev = grades.index(self.grade_history[-2])
        curr = grades.index(self.grade_history[-1])
        return curr < prev  # Lower index = better grade


@dataclass
class ComplianceReport:
    """Quarterly compliance report, Chrome CT style."""
    report_id: str
    period_start: float
    period_end: float
    total_agents: int
    total_receipts: int
    overall_compliance: float
    grade_distribution: dict  # Grade → count
    worst_offenders: list  # Top 10 by violation count
    most_improved: list  # Top 5 by grade improvement
    violation_breakdown: dict  # ViolationType → count
    generated_at: float = 0.0


class ComplianceReportGenerator:
    """Generate and publish CT-style compliance reports."""
    
    def __init__(self):
        self.records: dict[str, AgentComplianceRecord] = {}
        self.reports: list[ComplianceReport] = []
    
    def record_receipt(self, agent_id: str, valid: bool,
                       violations: list[ViolationType] = None):
        """Record a receipt check result."""
        now = time.time()
        if agent_id not in self.records:
            self.records[agent_id] = AgentComplianceRecord(
                agent_id=agent_id, first_seen=now
            )
        
        rec = self.records[agent_id]
        rec.total_receipts += 1
        rec.last_seen = now
        if valid:
            rec.valid_receipts += 1
        if violations:
            for v in violations:
                rec.violations[v.value] += 1
    
    def snapshot_grades(self):
        """Take a grade snapshot for trend tracking."""
        for rec in self.records.values():
            rec.grade_history.append(rec.grade)
    
    def generate_report(self, period_start: float, period_end: float) -> ComplianceReport:
        """Generate a compliance report for a time period."""
        self.snapshot_grades()
        
        # Grade distribution
        grade_dist = defaultdict(int)
        for rec in self.records.values():
            grade_dist[rec.grade.value] += 1
        
        # Overall compliance
        total_valid = sum(r.valid_receipts for r in self.records.values())
        total_all = sum(r.total_receipts for r in self.records.values())
        overall = total_valid / total_all if total_all > 0 else 0.0
        
        # Worst offenders (most violations, lowest compliance)
        sorted_by_compliance = sorted(
            self.records.values(),
            key=lambda r: r.compliance_rate
        )
        worst = [
            {
                "agent_id": r.agent_id,
                "compliance": f"{r.compliance_rate:.1%}",
                "grade": r.grade.value,
                "total": r.total_receipts,
                "top_violation": r.top_violation,
            }
            for r in sorted_by_compliance[:10]
            if r.total_receipts >= 5  # Minimum sample
        ]
        
        # Most improved
        improved = [
            {
                "agent_id": r.agent_id,
                "improving": r.improving,
                "current_grade": r.grade.value,
                "receipts": r.total_receipts,
            }
            for r in self.records.values()
            if r.improving is True
        ][:5]
        
        # Violation breakdown
        all_violations = defaultdict(int)
        for rec in self.records.values():
            for v_type, count in rec.violations.items():
                all_violations[v_type] += count
        
        report = ComplianceReport(
            report_id=hashlib.sha256(
                f"{period_start}:{period_end}".encode()
            ).hexdigest()[:12],
            period_start=period_start,
            period_end=period_end,
            total_agents=len(self.records),
            total_receipts=total_all,
            overall_compliance=overall,
            grade_distribution=dict(grade_dist),
            worst_offenders=worst,
            most_improved=improved,
            violation_breakdown=dict(all_violations),
            generated_at=time.time(),
        )
        
        self.reports.append(report)
        return report
    
    def format_report(self, report: ComplianceReport) -> str:
        """Format report as human-readable text."""
        lines = [
            f"{'='*60}",
            f"AGENT TRUST RECEIPT COMPLIANCE REPORT",
            f"Report ID: {report.report_id}",
            f"{'='*60}",
            f"",
            f"📊 Summary",
            f"  Agents tracked: {report.total_agents}",
            f"  Receipts checked: {report.total_receipts}",
            f"  Overall compliance: {report.overall_compliance:.1%}",
            f"",
            f"📈 Grade Distribution",
        ]
        
        for grade in ["A", "B", "C", "D", "F"]:
            count = report.grade_distribution.get(grade, 0)
            pct = count / report.total_agents * 100 if report.total_agents > 0 else 0
            bar = "█" * int(pct / 2)
            lines.append(f"  {grade}: {count:3d} ({pct:5.1f}%) {bar}")
        
        lines.append(f"")
        lines.append(f"⚠️  Top Violations")
        for v_type, count in sorted(
            report.violation_breakdown.items(),
            key=lambda x: -x[1]
        )[:5]:
            lines.append(f"  {v_type}: {count}")
        
        if report.worst_offenders:
            lines.append(f"")
            lines.append(f"🔴 Lowest Compliance (min 5 receipts)")
            for off in report.worst_offenders[:5]:
                lines.append(
                    f"  {off['agent_id']}: {off['compliance']} "
                    f"(grade {off['grade']}, {off['total']} receipts, "
                    f"top issue: {off['top_violation']})"
                )
        
        if report.most_improved:
            lines.append(f"")
            lines.append(f"🟢 Most Improved")
            for imp in report.most_improved:
                lines.append(
                    f"  {imp['agent_id']}: now grade {imp['current_grade']} ↑"
                )
        
        lines.extend([
            f"",
            f"{'='*60}",
            f"Generated at: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(report.generated_at))}",
            f"Model: Chrome CT Compliance Reports (quarterly, public)",
            f"Principle: Public accountability > private enforcement",
        ])
        
        return "\n".join(lines)


def demo():
    """Simulate agent compliance tracking and report generation."""
    gen = ComplianceReportGenerator()
    now = time.time()
    
    # Simulate agent receipt data
    agents = {
        "agent:reliable":    (50, 49, []),  # 98% — A
        "agent:good":        (40, 35, [ViolationType.STALE_RECEIPT] * 5),  # 87% — B
        "agent:mediocre":    (30, 20, [ViolationType.NO_DIVERSITY_HASH] * 8 + [ViolationType.SINGLE_WITNESS] * 2),
        "agent:struggling":  (25, 12, [ViolationType.NO_MERKLE_PROOF] * 10 + [ViolationType.SAME_ORG_WITNESSES] * 3),
        "agent:failing":     (20, 5,  [ViolationType.NO_MERKLE_PROOF] * 12 + [ViolationType.SINGLE_WITNESS] * 3),
        "agent:new":         (3, 3,   []),  # Too few to list
    }
    
    for agent_id, (total, valid, violations) in agents.items():
        for i in range(valid):
            gen.record_receipt(agent_id, valid=True)
        for i in range(total - valid):
            gen.record_receipt(agent_id, valid=False)
        for v in violations:
            gen.records[agent_id].violations[v.value] += 1
    
    # First snapshot
    gen.snapshot_grades()
    
    # Simulate improvement: agent:struggling improves
    for _ in range(20):
        gen.record_receipt("agent:struggling", valid=True)
    
    # Generate report
    report = gen.generate_report(
        period_start=now - 86400 * 90,
        period_end=now,
    )
    
    print(gen.format_report(report))
    
    # Show individual agent detail
    print(f"\n\n📋 Agent Detail: agent:struggling")
    rec = gen.records["agent:struggling"]
    print(f"  Compliance: {rec.compliance_rate:.1%}")
    print(f"  Grade: {rec.grade.value}")
    print(f"  Improving: {rec.improving}")
    print(f"  Top violation: {rec.top_violation}")
    print(f"  Grade history: {[g.value for g in rec.grade_history]}")


if __name__ == "__main__":
    demo()
