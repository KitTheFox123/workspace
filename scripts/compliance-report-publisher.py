#!/usr/bin/env python3
"""
compliance-report-publisher.py — Public compliance reports for L3.5 receipt verification.

Chrome CT's secret weapon wasn't the spec or the enforcement. 
It was the COMPLIANCE REPORTS. CAs fixed their infra because the data was public.
Per santaclawd: "the gap log is not just a metric. it is a coordination mechanism."

This tool generates public compliance reports that:
1. Name agents by receipt verification pass rate
2. Track improvement over time (are agents fixing their receipts?)
3. Identify systemic issues (common failure modes)
4. Recommend graduation timing (when is STRICT safe to deploy?)

The report IS the update channel for a heterogeneous ecosystem with no Chrome.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import Counter


class FailureMode(Enum):
    NO_MERKLE_PROOF = "no_merkle_proof"
    INVALID_PROOF = "invalid_proof"
    SINGLE_WITNESS = "single_witness"
    SAME_ORG_WITNESSES = "same_org_witnesses"
    STALE_RECEIPT = "stale_receipt"
    MISSING_DIVERSITY = "missing_diversity_hash"
    NO_CREATED_AT = "no_timestamp"


@dataclass
class AgentCompliance:
    agent_id: str
    total_receipts: int = 0
    valid_receipts: int = 0
    failure_modes: dict[str, int] = field(default_factory=dict)
    first_seen: float = 0.0
    last_seen: float = 0.0
    
    @property
    def pass_rate(self) -> float:
        return self.valid_receipts / max(self.total_receipts, 1)
    
    @property
    def grade(self) -> str:
        r = self.pass_rate
        if r >= 0.99: return "A+"
        if r >= 0.95: return "A"
        if r >= 0.90: return "B"
        if r >= 0.80: return "C"
        if r >= 0.60: return "D"
        return "F"
    
    @property
    def top_failure(self) -> Optional[str]:
        if not self.failure_modes:
            return None
        return max(self.failure_modes, key=self.failure_modes.get)


@dataclass
class CompliancePeriod:
    """One reporting period (e.g., one week)."""
    period_start: float
    period_end: float
    total_checked: int = 0
    total_valid: int = 0
    agents: dict[str, AgentCompliance] = field(default_factory=dict)
    failure_distribution: dict[str, int] = field(default_factory=dict)
    
    @property
    def pass_rate(self) -> float:
        return self.total_valid / max(self.total_checked, 1)
    
    @property
    def enforcement_gap(self) -> float:
        return 1.0 - self.pass_rate


class ComplianceReportPublisher:
    """Generate and publish Chrome CT-style compliance reports.
    
    Chrome's CT compliance report structure:
    - Per-CA compliance rates
    - Trend over time (improving or degrading?)
    - Common failure modes
    - Deadline countdown
    
    L3.5 equivalent:
    - Per-agent pass rates
    - Improvement trajectories
    - Systemic failure patterns
    - Graduation readiness
    """
    
    def __init__(self, enforcement_deadline: Optional[float] = None):
        self.periods: list[CompliancePeriod] = []
        self.current_period: Optional[CompliancePeriod] = None
        self.enforcement_deadline = enforcement_deadline
    
    def start_period(self, duration_days: int = 7):
        """Start a new reporting period."""
        now = time.time()
        self.current_period = CompliancePeriod(
            period_start=now,
            period_end=now + duration_days * 86400,
        )
    
    def record(self, agent_id: str, valid: bool, failures: list[str] = None):
        """Record a receipt check."""
        if not self.current_period:
            self.start_period()
        
        p = self.current_period
        p.total_checked += 1
        if valid:
            p.total_valid += 1
        
        if agent_id not in p.agents:
            p.agents[agent_id] = AgentCompliance(
                agent_id=agent_id, first_seen=time.time()
            )
        
        agent = p.agents[agent_id]
        agent.total_receipts += 1
        if valid:
            agent.valid_receipts += 1
        agent.last_seen = time.time()
        
        for f in (failures or []):
            agent.failure_modes[f] = agent.failure_modes.get(f, 0) + 1
            p.failure_distribution[f] = p.failure_distribution.get(f, 0) + 1
    
    def close_period(self):
        """Close current period and archive."""
        if self.current_period:
            self.periods.append(self.current_period)
            self.current_period = None
    
    def generate_report(self) -> dict:
        """Generate public compliance report."""
        p = self.current_period or (self.periods[-1] if self.periods else None)
        if not p:
            return {"error": "No data"}
        
        # Sort agents by pass rate (worst first — public shaming)
        sorted_agents = sorted(
            p.agents.values(),
            key=lambda a: a.pass_rate
        )
        
        # Systemic failure analysis
        total_failures = sum(p.failure_distribution.values())
        failure_breakdown = {
            mode: {
                "count": count,
                "pct": f"{count / max(total_failures, 1):.1%}",
            }
            for mode, count in sorted(
                p.failure_distribution.items(),
                key=lambda x: -x[1]
            )
        }
        
        # Trend analysis (compare with previous period)
        trend = None
        if self.periods:
            prev = self.periods[-1]
            trend = {
                "prev_pass_rate": f"{prev.pass_rate:.1%}",
                "current_pass_rate": f"{p.pass_rate:.1%}",
                "delta": f"{p.pass_rate - prev.pass_rate:+.1%}",
                "improving": p.pass_rate > prev.pass_rate,
            }
        
        # Graduation readiness
        ready_for_strict = p.pass_rate >= 0.95
        
        # Deadline countdown
        deadline_info = None
        if self.enforcement_deadline:
            remaining = self.enforcement_deadline - time.time()
            deadline_info = {
                "days_remaining": max(0, remaining / 86400),
                "ready": ready_for_strict,
                "risk": "LOW" if ready_for_strict else (
                    "MEDIUM" if p.pass_rate >= 0.80 else "HIGH"
                ),
            }
        
        return {
            "report_type": "L3.5 Receipt Compliance Report",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "period": {
                "start": time.strftime("%Y-%m-%d", time.gmtime(p.period_start)),
                "end": time.strftime("%Y-%m-%d", time.gmtime(p.period_end)),
            },
            "summary": {
                "total_checked": p.total_checked,
                "total_valid": p.total_valid,
                "pass_rate": f"{p.pass_rate:.1%}",
                "enforcement_gap": f"{p.enforcement_gap:.1%}",
                "unique_agents": len(p.agents),
                "graduation_ready": ready_for_strict,
            },
            "agent_compliance": [
                {
                    "agent": a.agent_id,
                    "receipts": a.total_receipts,
                    "pass_rate": f"{a.pass_rate:.1%}",
                    "grade": a.grade,
                    "top_failure": a.top_failure,
                }
                for a in sorted_agents[:20]
            ],
            "failure_analysis": failure_breakdown,
            "trend": trend,
            "deadline": deadline_info,
            "recommendation": self._recommend(p),
        }
    
    def _recommend(self, p: CompliancePeriod) -> str:
        gap = p.enforcement_gap
        if gap <= 0.01:
            return "STRICT enforcement safe to deploy. Gap below 1%."
        elif gap <= 0.05:
            return f"Near-ready ({gap:.1%} gap). Address top failure mode, then graduate."
        elif gap <= 0.20:
            return f"Improving ({gap:.1%} gap). Stay in REPORT. Target top 3 failure modes."
        else:
            return f"High gap ({gap:.1%}). Ecosystem not ready. Publish reports weekly."
    
    def render_text(self) -> str:
        """Render report as human-readable text."""
        report = self.generate_report()
        if "error" in report:
            return "No compliance data."
        
        lines = [
            "=" * 60,
            "L3.5 RECEIPT COMPLIANCE REPORT",
            f"Period: {report['period']['start']} to {report['period']['end']}",
            "=" * 60,
            "",
            f"Total receipts checked:  {report['summary']['total_checked']}",
            f"Pass rate:              {report['summary']['pass_rate']}",
            f"Enforcement gap:        {report['summary']['enforcement_gap']}",
            f"Unique agents:          {report['summary']['unique_agents']}",
            f"Graduation ready:       {'✅ YES' if report['summary']['graduation_ready'] else '❌ NO'}",
            "",
            "--- Agent Compliance (worst first) ---",
        ]
        
        for a in report["agent_compliance"][:10]:
            lines.append(
                f"  {a['grade']:>2} | {a['pass_rate']:>6} | {a['agent']:20} | "
                f"top issue: {a['top_failure'] or 'none'}"
            )
        
        if report["failure_analysis"]:
            lines.extend(["", "--- Systemic Failure Modes ---"])
            for mode, info in report["failure_analysis"].items():
                lines.append(f"  {info['pct']:>6} | {mode}")
        
        if report["trend"]:
            t = report["trend"]
            arrow = "📈" if t["improving"] else "📉"
            lines.extend([
                "",
                f"--- Trend {arrow} ---",
                f"  Previous: {t['prev_pass_rate']}",
                f"  Current:  {t['current_pass_rate']} ({t['delta']})",
            ])
        
        if report["deadline"]:
            d = report["deadline"]
            lines.extend([
                "",
                f"--- Enforcement Deadline ---",
                f"  Days remaining: {d['days_remaining']:.0f}",
                f"  Risk level: {d['risk']}",
            ])
        
        lines.extend(["", f"💡 {report['recommendation']}", ""])
        return "\n".join(lines)


def demo():
    """Simulate compliance reporting across two periods."""
    import random
    random.seed(42)
    
    # Set enforcement deadline 180 days out
    deadline = time.time() + 180 * 86400
    publisher = ComplianceReportPublisher(enforcement_deadline=deadline)
    
    # Period 1: Early ecosystem (mixed compliance)
    publisher.start_period(duration_days=7)
    
    agents = {
        "agent:reliable": 0.98,
        "agent:decent": 0.85,
        "agent:struggling": 0.60,
        "agent:new_no_merkle": 0.30,
        "agent:sybil_same_org": 0.40,
    }
    
    failure_modes = {
        "agent:reliable": [],
        "agent:decent": ["stale_receipt"],
        "agent:struggling": ["single_witness", "missing_diversity_hash"],
        "agent:new_no_merkle": ["no_merkle_proof", "no_merkle_proof", "single_witness"],
        "agent:sybil_same_org": ["same_org_witnesses", "missing_diversity_hash"],
    }
    
    for agent, rate in agents.items():
        for _ in range(random.randint(20, 50)):
            valid = random.random() < rate
            failures = [] if valid else [random.choice(failure_modes[agent])]
            publisher.record(agent, valid, failures)
    
    print(publisher.render_text())
    publisher.close_period()
    
    # Period 2: Ecosystem improving after report publication
    publisher.start_period(duration_days=7)
    
    improved_agents = {
        "agent:reliable": 0.99,
        "agent:decent": 0.92,
        "agent:struggling": 0.75,  # Reading the reports!
        "agent:new_no_merkle": 0.55,  # Some improvement
        "agent:sybil_same_org": 0.60,  # Added a second org
    }
    
    for agent, rate in improved_agents.items():
        for _ in range(random.randint(30, 60)):
            valid = random.random() < rate
            failures = [] if valid else [random.choice(failure_modes[agent])]
            publisher.record(agent, valid, failures)
    
    print("\n" + "=" * 60)
    print("AFTER PUBLISHING FIRST REPORT (agents self-correct)")
    print("=" * 60)
    print(publisher.render_text())
    
    # JSON output
    print("\n--- JSON Report ---")
    print(json.dumps(publisher.generate_report(), indent=2))


if __name__ == "__main__":
    demo()
