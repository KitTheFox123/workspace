#!/usr/bin/env python3
"""
slsa-abc-composer.py — Composes SLSA (build provenance) with ABC (runtime behavior) for agent trust.

Based on:
- SLSA v1.0 (slsa.dev): Supply-chain Levels for Software Artifacts
- Bhardwaj (arXiv 2602.22302, Feb 2026): Agent Behavioral Contracts
  - C = (P, I, G, R): Preconditions, Invariants, Governance, Recovery
  - (p, δ, k)-satisfaction: probabilistic compliance
  - Drift Bounds: D* = α/γ when γ > α (recovery > drift)
- santaclawd: "SLSA without ABC = birth cert for rogue agent"

SLSA = build-time provenance (did this agent build correctly?)
ABC = runtime behavioral bounds (is this agent behaving within bounds?)
Orthogonal. Composable. Both necessary.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class SLSALevel(Enum):
    NONE = 0       # No provenance
    L1 = 1         # Documentation of build process
    L2 = 2         # Tamper resistance of build service
    L3 = 3         # Hardened builds (hermetic, reproducible)
    L4 = 4         # Two-party review + hermetic


class ABCCompliance(Enum):
    NONE = "none"           # No behavioral contract
    SPECIFIED = "specified"  # Contract exists but not enforced
    MONITORED = "monitored"  # Runtime monitoring active
    ENFORCED = "enforced"   # Runtime enforcement + recovery


@dataclass
class ABCContract:
    """Bhardwaj's C = (P, I, G, R)"""
    preconditions: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    governance: list[str] = field(default_factory=list)
    recovery: list[str] = field(default_factory=list)
    
    # Drift parameters
    alpha: float = 0.0    # Natural drift rate
    gamma: float = 0.0    # Recovery rate
    p: float = 0.0        # Compliance probability
    delta: float = 0.0    # Allowed deviation
    k: int = 0            # Recovery steps
    
    def drift_bound(self) -> Optional[float]:
        """D* = α/γ when γ > α"""
        if self.gamma > self.alpha and self.gamma > 0:
            return self.alpha / self.gamma
        return None  # Unbounded drift
    
    def is_bounded(self) -> bool:
        return self.gamma > self.alpha


@dataclass
class AgentTrustProfile:
    name: str
    slsa_level: SLSALevel = SLSALevel.NONE
    abc_compliance: ABCCompliance = ABCCompliance.NONE
    abc_contract: Optional[ABCContract] = None
    
    # Mapping to our existing primitives
    has_genesis_anchor: bool = False
    has_scope_hash: bool = False
    has_null_receipts: bool = False
    has_wal: bool = False
    
    def composite_grade(self) -> str:
        """Grade the SLSA×ABC composition."""
        slsa_score = self.slsa_level.value / 4.0
        
        abc_scores = {
            ABCCompliance.NONE: 0.0,
            ABCCompliance.SPECIFIED: 0.25,
            ABCCompliance.MONITORED: 0.6,
            ABCCompliance.ENFORCED: 1.0,
        }
        abc_score = abc_scores[self.abc_compliance]
        
        # Bonus for drift boundedness
        drift_bonus = 0.0
        if self.abc_contract and self.abc_contract.is_bounded():
            d_star = self.abc_contract.drift_bound()
            if d_star and d_star < 0.3:
                drift_bonus = 0.1
        
        # Bonus for existing trust primitives
        primitive_bonus = sum([
            self.has_genesis_anchor * 0.05,
            self.has_scope_hash * 0.05,
            self.has_null_receipts * 0.05,
            self.has_wal * 0.05,
        ])
        
        score = slsa_score * 0.4 + abc_score * 0.4 + drift_bonus + primitive_bonus
        
        if score >= 0.8: return "A"
        if score >= 0.6: return "B"
        if score >= 0.4: return "C"
        if score >= 0.2: return "D"
        return "F"
    
    def diagnosis(self) -> str:
        if self.slsa_level == SLSALevel.NONE and self.abc_compliance == ABCCompliance.NONE:
            return "UNVERIFIED"
        if self.slsa_level.value >= 2 and self.abc_compliance == ABCCompliance.NONE:
            return "BIRTH_CERT_ONLY"  # santaclawd's warning
        if self.slsa_level == SLSALevel.NONE and self.abc_compliance != ABCCompliance.NONE:
            return "GUARDRAILS_ON_UNKNOWN_CODE"
        if self.slsa_level.value >= 2 and self.abc_compliance == ABCCompliance.ENFORCED:
            return "FULL_LIFECYCLE"
        if self.abc_compliance == ABCCompliance.MONITORED:
            return "RUNTIME_MONITORED"
        return "PARTIAL"


def build_profiles() -> list[AgentTrustProfile]:
    profiles = []
    
    # Kit's current system
    kit_contract = ABCContract(
        preconditions=["scope_manifest_signed"],
        invariants=["scope_hash_match", "style_fingerprint_stable", "null_receipt_ratio_healthy"],
        governance=["heartbeat_interval_20min", "keenable_feedback_required"],
        recovery=["rollback_to_last_checkpoint", "alert_ilya"],
        alpha=0.05, gamma=0.15, p=0.88, delta=0.1, k=3
    )
    profiles.append(AgentTrustProfile(
        name="kit_fox",
        slsa_level=SLSALevel.L1,  # genesis-anchor.py = L1 provenance
        abc_compliance=ABCCompliance.MONITORED,  # drift detection active, not enforced
        abc_contract=kit_contract,
        has_genesis_anchor=True, has_scope_hash=True,
        has_null_receipts=True, has_wal=True,
    ))
    
    # SLSA L3 but no ABC (santaclawd's warning case)
    profiles.append(AgentTrustProfile(
        name="slsa_only",
        slsa_level=SLSALevel.L3,
        abc_compliance=ABCCompliance.NONE,
        has_genesis_anchor=True,
    ))
    
    # ABC enforced but no SLSA
    abc_only = ABCContract(
        preconditions=["input_validated"],
        invariants=["output_within_bounds"],
        governance=["human_approval_required"],
        recovery=["halt_and_alert"],
        alpha=0.03, gamma=0.20, p=0.95, delta=0.05, k=2
    )
    profiles.append(AgentTrustProfile(
        name="abc_only",
        slsa_level=SLSALevel.NONE,
        abc_compliance=ABCCompliance.ENFORCED,
        abc_contract=abc_only,
    ))
    
    # Full lifecycle (the goal)
    full = ABCContract(
        preconditions=["scope_manifest_cosigned", "slsa_l3_verified"],
        invariants=["behavioral_envelope", "scope_hash", "style_stable"],
        governance=["poisson_audit", "cross_agent_attestation"],
        recovery=["bounded_rollback", "attestation_required"],
        alpha=0.02, gamma=0.25, p=0.97, delta=0.03, k=1
    )
    profiles.append(AgentTrustProfile(
        name="full_lifecycle",
        slsa_level=SLSALevel.L3,
        abc_compliance=ABCCompliance.ENFORCED,
        abc_contract=full,
        has_genesis_anchor=True, has_scope_hash=True,
        has_null_receipts=True, has_wal=True,
    ))
    
    # Unverified agent
    profiles.append(AgentTrustProfile(name="unverified"))
    
    return profiles


def main():
    print("=" * 70)
    print("SLSA × ABC COMPOSITION ANALYZER")
    print("SLSA = build provenance | ABC = runtime behavior (Bhardwaj 2026)")
    print("=" * 70)
    
    profiles = build_profiles()
    
    print(f"\n{'Agent':<20} {'SLSA':<8} {'ABC':<12} {'D*':<8} {'Grade':<6} {'Diagnosis'}")
    print("-" * 70)
    
    for p in profiles:
        d_star = "-"
        if p.abc_contract and p.abc_contract.is_bounded():
            d_star = f"{p.abc_contract.drift_bound():.3f}"
        
        print(f"{p.name:<20} L{p.slsa_level.value:<7} {p.abc_compliance.value:<12} "
              f"{d_star:<8} {p.composite_grade():<6} {p.diagnosis()}")
    
    print("\n--- Composition Rules ---")
    print("1. SLSA alone = birth certificate for potential rogue (santaclawd)")
    print("2. ABC alone = guardrails on unverified code")
    print("3. SLSA + ABC = full lifecycle trust")
    print("4. Deploy ABC FIRST — drift is continuous, builds are discrete")
    print()
    print("--- Drift Bounds Theorem (Bhardwaj) ---")
    print("D* = α/γ when γ > α")
    print("α = natural drift rate, γ = recovery rate")
    print("If recovery outpaces drift, behavior stays bounded")
    print("Our scope_hash + null_receipts + WAL = ABC invariants in practice")
    print()
    print("--- santaclawd's Question: 'which comes first?' ---")
    print("ABC. Because:")
    print("  - Drift happens every heartbeat (continuous)")
    print("  - Builds happen at deployment (discrete)")
    print("  - Runtime violations compound; build issues are fixed once")
    print("  - ABC can operate on observable outputs (no ground truth needed)")


if __name__ == "__main__":
    main()
