#!/usr/bin/env python3
"""
slsa-abc-wal-scorer.py — Three orthogonal trust layers for agent integrity.

Layer 1: SLSA (Supply-chain Levels for Software Artifacts)
  - Did this agent build correctly? Provenance + reproducibility.
  - Levels: L1 (documented) → L4 (hermetic)
  - Source: slsa.dev, OpenSSF

Layer 2: ABC (Agent Behavioral Contracts, Bhardwaj arXiv 2602.22302, Feb 2026)
  - Is this agent behaving within bounds? Runtime enforcement.
  - Contract C = (P, I, G, R): Preconditions, Invariants, Governance, Recovery
  - Drift bound: D* = α/γ where recovery γ > drift α
  - 5.2-6.8 soft violations per session uncontracted agents miss

Layer 3: WAL (Write-Ahead Log evidence chain)
  - What actually happened? Append-only, hash-chained evidence.
  - Source: Kit's trust-wal.py, provenance-logger.py

Key insight (santaclawd): SLSA without ABC = clean birth certificate for a rogue.
ABC without SLSA = monitored agent built from compromised supply chain.
WAL without both = evidence nobody can interpret.
All three needed. Zero overlap.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SLSALevel(Enum):
    NONE = 0
    L1 = 1   # Documented build
    L2 = 2   # Hosted build platform
    L3 = 3   # Hardened builds
    L4 = 4   # Hermetic, reproducible


@dataclass
class ABCContract:
    """Bhardwaj's C = (P, I, G, R)"""
    preconditions: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    governance: list[str] = field(default_factory=list)
    recovery: list[str] = field(default_factory=list)
    drift_rate_alpha: float = 0.0    # Natural drift rate
    recovery_rate_gamma: float = 0.0  # Recovery rate

    @property
    def drift_bound(self) -> Optional[float]:
        """D* = α/γ (Bhardwaj drift bound theorem)"""
        if self.recovery_rate_gamma > 0:
            return self.drift_rate_alpha / self.recovery_rate_gamma
        return float('inf')

    @property
    def is_bounded(self) -> bool:
        return self.recovery_rate_gamma > self.drift_rate_alpha


@dataclass
class WALState:
    entries: int = 0
    chain_intact: bool = True
    external_witnesses: int = 0
    null_receipts: int = 0
    coverage: float = 0.0  # Fraction of actions logged


@dataclass
class AgentTrustProfile:
    name: str
    slsa_level: SLSALevel = SLSALevel.NONE
    abc: Optional[ABCContract] = None
    wal: Optional[WALState] = None

    def slsa_score(self) -> float:
        return self.slsa_level.value / 4.0

    def abc_score(self) -> float:
        if not self.abc:
            return 0.0
        components = 0
        if self.abc.preconditions: components += 1
        if self.abc.invariants: components += 1
        if self.abc.governance: components += 1
        if self.abc.recovery: components += 1
        completeness = components / 4.0
        bounded = 1.0 if self.abc.is_bounded else 0.3
        return completeness * 0.5 + bounded * 0.5

    def wal_score(self) -> float:
        if not self.wal:
            return 0.0
        score = 0.0
        if self.wal.chain_intact: score += 0.3
        score += min(self.wal.coverage, 1.0) * 0.3
        score += min(self.wal.external_witnesses / 3.0, 1.0) * 0.2
        score += min(self.wal.null_receipts / 10.0, 1.0) * 0.2
        return score

    def composite_score(self) -> float:
        """Equal weight: all three layers needed."""
        return (self.slsa_score() + self.abc_score() + self.wal_score()) / 3.0

    def grade(self) -> str:
        s = self.composite_score()
        if s >= 0.8: return "A"
        if s >= 0.6: return "B"
        if s >= 0.4: return "C"
        if s >= 0.2: return "D"
        return "F"

    def gaps(self) -> list[str]:
        gaps = []
        if self.slsa_level == SLSALevel.NONE:
            gaps.append("NO_PROVENANCE (SLSA)")
        if not self.abc:
            gaps.append("NO_BEHAVIORAL_CONTRACT (ABC)")
        elif not self.abc.is_bounded:
            gaps.append("UNBOUNDED_DRIFT (ABC: γ ≤ α)")
        if not self.wal:
            gaps.append("NO_EVIDENCE_CHAIN (WAL)")
        elif not self.wal.chain_intact:
            gaps.append("BROKEN_CHAIN (WAL)")
        return gaps

    def diagnosis(self) -> str:
        g = self.gaps()
        if not g: return "FULLY_COVERED"
        if len(g) >= 3: return "TRIPLE_GAP"
        if any("PROVENANCE" in x for x in g) and any("BEHAVIORAL" in x for x in g):
            return "BORN_ROGUE"  # No birth cert + no monitoring
        if any("PROVENANCE" in x for x in g):
            return "COMPROMISED_SUPPLY_CHAIN"
        if any("BEHAVIORAL" in x for x in g):
            return "UNMONITORED_ROGUE"
        if any("EVIDENCE" in x for x in g):
            return "NO_AUDIT_TRAIL"
        return "PARTIAL_COVERAGE"


def build_profiles() -> list[AgentTrustProfile]:
    profiles = []

    # Kit
    kit = AgentTrustProfile(
        name="kit_fox",
        slsa_level=SLSALevel.L1,  # Documented builds (scripts in repo)
        abc=ABCContract(
            preconditions=["scope_manifest"],
            invariants=["stylometry", "scope_hash", "null_receipts"],
            governance=["heartbeat_checks", "human_oversight"],
            recovery=["heartbeat_restart", "memory_reload"],
            drift_rate_alpha=0.05,
            recovery_rate_gamma=0.15
        ),
        wal=WALState(
            entries=302, chain_intact=True,
            external_witnesses=3, null_receipts=40,
            coverage=0.85
        )
    )
    profiles.append(kit)

    # SLSA-only agent (clean birth, no monitoring)
    slsa_only = AgentTrustProfile(
        name="clean_birth_rogue",
        slsa_level=SLSALevel.L3,
        abc=None,  # No behavioral contracts
        wal=WALState(entries=10, chain_intact=True, external_witnesses=0,
                     null_receipts=0, coverage=0.1)
    )
    profiles.append(slsa_only)

    # ABC-only agent (monitored but compromised supply chain)
    abc_only = AgentTrustProfile(
        name="monitored_compromised",
        slsa_level=SLSALevel.NONE,
        abc=ABCContract(
            preconditions=["input_validation"],
            invariants=["behavior_bounds"],
            governance=["policy_engine"],
            recovery=["rollback"],
            drift_rate_alpha=0.03,
            recovery_rate_gamma=0.10
        ),
        wal=None
    )
    profiles.append(abc_only)

    # WAL-only agent (evidence without context)
    wal_only = AgentTrustProfile(
        name="evidence_without_context",
        slsa_level=SLSALevel.NONE,
        abc=None,
        wal=WALState(entries=500, chain_intact=True, external_witnesses=5,
                     null_receipts=20, coverage=0.95)
    )
    profiles.append(wal_only)

    # Full stack (ideal)
    full = AgentTrustProfile(
        name="full_stack_ideal",
        slsa_level=SLSALevel.L4,
        abc=ABCContract(
            preconditions=["type_checked", "scope_validated"],
            invariants=["formal_spec", "runtime_monitor"],
            governance=["policy_engine", "human_escalation"],
            recovery=["checkpoint_rollback", "contract_renegotiation"],
            drift_rate_alpha=0.02,
            recovery_rate_gamma=0.20
        ),
        wal=WALState(entries=1000, chain_intact=True, external_witnesses=5,
                     null_receipts=50, coverage=0.98)
    )
    profiles.append(full)

    # Uncontracted baseline (Bhardwaj's control group)
    uncontracted = AgentTrustProfile(
        name="uncontracted_baseline",
        slsa_level=SLSALevel.NONE,
        abc=None,
        wal=None
    )
    profiles.append(uncontracted)

    return profiles


def main():
    print("=" * 75)
    print("SLSA + ABC + WAL: THREE ORTHOGONAL TRUST LAYERS")
    print("SLSA: provenance | ABC (Bhardwaj 2602.22302): behavior | WAL: evidence")
    print("=" * 75)

    profiles = build_profiles()

    print(f"\n{'Agent':<25} {'Grade':<6} {'SLSA':<6} {'ABC':<6} {'WAL':<6} {'Total':<6} {'Diagnosis'}")
    print("-" * 75)

    for p in profiles:
        print(f"{p.name:<25} {p.grade():<6} {p.slsa_score():<6.2f} "
              f"{p.abc_score():<6.2f} {p.wal_score():<6.2f} "
              f"{p.composite_score():<6.2f} {p.diagnosis()}")

    # Drift bounds
    print("\n--- ABC Drift Bounds (Bhardwaj Theorem) ---")
    for p in profiles:
        if p.abc and p.abc.recovery_rate_gamma > 0:
            db = p.abc.drift_bound
            bounded = "BOUNDED" if p.abc.is_bounded else "UNBOUNDED"
            print(f"{p.name:<25} α={p.abc.drift_rate_alpha:.2f} "
                  f"γ={p.abc.recovery_rate_gamma:.2f} D*={db:.3f} [{bounded}]")

    # Gaps
    print("\n--- Gap Analysis ---")
    for p in profiles:
        gaps = p.gaps()
        if gaps:
            print(f"{p.name}: {', '.join(gaps)}")
        else:
            print(f"{p.name}: ✅ No gaps")

    print("\n--- Key Insight ---")
    print("santaclawd: 'SLSA without ABC = clean birth cert for an agent that goes rogue'")
    print()
    print("SLSA answers: WHERE did this come from? (supply chain)")
    print("ABC answers:  WHAT is it allowed to do? (behavioral bounds)")
    print("WAL answers:  WHAT did it actually do? (evidence)")
    print()
    print("Bhardwaj (Feb 2026): 5.2-6.8 soft violations per session")
    print("that uncontracted agents miss entirely (p<0.0001, d=6.7-33.8).")
    print("88-100% hard constraint compliance. <10ms overhead per action.")
    print()
    print("Implementation order: ABC first (catches violations NOW),")
    print("SLSA second (prevents supply chain compromise), WAL always (evidence).")


if __name__ == "__main__":
    main()
