#!/usr/bin/env python3
"""
bridge-trust-boundary.py — Cross-chain trust boundary analyzer.

Based on Zhang et al. (RAID 2024, Ohio State): 35 bridge attacks, $2.83B lost.
12 attack surfaces across 2 communication models.

Models trust boundaries between chains and identifies where cert DAG
attestations need "witness nodes" at chain/trust boundaries.

Key insight from gendolf: "Most bridge exploits happened because trust
boundaries between chains were poorly defined, not because core logic was wrong."
"""

import json
from dataclasses import dataclass, field
from enum import Enum


class VerificationType(Enum):
    EXTERNAL = "external"      # 22/30 bridges — multi-sig/MPC validators
    OPTIMISTIC = "optimistic"  # 3/30 — challenge period
    LOCAL = "local"            # 2/30 — HTLC atomic swaps
    NATIVE = "native"          # 3/30 — light client (most secure)


class AttackSurface(Enum):
    # Both models
    A1_FRONTEND_PHISHING = "front-end phishing"
    A2_INACCURATE_DEPOSIT = "inaccurate deposit"
    A3_MISHANDLING_EVENTS = "mishandling events"
    A4_MISMATCHED_TX = "mismatched transactions"
    A5_SINGLE_POINT_FAILURE = "single points of failure"
    A6_RUGPULL = "rugpull"
    A7_VULNERABLE_CONTRACTS = "vulnerable contracts"
    # Lock-and-mint only
    A8_PROBLEMATIC_MINT = "problematic mint"
    A9_FAKE_BURN = "fake burn"
    A10_INCORRECT_RELEASE = "incorrect release"
    A11_REPLAYED_WITHDRAW = "replayed withdraw"
    # Liquidity-pool only
    A12_INCONSISTENT_TRANSFER = "inconsistent transfer"


class VulnCategory(Enum):
    PERMISSION_ISSUE = "PI"  # 20/35 attacks
    LOGIC_ISSUE = "LI"       # 5/35
    EVENT_ISSUE = "EI"       # 8/35
    FRONTEND_ISSUE = "FI"    # 2/35


# Real attack data from RAID 2024
ATTACK_DB = [
    {"name": "Poly Network", "date": "2021-08-10", "loss_m": 600, "vuln": "V1", "cat": "PI"},
    {"name": "Ronin Network", "date": "2022-03-29", "loss_m": 625, "vuln": "V5", "cat": "PI"},
    {"name": "Binance Bridge", "date": "2022-10-06", "loss_m": 566, "vuln": "V2", "cat": "PI"},
    {"name": "Wormhole", "date": "2022-02-02", "loss_m": 320, "vuln": "V4", "cat": "PI"},
    {"name": "Nomad", "date": "2022-08-02", "loss_m": 190, "vuln": "V7", "cat": "LI"},
    {"name": "Multichain", "date": "2023-07-06", "loss_m": 126, "vuln": "V5", "cat": "PI"},
    {"name": "Horizon Bridge", "date": "2022-06-24", "loss_m": 100, "vuln": "V5", "cat": "PI"},
    {"name": "pNetwork", "date": "2022-11-04", "loss_m": 108, "vuln": "V5", "cat": "PI"},
    {"name": "Heco Bridge", "date": "2023-11-22", "loss_m": 86.28, "vuln": "V5", "cat": "PI"},
    {"name": "Orbit Bridge", "date": "2023-12-31", "loss_m": 82, "vuln": "V5", "cat": "PI"},
    {"name": "Qubit", "date": "2022-01-27", "loss_m": 80, "vuln": "V8", "cat": "EI"},
]


@dataclass
class TrustBoundary:
    """A boundary between two trust domains (chains, validator sets, etc.)."""
    chain_a: str
    chain_b: str
    verification: VerificationType
    exposed_surfaces: list = field(default_factory=list)
    witness_nodes: int = 0  # cert DAG witness nodes at this boundary
    
    def risk_score(self) -> float:
        """Higher = more risk. Based on verification type and exposed surfaces."""
        base = {
            VerificationType.EXTERNAL: 0.7,
            VerificationType.OPTIMISTIC: 0.5,
            VerificationType.LOCAL: 0.3,
            VerificationType.NATIVE: 0.1,
        }[self.verification]
        
        surface_penalty = len(self.exposed_surfaces) * 0.05
        witness_discount = min(self.witness_nodes * 0.1, 0.3)
        
        return min(1.0, max(0.0, base + surface_penalty - witness_discount))
    
    def recommendations(self) -> list:
        recs = []
        if self.verification == VerificationType.EXTERNAL:
            recs.append("Increase validator decentralization (Ronin: 5-of-9 → 21 validators post-hack)")
        if self.witness_nodes == 0:
            recs.append("Add cert DAG witness nodes at boundary (sign both branches at fork)")
        if AttackSurface.A5_SINGLE_POINT_FAILURE in self.exposed_surfaces:
            recs.append("Distribute key management — 10/35 attacks were leaked keys (V5)")
        if AttackSurface.A3_MISHANDLING_EVENTS in self.exposed_surfaces:
            recs.append("Verify event source contract — 5/35 attacks used fake events (V9)")
        return recs


def analyze_portfolio(boundaries: list) -> dict:
    """Analyze a set of trust boundaries."""
    total_risk = sum(b.risk_score() for b in boundaries)
    avg_risk = total_risk / len(boundaries) if boundaries else 0
    
    # Find worst boundary
    worst = max(boundaries, key=lambda b: b.risk_score()) if boundaries else None
    
    # Attack surface coverage
    all_surfaces = set()
    for b in boundaries:
        all_surfaces.update(b.exposed_surfaces)
    
    return {
        "boundary_count": len(boundaries),
        "avg_risk": round(avg_risk, 3),
        "worst_boundary": f"{worst.chain_a}↔{worst.chain_b}" if worst else "none",
        "worst_risk": round(worst.risk_score(), 3) if worst else 0,
        "unique_attack_surfaces": len(all_surfaces),
        "total_witness_nodes": sum(b.witness_nodes for b in boundaries),
    }


def demo():
    print("=" * 60)
    print("BRIDGE TRUST BOUNDARY ANALYZER")
    print("Based on Zhang et al. (RAID 2024) — 35 attacks, $2.83B lost")
    print("=" * 60)
    
    # Attack statistics
    print("\n📊 ATTACK STATISTICS (Apr 2021 — Apr 2024)")
    print(f"  Total attacks: 35")
    print(f"  Total losses: $2.83B")
    
    by_cat = {}
    for a in ATTACK_DB:
        cat = a["cat"]
        by_cat.setdefault(cat, {"count": 0, "loss": 0})
        by_cat[cat]["count"] += 1
        by_cat[cat]["loss"] += a["loss_m"]
    
    for cat, data in sorted(by_cat.items(), key=lambda x: -x[1]["loss"]):
        print(f"  {cat}: {data['count']} attacks, ${data['loss']:.0f}M lost")
    
    print(f"\n  Key finding: Permission Issues (PI) = {by_cat.get('PI', {}).get('count', 0)}/35 attacks")
    print(f"  Leaked keys (V5) alone = 10/35 attacks")
    
    # Demo boundaries
    boundaries = [
        TrustBoundary(
            "Ethereum", "BNB Chain",
            VerificationType.EXTERNAL,
            [AttackSurface.A5_SINGLE_POINT_FAILURE, AttackSurface.A3_MISHANDLING_EVENTS,
             AttackSurface.A7_VULNERABLE_CONTRACTS],
            witness_nodes=0
        ),
        TrustBoundary(
            "Ethereum", "Solana",
            VerificationType.EXTERNAL,
            [AttackSurface.A5_SINGLE_POINT_FAILURE, AttackSurface.A8_PROBLEMATIC_MINT],
            witness_nodes=1
        ),
        TrustBoundary(
            "Ethereum", "Near",
            VerificationType.NATIVE,
            [AttackSurface.A7_VULNERABLE_CONTRACTS],
            witness_nodes=2
        ),
        TrustBoundary(
            "Ethereum", "Polygon",
            VerificationType.OPTIMISTIC,
            [AttackSurface.A11_REPLAYED_WITHDRAW],
            witness_nodes=1
        ),
    ]
    
    print(f"\n{'─' * 60}")
    print("TRUST BOUNDARY ANALYSIS")
    
    for b in boundaries:
        risk = b.risk_score()
        risk_bar = "█" * int(risk * 20) + "░" * (20 - int(risk * 20))
        print(f"\n  {b.chain_a} ↔ {b.chain_b}")
        print(f"    Verification: {b.verification.value}")
        print(f"    Risk: [{risk_bar}] {risk:.2f}")
        print(f"    Surfaces: {len(b.exposed_surfaces)} | Witnesses: {b.witness_nodes}")
        
        recs = b.recommendations()
        if recs:
            for r in recs:
                print(f"    ⚠️  {r}")
    
    # Portfolio
    portfolio = analyze_portfolio(boundaries)
    print(f"\n{'=' * 60}")
    print("PORTFOLIO SUMMARY")
    print(f"  Boundaries: {portfolio['boundary_count']}")
    print(f"  Avg risk: {portfolio['avg_risk']}")
    print(f"  Worst: {portfolio['worst_boundary']} ({portfolio['worst_risk']})")
    print(f"  Witness nodes: {portfolio['total_witness_nodes']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Trust boundaries, not logic bugs, cause most")
    print("bridge exploits. Cert DAG witness nodes at chain boundaries")
    print("create accountability for cross-chain attestation forks.")
    print("(gendolf: 'different finality models, different validator")
    print("sets, different failure modes')")
    print("=" * 60)


if __name__ == "__main__":
    demo()
