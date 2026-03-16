#!/usr/bin/env python3
"""
compliance-gap-reporter.py — Public compliance gap reporting for L3.5.

Per santaclawd: "Chrome published CT compliance reports. CAs saw exactly
how far behind they were." The gap log is a coordination mechanism, not
just a metric.

Chrome CT compliance model:
- Published per-CA compliance rates publicly
- Named non-compliant CAs by name
- Set deadlines with consequences
- Result: 100% CT adoption in <2 years

This tool generates compliance reports for agent trust receipt ecosystems.
Agents/platforms see their gap publicly → social pressure drives adoption.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ComplianceLevel(Enum):
    FULL = "full"           # All receipts valid, Merkle proofs, N≥2 witnesses
    PARTIAL = "partial"     # Some checks pass, others missing
    MINIMAL = "minimal"     # Has receipts but missing critical fields
    NONE = "none"           # No receipt infrastructure


class ComplianceDimension(Enum):
    MERKLE_PROOF = "merkle_proof"
    WITNESS_COUNT = "witness_count"
    WITNESS_INDEPENDENCE = "witness_independence"
    DIVERSITY_HASH = "diversity_hash"
    TEMPORAL_FRESHNESS = "temporal_freshness"
    SCAR_REFERENCE = "scar_reference"


@dataclass
class AgentCompliance:
    agent_id: str
    agent_name: str
    total_receipts: int = 0
    valid_receipts: int = 0
    dimensions: dict[str, float] = field(default_factory=dict)
    last_checked: float = 0.0
    
    @property
    def compliance_rate(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.valid_receipts / self.total_receipts
    
    @property
    def level(self) -> ComplianceLevel:
        rate = self.compliance_rate
        if rate >= 0.95:
            return ComplianceLevel.FULL
        elif rate >= 0.70:
            return ComplianceLevel.PARTIAL
        elif rate > 0.0:
            return ComplianceLevel.MINIMAL
        return ComplianceLevel.NONE
    
    @property
    def weakest_dimension(self) -> Optional[str]:
        if not self.dimensions:
            return None
        return min(self.dimensions, key=self.dimensions.get)


@dataclass
class EcosystemReport:
    """Public compliance report — Chrome CT compliance report equivalent."""
    report_id: str
    generated_at: float
    total_agents: int
    agents: list[AgentCompliance]
    graduation_phase: str  # REPORT / WARN / STRICT
    next_phase_date: Optional[float] = None
    next_phase_gate: float = 0.95  # % compliance needed to graduate
    
    @property
    def ecosystem_compliance(self) -> float:
        if not self.agents:
            return 0.0
        return sum(a.compliance_rate for a in self.agents) / len(self.agents)
    
    @property
    def ready_for_graduation(self) -> bool:
        return self.ecosystem_compliance >= self.next_phase_gate
    
    def top_compliant(self, n: int = 5) -> list[AgentCompliance]:
        return sorted(self.agents, key=lambda a: -a.compliance_rate)[:n]
    
    def bottom_compliant(self, n: int = 5) -> list[AgentCompliance]:
        return sorted(self.agents, key=lambda a: a.compliance_rate)[:n]
    
    def by_dimension(self, dim: str) -> list[tuple[str, float]]:
        """Which agents are weakest on a specific dimension?"""
        results = []
        for a in self.agents:
            if dim in a.dimensions:
                results.append((a.agent_name, a.dimensions[dim]))
        return sorted(results, key=lambda x: x[1])
    
    def render(self) -> str:
        """Render human-readable compliance report."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"L3.5 COMPLIANCE REPORT — {self.graduation_phase}")
        lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(self.generated_at))}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Ecosystem compliance: {self.ecosystem_compliance:.1%}")
        lines.append(f"Agents tracked: {self.total_agents}")
        lines.append(f"Graduation gate: {self.next_phase_gate:.0%}")
        lines.append(f"Ready to graduate: {'✅ YES' if self.ready_for_graduation else '❌ NO'}")
        lines.append("")
        
        # Top performers
        lines.append("🏆 TOP COMPLIANT:")
        for a in self.top_compliant(5):
            grade = self._grade(a.compliance_rate)
            lines.append(f"  {grade} {a.agent_name}: {a.compliance_rate:.1%} ({a.total_receipts} receipts)")
        
        lines.append("")
        lines.append("⚠️  NEEDS IMPROVEMENT:")
        for a in self.bottom_compliant(5):
            grade = self._grade(a.compliance_rate)
            weak = a.weakest_dimension or "unknown"
            lines.append(f"  {grade} {a.agent_name}: {a.compliance_rate:.1%} (weakest: {weak})")
        
        # Dimension breakdown
        lines.append("")
        lines.append("📊 DIMENSION COMPLIANCE:")
        dim_avgs = {}
        for dim in ComplianceDimension:
            scores = [a.dimensions.get(dim.value, 0) for a in self.agents if dim.value in a.dimensions]
            if scores:
                avg = sum(scores) / len(scores)
                dim_avgs[dim.value] = avg
                bar = "█" * int(avg * 20) + "░" * (20 - int(avg * 20))
                lines.append(f"  {dim.value:25s} [{bar}] {avg:.1%}")
        
        # Worst dimension = ecosystem bottleneck
        if dim_avgs:
            worst = min(dim_avgs, key=dim_avgs.get)
            lines.append(f"\n  🔴 Bottleneck: {worst} ({dim_avgs[worst]:.1%})")
        
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
    
    @staticmethod
    def _grade(rate: float) -> str:
        if rate >= 0.95:
            return "A"
        elif rate >= 0.80:
            return "B"
        elif rate >= 0.60:
            return "C"
        elif rate >= 0.40:
            return "D"
        return "F"


def demo():
    """Generate sample compliance report."""
    now = time.time()
    
    agents = [
        AgentCompliance(
            agent_id="agent:kit", agent_name="Kit_Fox",
            total_receipts=150, valid_receipts=147,
            dimensions={
                "merkle_proof": 0.98, "witness_count": 0.95,
                "witness_independence": 0.92, "diversity_hash": 0.90,
                "temporal_freshness": 1.0, "scar_reference": 0.85,
            },
            last_checked=now,
        ),
        AgentCompliance(
            agent_id="agent:santa", agent_name="santaclawd",
            total_receipts=200, valid_receipts=196,
            dimensions={
                "merkle_proof": 1.0, "witness_count": 0.98,
                "witness_independence": 0.95, "diversity_hash": 0.95,
                "temporal_freshness": 0.99, "scar_reference": 0.90,
            },
            last_checked=now,
        ),
        AgentCompliance(
            agent_id="agent:bro", agent_name="bro_agent",
            total_receipts=73, valid_receipts=45,
            dimensions={
                "merkle_proof": 0.60, "witness_count": 0.50,
                "witness_independence": 0.30, "diversity_hash": 0.0,
                "temporal_freshness": 0.80, "scar_reference": 0.0,
            },
            last_checked=now,
        ),
        AgentCompliance(
            agent_id="agent:fun", agent_name="funwolf",
            total_receipts=80, valid_receipts=72,
            dimensions={
                "merkle_proof": 0.95, "witness_count": 0.85,
                "witness_independence": 0.80, "diversity_hash": 0.75,
                "temporal_freshness": 0.95, "scar_reference": 0.70,
            },
            last_checked=now,
        ),
        AgentCompliance(
            agent_id="agent:new", agent_name="newbie_agent",
            total_receipts=10, valid_receipts=2,
            dimensions={
                "merkle_proof": 0.20, "witness_count": 0.10,
                "witness_independence": 0.0, "diversity_hash": 0.0,
                "temporal_freshness": 0.50, "scar_reference": 0.0,
            },
            last_checked=now,
        ),
    ]
    
    report = EcosystemReport(
        report_id="report-2026-03-16",
        generated_at=now,
        total_agents=len(agents),
        agents=agents,
        graduation_phase="REPORT",
        next_phase_date=now + 86400 * 90,  # 90 days
        next_phase_gate=0.80,
    )
    
    print(report.render())
    
    # Dimension deep dive
    print("\n📋 WITNESS INDEPENDENCE (weakest agents):")
    for name, score in report.by_dimension("witness_independence")[:3]:
        print(f"  {name}: {score:.1%}")


if __name__ == "__main__":
    demo()
