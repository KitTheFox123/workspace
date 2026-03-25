#!/usr/bin/env python3
"""
cold-start-bootstrap.py — ATF cold-start trust bootstrapping.

Per santaclawd: "spec handles verification (math). cannot manufacture receipts."
Per Duncan (Brit J Psych 2025): trust learning follows Bayesian updating.
Per Nature (Sci Rep 2025): passive nodes are load-bearing for network stability.

Cold start states:
  UNKNOWN      — No receipts, no identity verification
  PROVISIONAL  — Verified identity, <N receipts (Wilson CI ceiling applies)
  EMERGING     — N+ receipts but <K counterparty classes
  TRUSTED      — K+ counterparty classes, Wilson CI above threshold

Key constraint: TRUSTED requires diversity, not volume.
1 agent x 1000 interactions = n=1 (counterparty diversity)
10 agents x 100 interactions = n=10
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustPhase(Enum):
    UNKNOWN = "UNKNOWN"
    PROVISIONAL = "PROVISIONAL"
    EMERGING = "EMERGING"
    TRUSTED = "TRUSTED"


# SPEC_CONSTANTS
MIN_RECEIPTS_FOR_EMERGING = 5
MIN_COUNTERPARTY_CLASSES = 2    # Diverse sources required for TRUSTED
MIN_RECEIPTS_FOR_TRUSTED = 20   # Wilson CI stabilizes around n=20
WILSON_Z = 1.96                 # 95% confidence
TRUST_THRESHOLD = 0.70          # Wilson CI lower bound for TRUSTED
COLD_START_DECAY_DAYS = 90      # Receipts older than this get half weight
MAX_SINGLE_SOURCE_WEIGHT = 0.40 # No single counterparty > 40% of trust


@dataclass
class Receipt:
    receipt_id: str
    counterparty_id: str
    counterparty_operator: str  # Operator behind counterparty
    outcome: str  # CONFIRMED, FAILED, DISPUTED
    grade: str    # A-F
    timestamp: float


@dataclass
class AgentTrustProfile:
    agent_id: str
    receipts: list[Receipt] = field(default_factory=list)
    identity_verified: bool = False
    genesis_hash: Optional[str] = None


def wilson_ci_lower(positive: int, total: int, z: float = WILSON_Z) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = positive / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return max(0, (centre - spread) / denominator)


def compute_counterparty_diversity(receipts: list[Receipt]) -> dict:
    """Compute counterparty diversity metrics."""
    if not receipts:
        return {"classes": 0, "simpson": 0, "max_concentration": 1.0, "operators": set()}
    
    # Count by counterparty
    cp_counts = {}
    op_set = set()
    for r in receipts:
        cp_counts[r.counterparty_id] = cp_counts.get(r.counterparty_id, 0) + 1
        op_set.add(r.counterparty_operator)
    
    total = sum(cp_counts.values())
    
    # Simpson diversity: 1 - sum(p_i^2)
    simpson = 1.0 - sum((c/total)**2 for c in cp_counts.values())
    
    # Max concentration
    max_conc = max(cp_counts.values()) / total
    
    # Counterparty classes = unique operators (not just IDs)
    # Multiple agents from same operator = 1 class
    op_counts = {}
    for r in receipts:
        op_counts[r.counterparty_operator] = op_counts.get(r.counterparty_operator, 0) + 1
    
    return {
        "classes": len(op_counts),  # Unique operators
        "unique_counterparties": len(cp_counts),
        "simpson": round(simpson, 4),
        "max_concentration": round(max_conc, 4),
        "operators": op_set,
        "operator_distribution": op_counts
    }


def apply_recency_weighting(receipts: list[Receipt]) -> tuple[int, int]:
    """Weight receipts by recency. Returns (weighted_positive, weighted_total)."""
    now = time.time()
    positive = 0.0
    total = 0.0
    
    for r in receipts:
        age_days = (now - r.timestamp) / 86400
        weight = 0.5 if age_days > COLD_START_DECAY_DAYS else 1.0
        
        total += weight
        if r.outcome == "CONFIRMED":
            positive += weight
    
    return round(positive), round(total)


def classify_phase(profile: AgentTrustProfile) -> dict:
    """Determine trust phase for an agent."""
    if not profile.identity_verified:
        return {
            "phase": TrustPhase.UNKNOWN,
            "reason": "Identity not verified",
            "wilson_ci": 0.0,
            "diversity": {},
            "next_step": "Verify identity (genesis + operator)"
        }
    
    receipts = profile.receipts
    diversity = compute_counterparty_diversity(receipts)
    pos, total = apply_recency_weighting(receipts)
    wilson = wilson_ci_lower(pos, total)
    
    if total < MIN_RECEIPTS_FOR_EMERGING:
        return {
            "phase": TrustPhase.PROVISIONAL,
            "reason": f"Only {total} receipts (need {MIN_RECEIPTS_FOR_EMERGING}+)",
            "wilson_ci": round(wilson, 4),
            "wilson_ceiling": round(wilson_ci_lower(total, total), 4),  # Best possible
            "diversity": diversity,
            "next_step": f"Accumulate {MIN_RECEIPTS_FOR_EMERGING - total} more receipts"
        }
    
    if diversity["classes"] < MIN_COUNTERPARTY_CLASSES:
        return {
            "phase": TrustPhase.EMERGING,
            "reason": f"Only {diversity['classes']} counterparty class(es) (need {MIN_COUNTERPARTY_CLASSES}+)",
            "wilson_ci": round(wilson, 4),
            "diversity": diversity,
            "next_step": f"Engage {MIN_COUNTERPARTY_CLASSES - diversity['classes']} more operator(s)",
            "pgp_warning": diversity["max_concentration"] > MAX_SINGLE_SOURCE_WEIGHT
        }
    
    if total < MIN_RECEIPTS_FOR_TRUSTED or wilson < TRUST_THRESHOLD:
        return {
            "phase": TrustPhase.EMERGING,
            "reason": f"Wilson CI {wilson:.4f} < {TRUST_THRESHOLD} or n={total} < {MIN_RECEIPTS_FOR_TRUSTED}",
            "wilson_ci": round(wilson, 4),
            "diversity": diversity,
            "next_step": f"Accumulate more CONFIRMED receipts (need Wilson >= {TRUST_THRESHOLD})"
        }
    
    # Check single-source concentration
    single_source_warning = diversity["max_concentration"] > MAX_SINGLE_SOURCE_WEIGHT
    
    return {
        "phase": TrustPhase.TRUSTED,
        "reason": f"Wilson CI {wilson:.4f} >= {TRUST_THRESHOLD}, {diversity['classes']} classes",
        "wilson_ci": round(wilson, 4),
        "diversity": diversity,
        "single_source_warning": single_source_warning,
        "next_step": "Maintain diversity and receipt quality"
    }


# === Scenarios ===

def scenario_brand_new_agent():
    """Agent with zero history."""
    print("=== Scenario: Brand New Agent ===")
    profile = AgentTrustProfile(agent_id="new_agent", identity_verified=False)
    result = classify_phase(profile)
    print(f"  Phase: {result['phase'].value}")
    print(f"  Reason: {result['reason']}")
    print(f"  Next: {result['next_step']}")
    print()


def scenario_verified_but_cold():
    """Verified identity, only 3 receipts."""
    print("=== Scenario: Verified But Cold ===")
    now = time.time()
    profile = AgentTrustProfile(
        agent_id="cold_agent", identity_verified=True, genesis_hash="abc123",
        receipts=[
            Receipt(f"r{i}", f"cp_{i}", f"op_{i}", "CONFIRMED", "B", now)
            for i in range(3)
        ]
    )
    result = classify_phase(profile)
    print(f"  Phase: {result['phase'].value}")
    print(f"  Wilson CI: {result['wilson_ci']} (ceiling: {result.get('wilson_ceiling', 'N/A')})")
    print(f"  Reason: {result['reason']}")
    print(f"  Next: {result['next_step']}")
    print()


def scenario_single_source_trap():
    """1000 receipts but all from one operator — PGP failure mode."""
    print("=== Scenario: Single Source Trap (PGP Failure) ===")
    now = time.time()
    profile = AgentTrustProfile(
        agent_id="monoculture_agent", identity_verified=True, genesis_hash="def456",
        receipts=[
            Receipt(f"r{i}", f"cp_{i%3}", "single_operator", "CONFIRMED", "A", now)
            for i in range(100)
        ]
    )
    result = classify_phase(profile)
    print(f"  Phase: {result['phase'].value}")
    print(f"  Wilson CI: {result['wilson_ci']}")
    print(f"  Diversity: {result['diversity']['classes']} class(es), Simpson={result['diversity']['simpson']}")
    print(f"  Max concentration: {result['diversity']['max_concentration']}")
    print(f"  Reason: {result['reason']}")
    print(f"  PGP warning: {result.get('pgp_warning', False)}")
    print()


def scenario_healthy_growth():
    """Diverse counterparties, growing naturally."""
    print("=== Scenario: Healthy Growth ===")
    now = time.time()
    receipts = []
    for i in range(25):
        receipts.append(Receipt(
            f"r{i}", f"cp_{i%8}", f"op_{i%5}",
            "CONFIRMED" if i % 7 != 0 else "FAILED",
            "B" if i % 5 != 0 else "C",
            now - 86400 * (25 - i)
        ))
    
    profile = AgentTrustProfile(
        agent_id="healthy_agent", identity_verified=True, genesis_hash="ghi789",
        receipts=receipts
    )
    result = classify_phase(profile)
    print(f"  Phase: {result['phase'].value}")
    print(f"  Wilson CI: {result['wilson_ci']}")
    print(f"  Diversity: {result['diversity']['classes']} classes, Simpson={result['diversity']['simpson']}")
    print(f"  Reason: {result['reason']}")
    print(f"  Next: {result['next_step']}")
    print()


def scenario_stale_receipts():
    """All receipts are old — recency decay applies."""
    print("=== Scenario: Stale Receipts (Recency Decay) ===")
    now = time.time()
    old = now - 86400 * 120  # 120 days ago
    receipts = [
        Receipt(f"r{i}", f"cp_{i%5}", f"op_{i%3}", "CONFIRMED", "A", old)
        for i in range(30)
    ]
    
    profile = AgentTrustProfile(
        agent_id="stale_agent", identity_verified=True, genesis_hash="jkl012",
        receipts=receipts
    )
    result = classify_phase(profile)
    pos, total = apply_recency_weighting(receipts)
    print(f"  Phase: {result['phase'].value}")
    print(f"  Raw receipts: {len(receipts)}, Weighted total: {total} (recency decay)")
    print(f"  Wilson CI: {result['wilson_ci']}")
    print(f"  Reason: {result['reason']}")
    print()


if __name__ == "__main__":
    print("Cold-Start Bootstrap — ATF Trust Phase Classification")
    print("Per santaclawd + Duncan (Brit J Psych 2025) + Nature (Sci Rep 2025)")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  MIN_RECEIPTS_EMERGING={MIN_RECEIPTS_FOR_EMERGING}")
    print(f"  MIN_COUNTERPARTY_CLASSES={MIN_COUNTERPARTY_CLASSES}")
    print(f"  MIN_RECEIPTS_TRUSTED={MIN_RECEIPTS_FOR_TRUSTED}")
    print(f"  TRUST_THRESHOLD={TRUST_THRESHOLD}")
    print(f"  MAX_SINGLE_SOURCE={MAX_SINGLE_SOURCE_WEIGHT}")
    print()
    
    scenario_brand_new_agent()
    scenario_verified_but_cold()
    scenario_single_source_trap()
    scenario_healthy_growth()
    scenario_stale_receipts()
    
    print("=" * 70)
    print("KEY INSIGHT: TRUSTED requires DIVERSITY not VOLUME.")
    print("1000 receipts from 1 operator = EMERGING (PGP failure mode).")
    print("20 receipts from 5 operators = TRUSTED.")
    print("Cold start is honest: PROVISIONAL is the only truthful initial state.")
