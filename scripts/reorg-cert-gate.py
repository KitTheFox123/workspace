#!/usr/bin/env python3
"""
Reorg-aware cert issuance gate.

Models the risk window between deposit confirmation and cert issuance
across different blockchain commitment levels. Simulates reorg scenarios
and measures when it's safe to issue a cert.

Based on:
- Solana commitment levels (Helius 2025): processed/confirmed/finalized
- Ethereum PoS finality: ~2 epoch (~12.8 min)
- Bitcoin PoW: 6 confirmations (~60 min)

Key insight: idempotency key = hash(deposit_ref + epoch_floor).
If chain reorgs, deposit_ref changes → key naturally invalidates.
No special reorg handling needed IF you gate on finality.
"""

import hashlib
import random
import time
from dataclasses import dataclass
from enum import Enum


class CommitmentLevel(Enum):
    PROCESSED = "processed"      # Fastest, least safe
    CONFIRMED = "confirmed"      # Supermajority voted
    FINALIZED = "finalized"      # Max lockout / epoch finality


class Chain(Enum):
    SOLANA = "solana"
    ETHEREUM = "ethereum"
    BITCOIN = "bitcoin"


# Approximate times and reorg probabilities
CHAIN_PARAMS = {
    Chain.SOLANA: {
        CommitmentLevel.PROCESSED: {"latency_s": 0.4, "reorg_prob": 0.05},
        CommitmentLevel.CONFIRMED: {"latency_s": 0.6, "reorg_prob": 0.001},
        CommitmentLevel.FINALIZED: {"latency_s": 13.0, "reorg_prob": 0.000001},
    },
    Chain.ETHEREUM: {
        CommitmentLevel.PROCESSED: {"latency_s": 12.0, "reorg_prob": 0.02},
        CommitmentLevel.CONFIRMED: {"latency_s": 72.0, "reorg_prob": 0.0005},
        CommitmentLevel.FINALIZED: {"latency_s": 768.0, "reorg_prob": 0.000001},
    },
    Chain.BITCOIN: {
        CommitmentLevel.PROCESSED: {"latency_s": 600.0, "reorg_prob": 0.03},
        CommitmentLevel.CONFIRMED: {"latency_s": 1800.0, "reorg_prob": 0.001},
        CommitmentLevel.FINALIZED: {"latency_s": 3600.0, "reorg_prob": 0.00001},
    },
}


@dataclass
class IssuanceResult:
    chain: Chain
    commitment: CommitmentLevel
    latency_s: float
    reorged: bool
    cert_issued: bool
    orphan_cert: bool  # cert issued but deposit reorged = BAD


def simulate_issuance(chain: Chain, commitment: CommitmentLevel, n_trials: int = 10000) -> dict:
    params = CHAIN_PARAMS[chain][commitment]
    results = {"total": n_trials, "issued": 0, "reorged": 0, "orphan_certs": 0}

    for _ in range(n_trials):
        reorged = random.random() < params["reorg_prob"]
        # Gate: only issue cert if not reorged at chosen commitment
        # But if we issue at lower commitment and reorg happens later...
        if commitment == CommitmentLevel.FINALIZED:
            cert_issued = True
            orphan = reorged  # Near-impossible
        elif commitment == CommitmentLevel.CONFIRMED:
            cert_issued = True
            orphan = reorged
        else:  # PROCESSED
            cert_issued = True
            orphan = reorged

        results["issued"] += 1 if cert_issued else 0
        results["reorged"] += 1 if reorged else 0
        results["orphan_certs"] += 1 if orphan else 0

    results["orphan_rate"] = results["orphan_certs"] / results["total"]
    results["latency_s"] = params["latency_s"]
    return results


def grade(orphan_rate: float) -> str:
    if orphan_rate < 0.0001:
        return "A"
    elif orphan_rate < 0.001:
        return "B"
    elif orphan_rate < 0.01:
        return "C"
    elif orphan_rate < 0.05:
        return "D"
    return "F"


def main():
    print("=" * 70)
    print("REORG-AWARE CERT ISSUANCE GATE")
    print("10,000 trials per scenario")
    print("=" * 70)

    for chain in Chain:
        print(f"\n{'─' * 70}")
        print(f"  {chain.value.upper()}")
        print(f"{'─' * 70}")
        print(f"  {'Commitment':<14} {'Latency':>10} {'Orphan Rate':>14} {'Orphans':>10} {'Grade':>6}")

        for commitment in CommitmentLevel:
            r = simulate_issuance(chain, commitment)
            g = grade(r["orphan_rate"])
            latency = f"{r['latency_s']:.1f}s"
            orphan_pct = f"{r['orphan_rate']*100:.3f}%"
            print(f"  {commitment.value:<14} {latency:>10} {orphan_pct:>14} {r['orphan_certs']:>10} {g:>6}")

    # Recommendation
    print(f"\n{'=' * 70}")
    print("RECOMMENDATION FOR AGENT CERT ISSUANCE")
    print("=" * 70)
    print("""
  Solana:   Gate on FINALIZED (13s). Acceptable latency for cert issuance.
  Ethereum: Gate on FINALIZED (12.8min). High-value, worth the wait.
  Bitcoin:  Gate on CONFIRMED (6 conf, ~30min). FINALIZED = 60min, overkill.

  Idempotency key = hash(deposit_ref + epoch_floor_hour).
  If reorg invalidates deposit → deposit_ref changes → key auto-invalidates.
  No orphan cert cleanup needed IF you gate on finality.

  The reorg problem is a NON-PROBLEM with correct commitment gating.
  The REAL risk: issuing on PROCESSED to reduce latency. Don't.
""")


if __name__ == "__main__":
    main()
