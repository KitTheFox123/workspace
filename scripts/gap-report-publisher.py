#!/usr/bin/env python3
"""
gap-report-publisher.py — Public compliance reporting for L3.5 receipt verification.

Per santaclawd: "Chrome published CT compliance reports. CAs saw exactly how
far behind they were." The gap log is a coordination mechanism, not just a metric.

Chrome CT compliance reports:
  - Named CAs by non-compliance rate
  - Published weekly
  - Created competitive pressure to comply
  - CAs that lagged got customer complaints

This tool generates per-agent and aggregate compliance reports
for the L3.5 enforcement graduation pipeline.

Forcing function: public shaming + clear deadline = adoption.
"""

import json
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplianceGrade(Enum):
    A = "A"  # 95-100% compliant
    B = "B"  # 80-95%
    C = "C"  # 60-80%
    D = "D"  # 40-60%
    F = "F"  # <40%


@dataclass
class AgentCompliance:
    agent_id: str
    receipts_checked: int
    receipts_valid: int
    most_common_failure: Optional[str] = None
    first_seen: float = 0.0
    last_checked: float = 0.0
    
    @property
    def compliance_rate(self) -> float:
        if self.receipts_checked == 0:
            return 0.0
        return self.receipts_valid / self.receipts_checked
    
    @property
    def grade(self) -> ComplianceGrade:
        r = self.compliance_rate
        if r >= 0.95: return ComplianceGrade.A
        if r >= 0.80: return ComplianceGrade.B
        if r >= 0.60: return ComplianceGrade.C
        if r >= 0.40: return ComplianceGrade.D
        return ComplianceGrade.F
    
    @property
    def failure_rate(self) -> float:
        return 1.0 - self.compliance_rate


@dataclass 
class FailureBreakdown:
    no_merkle_proof: int = 0
    invalid_proof: int = 0
    insufficient_witnesses: int = 0
    duplicate_operators: int = 0
    stale_receipt: int = 0
    missing_diversity_hash: int = 0
    
    @property
    def total(self) -> int:
        return (self.no_merkle_proof + self.invalid_proof + 
                self.insufficient_witnesses + self.duplicate_operators +
                self.stale_receipt + self.missing_diversity_hash)
    
    def top_failures(self, n: int = 3) -> list[tuple[str, int]]:
        failures = [
            ("no_merkle_proof", self.no_merkle_proof),
            ("invalid_proof", self.invalid_proof),
            ("insufficient_witnesses", self.insufficient_witnesses),
            ("duplicate_operators", self.duplicate_operators),
            ("stale_receipt", self.stale_receipt),
            ("missing_diversity_hash", self.missing_diversity_hash),
        ]
        return sorted(failures, key=lambda x: -x[1])[:n]


@dataclass
class GapReport:
    """Weekly compliance report (Chrome CT model)."""
    report_id: str
    period_start: float
    period_end: float
    enforcement_phase: str
    
    # Aggregate stats
    total_receipts: int = 0
    valid_receipts: int = 0
    
    # Per-agent compliance
    agent_compliance: list[AgentCompliance] = field(default_factory=list)
    
    # Failure breakdown
    failures: FailureBreakdown = field(default_factory=FailureBreakdown)
    
    # Trend (vs previous report)
    prev_compliance_rate: Optional[float] = None
    
    @property
    def compliance_rate(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.valid_receipts / self.total_receipts
    
    @property
    def enforcement_gap(self) -> float:
        return 1.0 - self.compliance_rate
    
    @property
    def trend(self) -> str:
        if self.prev_compliance_rate is None:
            return "—"
        delta = self.compliance_rate - self.prev_compliance_rate
        if delta > 0.01: return f"↑ +{delta:.1%}"
        if delta < -0.01: return f"↓ {delta:.1%}"
        return "→ stable"
    
    def report_hash(self) -> str:
        """Content-addressable hash for report integrity."""
        content = json.dumps({
            "id": self.report_id,
            "period": [self.period_start, self.period_end],
            "total": self.total_receipts,
            "valid": self.valid_receipts,
            "agents": len(self.agent_compliance),
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def render_text(self) -> str:
        """Render human-readable compliance report."""
        lines = [
            f"═══════════════════════════════════════════",
            f"  L3.5 COMPLIANCE REPORT — {self.enforcement_phase.upper()}",
            f"  Report: {self.report_id} ({self.report_hash()})",
            f"═══════════════════════════════════════════",
            f"",
            f"  Period: {time.strftime('%Y-%m-%d', time.gmtime(self.period_start))} → "
            f"{time.strftime('%Y-%m-%d', time.gmtime(self.period_end))}",
            f"  Receipts checked: {self.total_receipts:,}",
            f"  Compliance rate:  {self.compliance_rate:.1%} {self.trend}",
            f"  Enforcement gap:  {self.enforcement_gap:.1%}",
            f"",
        ]
        
        # Top failures
        top = self.failures.top_failures(3)
        if any(c > 0 for _, c in top):
            lines.append("  Top failure reasons:")
            for reason, count in top:
                if count > 0:
                    pct = count / max(self.failures.total, 1) * 100
                    lines.append(f"    {reason}: {count} ({pct:.0f}%)")
            lines.append("")
        
        # Per-agent leaderboard
        if self.agent_compliance:
            sorted_agents = sorted(self.agent_compliance, 
                                   key=lambda a: a.compliance_rate)
            
            # Worst agents (Chrome CT: name CAs by non-compliance)
            worst = [a for a in sorted_agents if a.failure_rate > 0][:5]
            if worst:
                lines.append("  ⚠️  Agents below 100% compliance:")
                for a in worst:
                    lines.append(
                        f"    {a.agent_id}: {a.compliance_rate:.0%} "
                        f"({a.grade.value}) — {a.receipts_checked} checked"
                        f"{', top issue: ' + a.most_common_failure if a.most_common_failure else ''}"
                    )
                lines.append("")
            
            # Best agents
            best = [a for a in reversed(sorted_agents) if a.compliance_rate >= 0.95][:3]
            if best:
                lines.append("  ✅ Top compliant agents:")
                for a in best:
                    lines.append(
                        f"    {a.agent_id}: {a.compliance_rate:.0%} "
                        f"({a.grade.value}) — {a.receipts_checked} checked"
                    )
                lines.append("")
        
        # Graduation readiness
        lines.append(f"  Graduation readiness:")
        if self.enforcement_gap < 0.05:
            lines.append(f"    ✅ Gap < 5% — ready for STRICT enforcement")
        elif self.enforcement_gap < 0.20:
            lines.append(f"    ⏳ Gap < 20% — ready for WARN phase")
        else:
            lines.append(f"    ❌ Gap > 20% — stay in REPORT")
        
        lines.append(f"\n  Hash: {self.report_hash()}")
        return "\n".join(lines)


class GapReportPublisher:
    """Generate and track weekly compliance reports."""
    
    def __init__(self):
        self.reports: list[GapReport] = []
        self.agent_data: dict[str, AgentCompliance] = {}
        self.current_failures = FailureBreakdown()
        self.period_start = time.time()
        self.receipts_total = 0
        self.receipts_valid = 0
    
    def record(self, agent_id: str, valid: bool, 
               failure_reason: Optional[str] = None):
        """Record a receipt check."""
        self.receipts_total += 1
        if valid:
            self.receipts_valid += 1
        
        if agent_id not in self.agent_data:
            self.agent_data[agent_id] = AgentCompliance(
                agent_id=agent_id, 
                receipts_checked=0, 
                receipts_valid=0,
                first_seen=time.time()
            )
        
        ac = self.agent_data[agent_id]
        ac.receipts_checked += 1
        if valid:
            ac.receipts_valid += 1
        ac.last_checked = time.time()
        
        if failure_reason:
            ac.most_common_failure = failure_reason
            if hasattr(self.current_failures, failure_reason):
                setattr(self.current_failures, failure_reason,
                        getattr(self.current_failures, failure_reason) + 1)
    
    def publish_report(self, phase: str = "report") -> GapReport:
        """Generate weekly compliance report."""
        now = time.time()
        
        prev_rate = self.reports[-1].compliance_rate if self.reports else None
        
        report = GapReport(
            report_id=f"gap-{len(self.reports)+1:04d}",
            period_start=self.period_start,
            period_end=now,
            enforcement_phase=phase,
            total_receipts=self.receipts_total,
            valid_receipts=self.receipts_valid,
            agent_compliance=list(self.agent_data.values()),
            failures=self.current_failures,
            prev_compliance_rate=prev_rate,
        )
        
        self.reports.append(report)
        
        # Reset for next period
        self.period_start = now
        self.receipts_total = 0
        self.receipts_valid = 0
        self.agent_data = {}
        self.current_failures = FailureBreakdown()
        
        return report


def demo():
    """Simulate weekly compliance reporting."""
    import random
    
    publisher = GapReportPublisher()
    
    agents = {
        "agent:alpha": 0.98,    # Very compliant
        "agent:beta": 0.85,     # Moderate
        "agent:gamma": 0.60,    # Struggling
        "agent:delta": 0.95,    # Good
        "agent:epsilon": 0.40,  # Poor
    }
    
    failure_reasons = [
        "no_merkle_proof", "insufficient_witnesses", 
        "duplicate_operators", "stale_receipt", "missing_diversity_hash"
    ]
    
    # Simulate 3 weekly reports with improving compliance
    for week in range(3):
        improvement = week * 0.05
        
        for _ in range(200):
            agent = random.choice(list(agents.keys()))
            rate = min(agents[agent] + improvement, 1.0)
            valid = random.random() < rate
            reason = random.choice(failure_reasons) if not valid else None
            publisher.record(agent, valid, reason)
        
        report = publisher.publish_report(phase="report")
        print(report.render_text())
        print()


if __name__ == "__main__":
    demo()
