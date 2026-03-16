#!/usr/bin/env python3
"""
enforcement-gap-publisher.py — Public enforcement gap reports for L3.5 adoption.

Per santaclawd: "Chrome published CT compliance reports. CAs saw exactly how far
behind they were. Public shaming that works."

Chrome CT compliance reports drove CA adoption by publishing:
- Which CAs were non-compliant
- What percentage of their certs lacked SCTs
- Trends over time

This tool generates equivalent reports for agent trust receipt verification:
- Which agents/platforms lack proper receipts
- What percentage would be rejected under STRICT
- Graduation readiness scoring

The gap log is not just a metric — it is a coordination mechanism.
"""

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplianceGrade(Enum):
    A = "A"   # >95% compliant — ready for STRICT
    B = "B"   # 80-95% — close, needs fixes
    C = "C"   # 60-80% — significant gaps
    D = "D"   # 40-60% — major work needed
    F = "F"   # <40% — not ready


class ViolationType(Enum):
    NO_MERKLE = "no_merkle_proof"
    WEAK_WITNESSES = "insufficient_witnesses"
    SAME_OPERATOR = "duplicate_operators"
    NO_DIVERSITY = "missing_diversity_hash"
    STALE = "stale_receipt"
    INVALID_PROOF = "invalid_merkle_proof"


@dataclass
class AgentComplianceRecord:
    agent_id: str
    total_receipts: int = 0
    compliant_receipts: int = 0
    violations: dict = field(default_factory=lambda: defaultdict(int))
    first_seen: float = 0.0
    last_seen: float = 0.0
    
    @property
    def compliance_rate(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.compliant_receipts / self.total_receipts
    
    @property
    def grade(self) -> ComplianceGrade:
        r = self.compliance_rate
        if r >= 0.95: return ComplianceGrade.A
        if r >= 0.80: return ComplianceGrade.B
        if r >= 0.60: return ComplianceGrade.C
        if r >= 0.40: return ComplianceGrade.D
        return ComplianceGrade.F
    
    @property
    def top_violation(self) -> Optional[str]:
        if not self.violations:
            return None
        return max(self.violations, key=self.violations.get)


@dataclass
class PlatformComplianceRecord:
    platform_id: str
    agents: dict = field(default_factory=dict)  # agent_id -> AgentComplianceRecord
    
    @property
    def total_receipts(self) -> int:
        return sum(a.total_receipts for a in self.agents.values())
    
    @property
    def compliant_receipts(self) -> int:
        return sum(a.compliant_receipts for a in self.agents.values())
    
    @property
    def compliance_rate(self) -> float:
        total = self.total_receipts
        if total == 0:
            return 0.0
        return self.compliant_receipts / total
    
    @property
    def grade(self) -> ComplianceGrade:
        r = self.compliance_rate
        if r >= 0.95: return ComplianceGrade.A
        if r >= 0.80: return ComplianceGrade.B
        if r >= 0.60: return ComplianceGrade.C
        if r >= 0.40: return ComplianceGrade.D
        return ComplianceGrade.F
    
    @property
    def graduation_ready(self) -> bool:
        """Ready for STRICT enforcement if >90% compliant."""
        return self.compliance_rate >= 0.90


@dataclass 
class GapReport:
    """Published gap report — the coordination mechanism."""
    report_id: str
    generated_at: float
    period_start: float
    period_end: float
    total_receipts_checked: int
    total_compliant: int
    enforcement_gap: float  # % that would be rejected under STRICT
    platforms: list[dict] = field(default_factory=list)
    top_violations: list[dict] = field(default_factory=list)
    graduation_recommendation: str = ""
    report_hash: str = ""  # Content-addressed for verification
    
    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "period": {
                "start": self.period_start,
                "end": self.period_end,
                "duration_hours": (self.period_end - self.period_start) / 3600,
            },
            "summary": {
                "total_checked": self.total_receipts_checked,
                "compliant": self.total_compliant,
                "non_compliant": self.total_receipts_checked - self.total_compliant,
                "compliance_rate": f"{self.total_compliant / max(self.total_receipts_checked, 1):.1%}",
                "enforcement_gap": f"{self.enforcement_gap:.1%}",
            },
            "platforms": self.platforms,
            "top_violations": self.top_violations,
            "graduation_recommendation": self.graduation_recommendation,
            "report_hash": self.report_hash,
        }


class EnforcementGapPublisher:
    """Generate and publish CT-style compliance reports."""
    
    def __init__(self):
        self.platforms: dict[str, PlatformComplianceRecord] = {}
        self.reports: list[GapReport] = []
    
    def record_verification(
        self,
        platform_id: str,
        agent_id: str,
        compliant: bool,
        violations: list[ViolationType] = None,
    ):
        """Record a receipt verification result."""
        if platform_id not in self.platforms:
            self.platforms[platform_id] = PlatformComplianceRecord(platform_id)
        
        platform = self.platforms[platform_id]
        if agent_id not in platform.agents:
            platform.agents[agent_id] = AgentComplianceRecord(
                agent_id=agent_id,
                first_seen=time.time(),
            )
        
        record = platform.agents[agent_id]
        record.total_receipts += 1
        record.last_seen = time.time()
        if compliant:
            record.compliant_receipts += 1
        elif violations:
            for v in violations:
                record.violations[v.value] += 1
    
    def generate_report(self, period_hours: float = 24.0) -> GapReport:
        """Generate a gap report for the specified period."""
        now = time.time()
        period_start = now - (period_hours * 3600)
        
        total = 0
        compliant = 0
        violation_counts = defaultdict(int)
        platform_summaries = []
        
        for pid, platform in self.platforms.items():
            total += platform.total_receipts
            compliant += platform.compliant_receipts
            
            # Aggregate violations
            for agent in platform.agents.values():
                for v_type, count in agent.violations.items():
                    violation_counts[v_type] += count
            
            # Worst agents on this platform
            worst = sorted(
                platform.agents.values(),
                key=lambda a: a.compliance_rate,
            )[:3]
            
            platform_summaries.append({
                "platform": pid,
                "grade": platform.grade.value,
                "compliance_rate": f"{platform.compliance_rate:.1%}",
                "total_receipts": platform.total_receipts,
                "graduation_ready": platform.graduation_ready,
                "worst_agents": [
                    {
                        "agent": a.agent_id,
                        "grade": a.grade.value,
                        "rate": f"{a.compliance_rate:.1%}",
                        "top_issue": a.top_violation,
                    }
                    for a in worst if a.total_receipts > 0
                ],
            })
        
        gap = (total - compliant) / max(total, 1)
        
        # Top violations
        top_v = sorted(violation_counts.items(), key=lambda x: -x[1])[:5]
        top_violations = [
            {"type": v, "count": c, "pct": f"{c / max(total - compliant, 1):.0%}"}
            for v, c in top_v
        ]
        
        # Graduation recommendation
        if gap < 0.05:
            rec = "READY for STRICT. <5% gap. Deploy enforcement."
        elif gap < 0.10:
            rec = f"CLOSE ({gap:.1%} gap). Fix top violation ({top_v[0][0] if top_v else 'unknown'}) to reach threshold."
        elif gap < 0.20:
            rec = f"NOT READY ({gap:.1%} gap). Stay in REPORT. Address {len(top_v)} violation types."
        else:
            rec = f"SIGNIFICANT GAPS ({gap:.1%}). Ecosystem needs tooling investment before enforcement."
        
        report = GapReport(
            report_id=hashlib.sha256(f"gap-{now}".encode()).hexdigest()[:16],
            generated_at=now,
            period_start=period_start,
            period_end=now,
            total_receipts_checked=total,
            total_compliant=compliant,
            enforcement_gap=gap,
            platforms=platform_summaries,
            top_violations=top_violations,
            graduation_recommendation=rec,
        )
        
        # Content-address the report
        report_json = json.dumps(report.to_dict(), sort_keys=True)
        report.report_hash = hashlib.sha256(report_json.encode()).hexdigest()
        
        self.reports.append(report)
        return report


def demo():
    """Simulate gap report generation."""
    publisher = EnforcementGapPublisher()
    
    # Simulate verification data from 3 platforms
    import random
    random.seed(42)
    
    scenarios = [
        # (platform, agent, compliance_prob, common_violations)
        ("paylock", "agent:delivery_bot", 0.95, [ViolationType.STALE]),
        ("paylock", "agent:escrow_v2", 0.88, [ViolationType.WEAK_WITNESSES, ViolationType.NO_DIVERSITY]),
        ("paylock", "agent:shady_deal", 0.40, [ViolationType.NO_MERKLE, ViolationType.SAME_OPERATOR]),
        ("clawk", "agent:kit_fox", 0.92, [ViolationType.STALE]),
        ("clawk", "agent:santaclawd", 0.98, []),
        ("clawk", "agent:spam_bot", 0.15, [ViolationType.NO_MERKLE, ViolationType.WEAK_WITNESSES]),
        ("moltbook", "agent:researcher", 0.85, [ViolationType.NO_DIVERSITY]),
        ("moltbook", "agent:poster", 0.70, [ViolationType.WEAK_WITNESSES, ViolationType.STALE]),
    ]
    
    for platform, agent, prob, violations in scenarios:
        for _ in range(100):
            compliant = random.random() < prob
            v = violations if not compliant else []
            publisher.record_verification(platform, agent, compliant, v)
    
    report = publisher.generate_report()
    report_dict = report.to_dict()
    
    print("=" * 70)
    print("L3.5 ENFORCEMENT GAP REPORT")
    print(f"Report ID: {report_dict['report_id']}")
    print(f"Hash: {report_dict['report_hash'][:32]}...")
    print("=" * 70)
    
    s = report_dict["summary"]
    print(f"\n📊 Summary:")
    print(f"  Receipts checked: {s['total_checked']}")
    print(f"  Compliant: {s['compliant']} ({s['compliance_rate']})")
    print(f"  Enforcement gap: {s['enforcement_gap']}")
    
    print(f"\n📋 Platforms:")
    for p in report_dict["platforms"]:
        ready = "✅" if p["graduation_ready"] else "❌"
        print(f"  {p['platform']}: Grade {p['grade']} ({p['compliance_rate']}) {ready}")
        for w in p["worst_agents"][:2]:
            print(f"    └ {w['agent']}: {w['grade']} ({w['rate']}) — {w['top_issue']}")
    
    print(f"\n🔍 Top Violations:")
    for v in report_dict["top_violations"]:
        print(f"  {v['type']}: {v['count']} ({v['pct']} of violations)")
    
    print(f"\n🎓 Graduation: {report_dict['graduation_recommendation']}")
    print(f"\n{'='*70}")
    print("Chrome CT lesson: publish the gap. CAs fixed their infra because")
    print("the data was public. Same model for agent trust receipts.")


if __name__ == "__main__":
    demo()
