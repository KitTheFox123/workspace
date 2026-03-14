#!/usr/bin/env python3
"""
Finality gate simulator for agent cert issuance.

Models the reorg risk when gating cert issuance on different
commitment levels across chains.

Based on:
- Trail of Bits "Engineer's Guide to Blockchain Finality" (2023)
- Helius: Solana commitment levels (processed/confirmed/finalized)
- ETH May 2023 finality stall incident (9 epochs unfinalized)

Key insight: block delays are NOT adequate for provable-finality chains.
Must query actual finality state.
"""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChainConfig:
    name: str
    finality_type: str  # "probabilistic" | "provable_delayed" | "provable_instant"
    avg_finality_seconds: float
    reorg_probability: float  # per-block probability of reorg at confirmation
    finality_stall_probability: float  # probability of finality mechanism stalling
    max_stall_blocks: int  # how many blocks can pass without finality


CHAINS = {
    "solana": ChainConfig(
        name="Solana",
        finality_type="provable_delayed",
        avg_finality_seconds=13.0,  # 32 slots × 400ms
        reorg_probability=0.001,  # very low after confirmed
        finality_stall_probability=0.0001,
        max_stall_blocks=100,
    ),
    "ethereum": ChainConfig(
        name="Ethereum PoS",
        finality_type="provable_delayed",
        avg_finality_seconds=768.0,  # 2 epochs × 32 slots × 12s
        reorg_probability=0.0005,
        finality_stall_probability=0.001,  # May 2023 incident
        max_stall_blocks=288,  # 9 epochs worth
    ),
    "bitcoin": ChainConfig(
        name="Bitcoin",
        finality_type="probabilistic",
        avg_finality_seconds=3600.0,  # 6 blocks × 600s
        reorg_probability=0.01,  # higher without provable finality
        finality_stall_probability=0.0,  # N/A for probabilistic
        max_stall_blocks=0,
    ),
    "cosmos": ChainConfig(
        name="Cosmos (Tendermint)",
        finality_type="provable_instant",
        avg_finality_seconds=6.0,
        reorg_probability=0.0,  # instant finality = no reorg
        finality_stall_probability=0.005,  # can halt
        max_stall_blocks=0,
    ),
}


@dataclass
class IssuanceResult:
    chain: str
    strategy: str
    issued: int
    double_issued: int  # certs issued for reorged deposits
    stall_events: int
    avg_latency_s: float
    grade: str


def simulate_issuance(
    chain: ChainConfig,
    strategy: str,  # "block_delay" | "finality_query" | "confirmation_only"
    block_delay: int = 12,
    n_deposits: int = 10000,
) -> IssuanceResult:
    issued = 0
    double_issued = 0
    stall_events = 0
    total_latency = 0.0

    for _ in range(n_deposits):
        # Simulate deposit
        reorged = random.random() < chain.reorg_probability
        stalled = random.random() < chain.finality_stall_probability

        if stalled:
            stall_events += 1

        if strategy == "confirmation_only":
            # Issue on first confirmation — fast but dangerous
            issued += 1
            total_latency += chain.avg_finality_seconds * 0.1  # ~10% of finality time
            if reorged:
                double_issued += 1

        elif strategy == "block_delay":
            # Wait N blocks — traditional approach
            issued += 1
            delay_seconds = block_delay * (chain.avg_finality_seconds / 32)
            total_latency += delay_seconds

            if stalled and chain.finality_type == "provable_delayed":
                # During stall, block delay gives false confidence
                # Trail of Bits: "block delays are not adequate"
                if reorged or random.random() < 0.05:  # 5% risk during stall
                    double_issued += 1
            elif reorged and chain.finality_type == "probabilistic":
                # For probabilistic chains, block delay IS the mechanism
                # Reduce risk based on delay depth
                if random.random() < (1.0 / (block_delay + 1)):
                    double_issued += 1

        elif strategy == "finality_query":
            # Query actual finality state — correct approach
            issued += 1
            if stalled:
                # During stall, we WAIT — no issuance until finality resumes
                total_latency += chain.avg_finality_seconds + (
                    chain.max_stall_blocks * 0.4
                )
                # Still safe — we waited for actual finality
            else:
                total_latency += chain.avg_finality_seconds

            if chain.finality_type == "provable_instant":
                pass  # Zero reorg risk
            elif chain.finality_type == "provable_delayed":
                pass  # Finality query = safe
            else:  # probabilistic
                if reorged and random.random() < (1.0 / 100):
                    double_issued += 1  # Residual risk for probabilistic

    avg_latency = total_latency / max(issued, 1)

    # Grade
    if double_issued == 0:
        grade = "A"
    elif double_issued / issued < 0.001:
        grade = "B"
    elif double_issued / issued < 0.01:
        grade = "C"
    elif double_issued / issued < 0.05:
        grade = "D"
    else:
        grade = "F"

    return IssuanceResult(
        chain=chain.name,
        strategy=strategy,
        issued=issued,
        double_issued=double_issued,
        stall_events=stall_events,
        avg_latency_s=avg_latency,
        grade=grade,
    )


def main():
    random.seed(42)
    n = 10000

    print("=" * 70)
    print("FINALITY GATE SIMULATOR — Agent Cert Issuance")
    print("Trail of Bits 2023: block delays ≠ finality for provable chains")
    print(f"Simulating {n} deposits per scenario")
    print("=" * 70)

    strategies = ["confirmation_only", "block_delay", "finality_query"]

    for chain_key, chain in CHAINS.items():
        print(f"\n{'─' * 70}")
        print(f"  {chain.name} ({chain.finality_type})")
        print(f"  Avg finality: {chain.avg_finality_seconds:.0f}s | "
              f"Reorg prob: {chain.reorg_probability} | "
              f"Stall prob: {chain.finality_stall_probability}")
        print(f"{'─' * 70}")
        print(f"  {'Strategy':<22} {'Issued':>7} {'Double':>7} {'Stalls':>7} "
              f"{'Latency':>10} {'Grade':>6}")

        for strat in strategies:
            if strat == "finality_query" and chain.finality_type == "probabilistic":
                # For probabilistic chains, finality_query = longer block delay
                pass
            result = simulate_issuance(chain, strat, block_delay=12, n_deposits=n)
            print(f"  {result.strategy:<22} {result.issued:>7} "
                  f"{result.double_issued:>7} {result.stall_events:>7} "
                  f"{result.avg_latency_s:>9.1f}s {result.grade:>6}")

    print(f"\n{'=' * 70}")
    print("KEY FINDINGS:")
    print("  1. confirmation_only = fast but HIGH double-issuance risk")
    print("  2. block_delay = adequate for probabilistic, FAILS during stalls")
    print("  3. finality_query = correct for provable chains, higher latency")
    print("  4. Solana: use 'finalized' commitment (32 slot lockout)")
    print("  5. ETH: use eth_getBlockByNumber('finalized') — NOT block count")
    print("  6. Cosmos/instant: every block is final, just check for halts")
    print("=" * 70)


if __name__ == "__main__":
    main()
