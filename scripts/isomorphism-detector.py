#!/usr/bin/env python3
"""
isomorphism-detector.py — Detect institutional isomorphism in agent registries.

DiMaggio & Powell (1983) "The Iron Cage Revisited": organizations in a field
become structurally similar through three mechanisms:
1. COERCIVE — external pressure (mandates, standards, regulations)
2. MIMETIC — uncertainty-driven copying (model successful peers)
3. NORMATIVE — professionalization (shared training, networks)

Applied to agent trust registries:
- Coercive: platform mandates (e.g., "must use DKIM", "must have ASPA record")
- Mimetic: registries copying each other's trust policies under uncertainty
- Normative: agent "best practices" propagated through shared tools/frameworks

Why this matters for ATF:
- Isomorphism in graders = correlated attestation = WISDOM OF CROWDS FAILS
  (Nature 2025: correlated voters destroy ensemble accuracy)
- Isomorphism in registries = monoculture = single point of policy failure
- Diversity is load-bearing. Detecting convergence is a security function.

The grader-drift-detector.py catches dynamic convergence.
This tool catches STRUCTURAL convergence — same policies, same tools, same approach.

Sources:
- DiMaggio & Powell (1983) "The Iron Cage Revisited" ASR 48(2):147-160
- Powell & DiMaggio (2023) "The Iron Cage Redux" Organization Theory 4(4)
- Nature (2025) Wisdom of crowds fails with correlated voters
- grader-drift-detector.py (Page-Hinkley for dynamic convergence)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone
import math


class IsomorphismType(Enum):
    """DiMaggio & Powell's three mechanisms."""
    COERCIVE = "coercive"      # External pressure / mandates
    MIMETIC = "mimetic"        # Uncertainty-driven copying
    NORMATIVE = "normative"    # Professionalization / shared training


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RegistryProfile:
    """Structural profile of an agent registry."""
    registry_id: str
    # Policy configuration
    trust_decay_rate: float          # 0.0-1.0 per hop
    max_chain_length: int            # Max trust chain hops
    epoch_duration_days: int         # Checkpoint frequency
    stale_window_hours: int          # STALE grace period
    grader_pool_size: int            # Number of active graders
    quorum_threshold: float          # Required agreement ratio
    # Tool/framework adoption
    tools_used: set[str] = field(default_factory=set)
    # Training/normative
    framework_version: str = ""
    grader_training_source: str = ""
    # Governance
    mandates_adopted: set[str] = field(default_factory=set)


@dataclass 
class IsomorphismSignal:
    """A detected isomorphism signal between registries."""
    mechanism: IsomorphismType
    registries: list[str]
    dimension: str           # What converged
    similarity: float        # 0.0-1.0
    risk: RiskLevel
    evidence: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IsomorphismDetector:
    """
    Detects structural convergence across agent registries.
    
    Three detection channels (mapping DiMaggio & Powell):
    
    1. COERCIVE: Mandate adoption overlap.
       If >80% of registries adopt same mandates, policy diversity collapses.
       
    2. MIMETIC: Policy parameter clustering.
       If registries converge on same trust_decay, epoch_duration, etc.
       without mandates forcing it — they're copying each other.
       
    3. NORMATIVE: Tool/framework homogeneity.
       If all graders trained on same data, using same tools,
       they're a monoculture regardless of nominal independence.
    """
    
    def __init__(self, similarity_threshold: float = 0.8):
        self.registries: dict[str, RegistryProfile] = {}
        self.signals: list[IsomorphismSignal] = []
        self.threshold = similarity_threshold
    
    def add_registry(self, profile: RegistryProfile):
        self.registries[profile.registry_id] = profile
    
    def jaccard_similarity(self, set_a: set, set_b: set) -> float:
        """Jaccard index: |A ∩ B| / |A ∪ B|"""
        if not set_a and not set_b:
            return 1.0  # Both empty = identical
        union = set_a | set_b
        if not union:
            return 0.0
        return len(set_a & set_b) / len(union)
    
    def numeric_similarity(self, a: float, b: float, max_diff: float) -> float:
        """Similarity between two numeric values. 1.0 = identical."""
        return max(0.0, 1.0 - abs(a - b) / max_diff)
    
    def detect_coercive(self) -> list[IsomorphismSignal]:
        """
        Detect coercive isomorphism: mandate adoption overlap.
        High overlap = external pressure homogenizing the field.
        """
        signals = []
        ids = list(self.registries.keys())
        
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                r1, r2 = self.registries[ids[i]], self.registries[ids[j]]
                sim = self.jaccard_similarity(r1.mandates_adopted, r2.mandates_adopted)
                
                if sim >= self.threshold:
                    risk = RiskLevel.HIGH if sim > 0.9 else RiskLevel.MEDIUM
                    shared = r1.mandates_adopted & r2.mandates_adopted
                    signal = IsomorphismSignal(
                        mechanism=IsomorphismType.COERCIVE,
                        registries=[ids[i], ids[j]],
                        dimension="mandate_adoption",
                        similarity=sim,
                        risk=risk,
                        evidence=f"Shared mandates: {shared}. "
                                 f"Coercive pressure producing policy monoculture.",
                    )
                    signals.append(signal)
        
        return signals
    
    def detect_mimetic(self) -> list[IsomorphismSignal]:
        """
        Detect mimetic isomorphism: policy parameter clustering.
        Registries converging on same parameters WITHOUT mandate pressure.
        """
        signals = []
        ids = list(self.registries.keys())
        
        # Compare numeric policy parameters
        params = [
            ("trust_decay_rate", 1.0),
            ("max_chain_length", 10),
            ("epoch_duration_days", 90),
            ("stale_window_hours", 168),
            ("quorum_threshold", 1.0),
        ]
        
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                r1, r2 = self.registries[ids[i]], self.registries[ids[j]]
                
                # Calculate composite similarity across all parameters
                sims = []
                converged_params = []
                for param_name, max_diff in params:
                    v1 = getattr(r1, param_name)
                    v2 = getattr(r2, param_name)
                    s = self.numeric_similarity(v1, v2, max_diff)
                    sims.append(s)
                    if s >= self.threshold:
                        converged_params.append(f"{param_name}({v1}≈{v2})")
                
                avg_sim = sum(sims) / len(sims)
                
                # Only flag if NOT explained by shared mandates (that's coercive)
                mandate_sim = self.jaccard_similarity(
                    r1.mandates_adopted, r2.mandates_adopted
                )
                
                if avg_sim >= self.threshold and mandate_sim < 0.5:
                    # High parameter similarity WITHOUT shared mandates = mimetic
                    risk = RiskLevel.HIGH if avg_sim > 0.9 else RiskLevel.MEDIUM
                    signal = IsomorphismSignal(
                        mechanism=IsomorphismType.MIMETIC,
                        registries=[ids[i], ids[j]],
                        dimension="policy_parameters",
                        similarity=round(avg_sim, 3),
                        risk=risk,
                        evidence=f"Converged params: {converged_params}. "
                                 f"Low mandate overlap ({mandate_sim:.2f}) = copying, not compliance.",
                    )
                    signals.append(signal)
        
        return signals
    
    def detect_normative(self) -> list[IsomorphismSignal]:
        """
        Detect normative isomorphism: tool/framework/training homogeneity.
        Same tools + same training = correlated outputs regardless of policy.
        """
        signals = []
        ids = list(self.registries.keys())
        
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                r1, r2 = self.registries[ids[i]], self.registries[ids[j]]
                
                tool_sim = self.jaccard_similarity(r1.tools_used, r2.tools_used)
                same_framework = r1.framework_version == r2.framework_version and r1.framework_version
                same_training = r1.grader_training_source == r2.grader_training_source and r1.grader_training_source
                
                # Composite normative score
                normative_score = tool_sim * 0.4
                if same_framework:
                    normative_score += 0.3
                if same_training:
                    normative_score += 0.3
                
                if normative_score >= 0.6:
                    risk = RiskLevel.CRITICAL if same_training and tool_sim > 0.8 else RiskLevel.HIGH
                    signal = IsomorphismSignal(
                        mechanism=IsomorphismType.NORMATIVE,
                        registries=[ids[i], ids[j]],
                        dimension="tools_and_training",
                        similarity=round(normative_score, 3),
                        risk=risk,
                        evidence=f"Tool similarity: {tool_sim:.2f}. "
                                 f"Same framework: {same_framework}. "
                                 f"Same training: {same_training}. "
                                 f"Professionalization = correlated graders.",
                    )
                    signals.append(signal)
        
        return signals
    
    def field_level_analysis(self) -> dict:
        """
        Aggregate field-level isomorphism metrics.
        DiMaggio & Powell's "organizational field" = the registry ecosystem.
        """
        n = len(self.registries)
        if n < 2:
            return {"error": "Need >= 2 registries for field analysis"}
        
        # Policy parameter variance (low variance = high isomorphism)
        params = ["trust_decay_rate", "max_chain_length", "epoch_duration_days",
                  "stale_window_hours", "quorum_threshold"]
        
        variances = {}
        for param in params:
            values = [getattr(r, param) for r in self.registries.values()]
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            # Normalize by mean to get coefficient of variation
            cv = (math.sqrt(var) / mean) if mean > 0 else 0
            variances[param] = round(cv, 3)
        
        # Tool ecosystem diversity (Simpson's diversity index)
        all_tools = set()
        for r in self.registries.values():
            all_tools |= r.tools_used
        
        tool_adoption = {}
        for tool in all_tools:
            count = sum(1 for r in self.registries.values() if tool in r.tools_used)
            tool_adoption[tool] = count / n
        
        # Simpson's D = 1 - Σ(pi²)
        if tool_adoption:
            simpson_d = 1 - sum(p ** 2 for p in tool_adoption.values()) / len(tool_adoption)
        else:
            simpson_d = 0
        
        # Overall field isomorphism score (0 = diverse, 1 = monoculture)
        avg_cv = sum(variances.values()) / len(variances)
        isomorphism_score = max(0, 1 - avg_cv)  # Low CV = high isomorphism
        
        return {
            "registry_count": n,
            "parameter_variation": variances,
            "tool_diversity_simpson": round(simpson_d, 3),
            "monoculture_tools": [t for t, p in tool_adoption.items() if p > 0.8],
            "isomorphism_score": round(isomorphism_score, 3),
            "risk_assessment": (
                "CRITICAL: Field approaching monoculture" if isomorphism_score > 0.8 else
                "HIGH: Significant convergence detected" if isomorphism_score > 0.6 else
                "MEDIUM: Some convergence, diversity still present" if isomorphism_score > 0.4 else
                "LOW: Healthy diversity in the field"
            ),
        }
    
    def full_scan(self) -> dict:
        """Run all detection channels and return comprehensive report."""
        coercive = self.detect_coercive()
        mimetic = self.detect_mimetic()
        normative = self.detect_normative()
        
        self.signals = coercive + mimetic + normative
        field = self.field_level_analysis()
        
        return {
            "signals": {
                "coercive": [{"registries": s.registries, "similarity": s.similarity,
                             "risk": s.risk.value, "evidence": s.evidence} for s in coercive],
                "mimetic": [{"registries": s.registries, "similarity": s.similarity,
                            "risk": s.risk.value, "evidence": s.evidence} for s in mimetic],
                "normative": [{"registries": s.registries, "similarity": s.similarity,
                              "risk": s.risk.value, "evidence": s.evidence} for s in normative],
            },
            "field_analysis": field,
            "total_signals": len(self.signals),
            "critical_count": sum(1 for s in self.signals if s.risk == RiskLevel.CRITICAL),
        }


def run_scenarios():
    """Demonstrate isomorphism detection across agent registries."""
    d = IsomorphismDetector(similarity_threshold=0.8)
    
    # Scenario: 4 registries with varying isomorphism
    d.add_registry(RegistryProfile(
        registry_id="alpha",
        trust_decay_rate=0.10,
        max_chain_length=3,
        epoch_duration_days=30,
        stale_window_hours=72,
        grader_pool_size=50,
        quorum_threshold=0.67,
        tools_used={"grader-drift-detector", "valley-free-verifier", "attestation-signer"},
        framework_version="ATF-1.2",
        grader_training_source="corpus-v3",
        mandates_adopted={"DKIM-required", "ASPA-record", "receipt-signing"},
    ))
    
    d.add_registry(RegistryProfile(
        registry_id="beta",
        trust_decay_rate=0.10,  # Same as alpha (mimetic?)
        max_chain_length=3,
        epoch_duration_days=30,
        stale_window_hours=72,
        grader_pool_size=45,
        quorum_threshold=0.67,
        tools_used={"grader-drift-detector", "valley-free-verifier", "attestation-signer"},
        framework_version="ATF-1.2",
        grader_training_source="corpus-v3",  # Same training!
        mandates_adopted={"receipt-signing"},  # Different mandates (less coercive)
    ))
    
    d.add_registry(RegistryProfile(
        registry_id="gamma",
        trust_decay_rate=0.15,  # Different
        max_chain_length=5,     # Different
        epoch_duration_days=14, # Different
        stale_window_hours=48,
        grader_pool_size=30,
        quorum_threshold=0.75,  # Different
        tools_used={"custom-verifier", "gamma-attestor", "attestation-signer"},
        framework_version="ATF-1.1",  # Older version
        grader_training_source="corpus-v2",  # Different training
        mandates_adopted={"DKIM-required", "ASPA-record", "receipt-signing", "epoch-checkpoint"},
    ))
    
    d.add_registry(RegistryProfile(
        registry_id="delta",
        trust_decay_rate=0.20,
        max_chain_length=2,
        epoch_duration_days=7,
        stale_window_hours=24,
        grader_pool_size=100,
        quorum_threshold=0.51,
        tools_used={"delta-stack", "custom-grader", "receipt-logger"},
        framework_version="delta-native",
        grader_training_source="proprietary",
        mandates_adopted={"receipt-signing"},
    ))
    
    print("=" * 70)
    print("INSTITUTIONAL ISOMORPHISM DETECTOR")
    print("DiMaggio & Powell (1983) applied to agent trust registries")
    print("=" * 70)
    
    result = d.full_scan()
    
    print(f"\n📊 FIELD-LEVEL ANALYSIS ({result['field_analysis']['registry_count']} registries)")
    print(f"   Isomorphism score: {result['field_analysis']['isomorphism_score']} (0=diverse, 1=monoculture)")
    print(f"   Tool diversity (Simpson): {result['field_analysis']['tool_diversity_simpson']}")
    print(f"   Monoculture tools: {result['field_analysis']['monoculture_tools']}")
    print(f"   Assessment: {result['field_analysis']['risk_assessment']}")
    
    print(f"\n   Parameter variation (coefficient of variation):")
    for param, cv in result['field_analysis']['parameter_variation'].items():
        bar = "█" * int(cv * 20) + "░" * (20 - int(cv * 20))
        print(f"     {param:25s} {bar} {cv}")
    
    for mechanism in ["coercive", "mimetic", "normative"]:
        signals = result['signals'][mechanism]
        emoji = {"coercive": "⚖️", "mimetic": "🪞", "normative": "🎓"}[mechanism]
        print(f"\n{emoji} {mechanism.upper()} ISOMORPHISM ({len(signals)} signals)")
        for s in signals:
            print(f"   [{s['risk'].upper()}] {s['registries'][0]} ↔ {s['registries'][1]}: {s['similarity']}")
            print(f"         {s['evidence'][:120]}")
    
    print(f"\n{'=' * 70}")
    print(f"Total: {result['total_signals']} signals, {result['critical_count']} critical")
    print(f"\nKey insight: Diversity is load-bearing in trust systems.")
    print(f"Correlated graders = correlated failures (Nature 2025).")
    print(f"Isomorphism detection IS a security function.")
    
    # Validate expected results
    assert result['total_signals'] > 0, "Should detect signals"
    assert result['critical_count'] > 0, "Alpha-Beta should be critical (same training)"
    assert any(s['registries'] == ['alpha', 'beta'] 
               for s in result['signals']['normative']), "Alpha-Beta normative expected"
    
    print("\n✓ All assertions passed")
    return True


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
