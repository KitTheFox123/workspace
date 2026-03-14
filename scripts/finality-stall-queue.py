#!/usr/bin/env python3
"""
Finality stall queue simulator.

Models cert issuance behavior when blockchain finality stalls
(like ETH May 2023 Casper FFG incident — 9 epochs, ~57 min).

Compares strategies:
1. Timeout-and-issue: dangerous (issues on unfinalized blocks)
2. Queue-and-drain: correct (holds until finality resumes, drains backlog)
3. Queue-with-DLQ: queue + email notification at threshold
4. Fallback-to-confirmed: degrades to confirmed after N minutes (risky)

Based on: ETH finality incident May 2023, Trail of Bits 2023
"""

import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Deposit:
    id: str
    amount: float
    arrived_at: float  # seconds into simulation
    block_slot: int
    finalized: bool = False
    cert_issued: bool = False
    cert_valid: bool = True
    issued_at: Optional[float] = None
    channel: str = "webhook"


@dataclass
class SimResult:
    strategy: str
    total_deposits: int
    certs_issued: int
    certs_valid: int
    certs_invalid: int  # issued but block not actually final
    max_queue_depth: int
    avg_wait_secs: float
    stall_duration_secs: float
    dlq_alerts: int = 0
    grade: str = ""


def simulate(strategy: str, stall_start: float, stall_duration: float,
             n_deposits: int = 100, sim_duration: float = 7200) -> SimResult:
    """Run simulation with given strategy over sim_duration seconds."""
    deposits: list[Deposit] = []
    queue: list[Deposit] = []
    issued: list[Deposit] = []
    max_queue = 0
    dlq_alerts = 0
    dlq_threshold = 20

    # Generate deposits uniformly across simulation
    for i in range(n_deposits):
        t = random.uniform(0, sim_duration)
        slot = int(t / 12)  # ~12s per ETH slot
        deposits.append(Deposit(id=f"dep_{i}", amount=random.uniform(0.01, 1.0),
                                arrived_at=t, block_slot=slot))

    deposits.sort(key=lambda d: d.arrived_at)

    finality_resumes = stall_start + stall_duration

    for dep in deposits:
        t = dep.arrived_at
        in_stall = stall_start <= t <= finality_resumes

        # Is this deposit's block finalized?
        if t < stall_start:
            # Before stall: finality normal, ~13s delay
            dep.finalized = True
        elif t > finality_resumes + 60:
            # After stall + drain time: finality caught up
            dep.finalized = True
        else:
            dep.finalized = False

        if strategy == "timeout":
            # Issue after 60s regardless of finality
            dep.cert_issued = True
            dep.issued_at = t + 60
            dep.cert_valid = dep.finalized
            issued.append(dep)

        elif strategy == "queue_drain":
            if dep.finalized:
                dep.cert_issued = True
                dep.issued_at = t + 13  # normal finality delay
                dep.cert_valid = True
                issued.append(dep)
            else:
                queue.append(dep)
                max_queue = max(max_queue, len(queue))
                # Drain when finality resumes
                if t > finality_resumes:
                    for q in queue:
                        q.cert_issued = True
                        q.issued_at = finality_resumes + 13
                        q.cert_valid = True
                        issued.append(q)
                    queue.clear()

        elif strategy == "queue_dlq":
            if dep.finalized:
                dep.cert_issued = True
                dep.issued_at = t + 13
                dep.cert_valid = True
                issued.append(dep)
            else:
                queue.append(dep)
                max_queue = max(max_queue, len(queue))
                if len(queue) >= dlq_threshold:
                    dlq_alerts += 1
                # Same drain logic
                if t > finality_resumes:
                    for q in queue:
                        q.cert_issued = True
                        q.issued_at = finality_resumes + 13
                        q.cert_valid = True
                        q.channel = "email_dlq"
                        issued.append(q)
                    queue.clear()

        elif strategy == "fallback_confirmed":
            if dep.finalized:
                dep.cert_issued = True
                dep.issued_at = t + 13
                dep.cert_valid = True
                issued.append(dep)
            elif in_stall and (t - stall_start) > 300:
                # Fallback: issue on confirmed after 5 min stall
                dep.cert_issued = True
                dep.issued_at = t + 2  # confirmed ~2s
                dep.cert_valid = False  # NOT actually final
                issued.append(dep)
            else:
                queue.append(dep)
                max_queue = max(max_queue, len(queue))

    # Final drain for remaining queue items
    for q in queue:
        q.cert_issued = True
        q.issued_at = finality_resumes + 30
        q.cert_valid = True
        issued.append(q)

    certs_valid = sum(1 for d in issued if d.cert_valid)
    certs_invalid = sum(1 for d in issued if not d.cert_valid)
    wait_times = [d.issued_at - d.arrived_at for d in issued if d.issued_at]
    avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0

    grade = "A" if certs_invalid == 0 else ("C" if certs_invalid < 3 else "F")

    return SimResult(
        strategy=strategy,
        total_deposits=n_deposits,
        certs_issued=len(issued),
        certs_valid=certs_valid,
        certs_invalid=certs_invalid,
        max_queue_depth=max_queue,
        avg_wait_secs=avg_wait,
        stall_duration_secs=stall_duration,
        dlq_alerts=dlq_alerts,
        grade=grade,
    )


def main():
    random.seed(42)

    stall_start = 1800.0   # 30 min into sim
    stall_duration = 3420.0  # 57 min (ETH May 2023)

    print("=" * 65)
    print("FINALITY STALL QUEUE SIMULATOR")
    print(f"Scenario: ETH-style stall, {stall_duration/60:.0f} min (May 2023 incident)")
    print(f"Deposits: 100 over 2 hours, stall at {stall_start/60:.0f} min")
    print("=" * 65)

    strategies = [
        ("timeout", "Timeout-and-issue (60s)"),
        ("queue_drain", "Queue-and-drain"),
        ("queue_dlq", "Queue + DLQ alerts"),
        ("fallback_confirmed", "Fallback to confirmed (5min)"),
    ]

    for strat_key, strat_name in strategies:
        r = simulate(strat_key, stall_start, stall_duration)
        print(f"\n--- {strat_name} --- Grade: {r.grade}")
        print(f"  Certs issued: {r.certs_issued}/{r.total_deposits}")
        print(f"  Valid: {r.certs_valid} | Invalid (reorg risk): {r.certs_invalid}")
        print(f"  Max queue depth: {r.max_queue_depth}")
        print(f"  Avg wait: {r.avg_wait_secs:.0f}s ({r.avg_wait_secs/60:.1f} min)")
        if r.dlq_alerts:
            print(f"  DLQ alerts fired: {r.dlq_alerts}")
        if r.certs_invalid > 0:
            print(f"  ⚠️  {r.certs_invalid} certs at double-spend risk!")

    print("\n" + "=" * 65)
    print("VERDICT")
    print("  Queue-and-drain is the only correct strategy.")
    print("  Timeout = double-spend. Fallback = double-spend.")
    print("  DLQ alerts = operational awareness without compromising safety.")
    print(f"  Max queue depth during 57-min stall is manageable.")
    print(f"  The stall is temporary. The double-spend is permanent.")
    print("=" * 65)


if __name__ == "__main__":
    main()
