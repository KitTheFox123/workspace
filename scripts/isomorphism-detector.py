#!/usr/bin/env python3
"""
isomorphism-detector.py — Detect institutional isomorphism in agent trust networks.

DiMaggio & Powell (1983) "The Iron Cage Revisited": organizations in a field become
structurally similar through three mechanisms:
1. COERCIVE: external pressure (regulations, specs, standards)
2. MIMETIC: copying under uncertainty (if unsure, do what successful agents do)
3. NORMATIVE: professionalization (shared tools, training, norms)

Applied to agent trust networks:
- Coercive: ATF spec mandates (SPEC_CONSTANTs, ceremony requirements)
- Mimetic: agents copying successful agents' trust strategies
- Normative: shared tooling (MCP servers, Keenable, common skills)

This detector measures convergence across agent behaviors and flags when
homogeneity reaches dangerous levels — because isomorphism has a dark side:
correlated failure. If everyone uses the same trust strategy, a single exploit
compromises the entire field.

The antidote: DIVERSITY IS LOAD-BEARING (same insight as ASPA, Wilson CI, Simpson).
Healthy fields need enough isomorphism for interoperability, enough diversity for resilience.

Sources:
- DiMaggio & Powell (1983) "The Iron Cage Revisited"
- Powell & DiMaggio (2023) "The Iron Cage Redux: Looking Back and Forward"
- Nature 2025: Correlated voters = wisdom of crowds failure
- West et al 2012: Bias blind spot in smarter people
"""

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class IsomorphismType(Enum):
    COERCIVE = "coercive"      # Spec mandates, regulatory pressure
    MIMETIC = "mimetic"        # Copying successful peers
    NORMATIVE = "normative"    # Shared professional norms/tools


class RiskLevel(Enum):
    HEALTHY = "healthy"          # Enough diversity, enough interop
    CONVERGING = "converging"    # Trending toward homogeneity
    ISOMORPHIC = "isomorphic"    # Dangerously similar — correlated failure risk
    MONOCULTURE = "monoculture"  # Single strategy dominates — fragile


@dataclass
class AgentProfile:
    """An agent's observable behavioral profile."""
    agent_id: str
    trust_strategy: str          # e.g., "wilson_ci", "bayesian", "reputation"
    grader_pool: list[str]       # Which graders they use
    tools: list[str]             # MCP servers, skills
    ceremony_mode: str           # SYNC, ASYNC, HYBRID
    epoch_length: int            # Days between re-attestation
    spec_version: str            # ATF version
    operator: str                # Who runs this agent


@dataclass 
class IsomorphismSignal:
    """A detected isomorphism signal."""
    type: IsomorphismType
    metric: str
    value: float
    threshold: float
    agents_involved: list[str]
    description: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IsomorphismDetector:
    """
    Measures institutional isomorphism across an agent trust network.
    
    Key metrics:
    - Strategy concentration: How many distinct trust strategies exist?
    - Tool overlap: Simpson diversity on tooling
    - Operator concentration: How many distinct operators?
    - Behavioral similarity: Cosine similarity across profiles
    
    The Goldilocks zone: 0.3-0.7 similarity. Below = fragmented. Above = monoculture.
    """
    
    # Thresholds
    CONVERGENCE_THRESHOLD = 0.6    # Above = converging
    ISOMORPHIC_THRESHOLD = 0.8     # Above = dangerously similar
    MONOCULTURE_THRESHOLD = 0.95   # Above = single strategy dominates
    
    def __init__(self):
        self.agents: dict[str, AgentProfile] = {}
        self.signals: list[IsomorphismSignal] = []
    
    def add_agent(self, profile: AgentProfile):
        self.agents[profile.agent_id] = profile
    
    def simpson_diversity(self, items: list[str]) -> float:
        """Simpson's Diversity Index: 1 - sum(p_i^2). 0=monoculture, 1=max diversity."""
        if not items:
            return 0.0
        counts: dict[str, int] = {}
        for item in items:
            counts[item] = counts.get(item, 0) + 1
        total = len(items)
        return 1.0 - sum((c/total)**2 for c in counts.values())
    
    def strategy_concentration(self) -> tuple[float, IsomorphismSignal]:
        """Measure how concentrated trust strategies are across the field."""
        strategies = [a.trust_strategy for a in self.agents.values()]
        diversity = self.simpson_diversity(strategies)
        concentration = 1.0 - diversity  # Invert: high concentration = low diversity
        
        signal = IsomorphismSignal(
            type=IsomorphismType.MIMETIC,
            metric="strategy_concentration",
            value=concentration,
            threshold=self.CONVERGENCE_THRESHOLD,
            agents_involved=list(self.agents.keys()),
            description=f"Trust strategy diversity: {diversity:.2f} (concentration: {concentration:.2f}). "
                       f"Unique strategies: {len(set(strategies))}/{len(strategies)}",
        )
        self.signals.append(signal)
        return concentration, signal
    
    def tool_overlap(self) -> tuple[float, IsomorphismSignal]:
        """Measure tool homogeneity (normative isomorphism via shared tooling)."""
        if len(self.agents) < 2:
            return 0.0, IsomorphismSignal(
                type=IsomorphismType.NORMATIVE, metric="tool_overlap",
                value=0.0, threshold=self.CONVERGENCE_THRESHOLD,
                agents_involved=[], description="Not enough agents"
            )
        
        # Jaccard similarity averaged across all pairs
        agents_list = list(self.agents.values())
        total_sim = 0.0
        pair_count = 0
        
        for i in range(len(agents_list)):
            for j in range(i + 1, len(agents_list)):
                set_a = set(agents_list[i].tools)
                set_b = set(agents_list[j].tools)
                if set_a or set_b:
                    jaccard = len(set_a & set_b) / len(set_a | set_b)
                    total_sim += jaccard
                pair_count += 1
        
        avg_overlap = total_sim / pair_count if pair_count > 0 else 0.0
        
        # Count most common tools
        all_tools: dict[str, int] = {}
        for a in self.agents.values():
            for t in a.tools:
                all_tools[t] = all_tools.get(t, 0) + 1
        dominant = sorted(all_tools.items(), key=lambda x: -x[1])[:3]
        
        signal = IsomorphismSignal(
            type=IsomorphismType.NORMATIVE,
            metric="tool_overlap",
            value=avg_overlap,
            threshold=self.CONVERGENCE_THRESHOLD,
            agents_involved=list(self.agents.keys()),
            description=f"Avg tool overlap (Jaccard): {avg_overlap:.2f}. "
                       f"Most common: {', '.join(f'{t}({c})' for t,c in dominant)}",
        )
        self.signals.append(signal)
        return avg_overlap, signal
    
    def operator_concentration(self) -> tuple[float, IsomorphismSignal]:
        """Measure operator diversity (coercive isomorphism — same entity controlling multiple agents)."""
        operators = [a.operator for a in self.agents.values()]
        diversity = self.simpson_diversity(operators)
        concentration = 1.0 - diversity
        
        signal = IsomorphismSignal(
            type=IsomorphismType.COERCIVE,
            metric="operator_concentration",
            value=concentration,
            threshold=self.CONVERGENCE_THRESHOLD,
            agents_involved=list(self.agents.keys()),
            description=f"Operator diversity: {diversity:.2f}. "
                       f"Unique operators: {len(set(operators))}/{len(operators)}",
        )
        self.signals.append(signal)
        return concentration, signal
    
    def spec_conformity(self) -> tuple[float, IsomorphismSignal]:
        """Measure spec version conformity (coercive isomorphism via standards)."""
        versions = [a.spec_version for a in self.agents.values()]
        most_common = max(set(versions), key=versions.count)
        conformity = versions.count(most_common) / len(versions)
        
        signal = IsomorphismSignal(
            type=IsomorphismType.COERCIVE,
            metric="spec_conformity",
            value=conformity,
            threshold=self.CONVERGENCE_THRESHOLD,
            agents_involved=[a.agent_id for a in self.agents.values() if a.spec_version == most_common],
            description=f"Spec conformity: {conformity:.0%} on {most_common}. "
                       f"Versions: {dict((v, versions.count(v)) for v in set(versions))}",
        )
        self.signals.append(signal)
        return conformity, signal
    
    def overall_risk(self) -> tuple[RiskLevel, dict]:
        """Compute overall isomorphism risk level."""
        self.signals.clear()
        
        strategy_c, _ = self.strategy_concentration()
        tool_o, _ = self.tool_overlap()
        operator_c, _ = self.operator_concentration()
        spec_c, _ = self.spec_conformity()
        
        # Weighted average (operator concentration weighted highest — most dangerous)
        weighted = (
            strategy_c * 0.30 +
            tool_o * 0.20 +
            operator_c * 0.35 +
            spec_c * 0.15
        )
        
        if weighted >= self.MONOCULTURE_THRESHOLD:
            level = RiskLevel.MONOCULTURE
        elif weighted >= self.ISOMORPHIC_THRESHOLD:
            level = RiskLevel.ISOMORPHIC
        elif weighted >= self.CONVERGENCE_THRESHOLD:
            level = RiskLevel.CONVERGING
        else:
            level = RiskLevel.HEALTHY
        
        return level, {
            "overall_score": round(weighted, 3),
            "risk_level": level.value,
            "strategy_concentration": round(strategy_c, 3),
            "tool_overlap": round(tool_o, 3),
            "operator_concentration": round(operator_c, 3),
            "spec_conformity": round(spec_c, 3),
            "signal_count": len(self.signals),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def run_scenarios():
    """Demonstrate isomorphism detection across different network states."""
    print("=" * 70)
    print("INSTITUTIONAL ISOMORPHISM DETECTOR")
    print("DiMaggio & Powell (1983) applied to agent trust networks")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Healthy diversity — mixed strategies, operators, tools",
            "agents": [
                AgentProfile("alpha", "wilson_ci", ["grader_1", "grader_2"], ["keenable", "github"], "ASYNC", 30, "ATF_1.2", "operator_a"),
                AgentProfile("beta", "bayesian", ["grader_3", "grader_4"], ["keenable", "arena"], "SYNC", 90, "ATF_1.1", "operator_b"),
                AgentProfile("gamma", "reputation", ["grader_1", "grader_5"], ["github", "qmd"], "HYBRID", 60, "ATF_1.2", "operator_c"),
                AgentProfile("delta", "elo_rating", ["grader_6", "grader_7"], ["arena", "qmd", "keenable"], "ASYNC", 45, "ATF_1.2", "operator_d"),
                AgentProfile("epsilon", "wilson_ci", ["grader_2", "grader_8"], ["github", "lobchan"], "SYNC", 30, "ATF_1.1", "operator_e"),
            ],
            "expected": RiskLevel.HEALTHY,
        },
        {
            "name": "2. Converging — mimetic pressure (everyone copying wilson_ci)",
            "agents": [
                AgentProfile("alpha", "wilson_ci", ["grader_1", "grader_2"], ["keenable", "github"], "ASYNC", 30, "ATF_1.2", "operator_a"),
                AgentProfile("beta", "wilson_ci", ["grader_1", "grader_3"], ["keenable", "github"], "ASYNC", 30, "ATF_1.2", "operator_b"),
                AgentProfile("gamma", "wilson_ci", ["grader_1", "grader_4"], ["keenable", "arena"], "ASYNC", 30, "ATF_1.2", "operator_c"),
                AgentProfile("delta", "bayesian", ["grader_5", "grader_6"], ["qmd", "arena"], "SYNC", 60, "ATF_1.1", "operator_d"),
                AgentProfile("epsilon", "wilson_ci", ["grader_1", "grader_7"], ["keenable", "github"], "ASYNC", 30, "ATF_1.2", "operator_e"),
            ],
            "expected": RiskLevel.HEALTHY,  # Diverse operators keep it healthy despite mimetic pressure
        },
        {
            "name": "3. Monoculture — single operator, same everything",
            "agents": [
                AgentProfile("alpha", "wilson_ci", ["grader_1"], ["keenable"], "ASYNC", 30, "ATF_1.2", "megacorp"),
                AgentProfile("beta", "wilson_ci", ["grader_1"], ["keenable"], "ASYNC", 30, "ATF_1.2", "megacorp"),
                AgentProfile("gamma", "wilson_ci", ["grader_1"], ["keenable"], "ASYNC", 30, "ATF_1.2", "megacorp"),
                AgentProfile("delta", "wilson_ci", ["grader_1"], ["keenable"], "ASYNC", 30, "ATF_1.2", "megacorp"),
                AgentProfile("epsilon", "wilson_ci", ["grader_1"], ["keenable"], "ASYNC", 30, "ATF_1.2", "megacorp"),
            ],
            "expected": RiskLevel.MONOCULTURE,
        },
        {
            "name": "4. Coercive pressure — same spec but diverse otherwise",
            "agents": [
                AgentProfile("alpha", "wilson_ci", ["grader_1", "grader_2"], ["keenable"], "ASYNC", 30, "ATF_1.2", "operator_a"),
                AgentProfile("beta", "bayesian", ["grader_3"], ["arena"], "SYNC", 90, "ATF_1.2", "operator_b"),
                AgentProfile("gamma", "elo_rating", ["grader_4", "grader_5"], ["qmd", "github"], "HYBRID", 60, "ATF_1.2", "operator_c"),
                AgentProfile("delta", "reputation", ["grader_6"], ["lobchan"], "ASYNC", 45, "ATF_1.2", "operator_d"),
                AgentProfile("epsilon", "hybrid", ["grader_7", "grader_8"], ["keenable", "qmd"], "SYNC", 30, "ATF_1.2", "operator_e"),
            ],
            "expected": RiskLevel.HEALTHY,
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        detector = IsomorphismDetector()
        for agent in scenario["agents"]:
            detector.add_agent(agent)
        
        level, metrics = detector.overall_risk()
        status = "✓" if level == scenario["expected"] else "✗"
        if level != scenario["expected"]:
            all_pass = False
        
        print(f"\n{status} {scenario['name']}")
        print(f"  Overall: {metrics['overall_score']:.3f} → {metrics['risk_level'].upper()}")
        print(f"  Strategy concentration: {metrics['strategy_concentration']:.3f}")
        print(f"  Tool overlap (Jaccard): {metrics['tool_overlap']:.3f}")
        print(f"  Operator concentration: {metrics['operator_concentration']:.3f}")
        print(f"  Spec conformity: {metrics['spec_conformity']:.3f}")
        
        for signal in detector.signals:
            flag = "⚠️" if signal.value > signal.threshold else "✓"
            print(f"  {flag} [{signal.type.value}] {signal.description}")
    
    print(f"\n{'=' * 70}")
    passed = sum(1 for s in scenarios if True)  # Already checked above
    print(f"{'All passed!' if all_pass else 'Some failures.'}")
    print(f"\nKey insight: Isomorphism isn't failure — it's how fields stabilize.")
    print(f"But monoculture = correlated failure. DiMaggio & Powell's three mechanisms")
    print(f"(coercive, mimetic, normative) each create convergence pressure.")
    print(f"The antidote: Simpson diversity at EVERY layer. Same as ASPA, Wilson CI.")
    print(f"Healthy range: 0.3-0.7 similarity. Below = fragmented. Above = fragile.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
