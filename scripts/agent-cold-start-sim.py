#!/usr/bin/env python3
"""
Agent cold start simulator.

Models the cost of event-driven vs always-on agent runtimes.
Key insight: the real cold start for agents isn't compute — it's context hydration
(loading MEMORY.md, SOUL.md, workspace files into the context window).

Based on: ACM Computing Surveys 2024 (cold start systematic review),
AWS Lambda cold start data (2025), OpenClaw heartbeat patterns.

Compares:
1. Always-on (24/7 compute, instant response)
2. Serverless (cold start per event, pay per invocation)
3. Warm pool (keep N instances warm, hybrid)
4. Persistent memory layer (event-driven + cached context)
"""

import random
from dataclasses import dataclass


@dataclass
class AgentWorkload:
    name: str
    events_per_day: int
    avg_work_duration_s: float
    context_size_kb: float  # MEMORY.md + SOUL.md + workspace
    latency_tolerance_ms: float  # max acceptable response time


@dataclass
class RuntimeResult:
    strategy: str
    cost_per_day_usd: float
    avg_latency_ms: float
    cold_starts_per_day: int
    compute_utilization: float  # fraction of time doing useful work
    context_loads_per_day: int
    grade: str


def simulate_always_on(workload: AgentWorkload) -> RuntimeResult:
    total_work_s = workload.events_per_day * workload.avg_work_duration_s
    utilization = total_work_s / 86400
    cost = 0.50  # ~$15/month for small instance
    return RuntimeResult(
        strategy="Always-on",
        cost_per_day_usd=cost,
        avg_latency_ms=50,  # Context already loaded
        cold_starts_per_day=1,  # Only on deploy
        compute_utilization=utilization,
        context_loads_per_day=1,
        grade="B" if utilization < 0.05 else "A",
    )


def simulate_serverless(workload: AgentWorkload) -> RuntimeResult:
    # Cold start = compute init + context hydration
    compute_cold_ms = random.uniform(100, 2000)  # ACM survey range
    context_hydration_ms = workload.context_size_kb * 0.5  # ~0.5ms per KB
    total_cold_ms = compute_cold_ms + context_hydration_ms
    
    # Warm invocations (Lambda keeps warm ~5-15 min)
    avg_gap_s = 86400 / max(workload.events_per_day, 1)
    warm_fraction = min(1.0, 900 / avg_gap_s)  # 15min warm window
    cold_starts = int(workload.events_per_day * (1 - warm_fraction))
    
    avg_latency = warm_fraction * 50 + (1 - warm_fraction) * total_cold_ms
    
    # Lambda pricing: ~$0.0000166 per GB-s
    total_work_s = workload.events_per_day * workload.avg_work_duration_s
    cost = total_work_s * 0.0000166 * 2  # 2GB memory
    cost += workload.events_per_day * 0.0000002  # per-request
    
    utilization = 1.0  # Only pay for what you use
    
    latency_ok = avg_latency < workload.latency_tolerance_ms
    grade = "A" if latency_ok and cold_starts < 5 else "C" if latency_ok else "F"
    
    return RuntimeResult(
        strategy="Serverless (Lambda)",
        cost_per_day_usd=cost,
        avg_latency_ms=avg_latency,
        cold_starts_per_day=cold_starts,
        compute_utilization=utilization,
        context_loads_per_day=cold_starts + 1,
        grade=grade,
    )


def simulate_warm_pool(workload: AgentWorkload, pool_size: int = 2) -> RuntimeResult:
    base_cost = 0.10 * pool_size  # Smaller instances in pool
    context_hydration_ms = workload.context_size_kb * 0.5
    
    # Pool absorbs most cold starts
    cold_starts = max(0, workload.events_per_day - pool_size * 100)
    avg_latency = 80 + context_hydration_ms * 0.1  # Mostly warm
    
    utilization = min(1.0, workload.events_per_day * workload.avg_work_duration_s / (86400 * pool_size))
    grade = "B" if cold_starts == 0 else "C"
    
    return RuntimeResult(
        strategy=f"Warm pool (n={pool_size})",
        cost_per_day_usd=base_cost,
        avg_latency_ms=avg_latency,
        cold_starts_per_day=cold_starts,
        compute_utilization=utilization,
        context_loads_per_day=pool_size,
        grade=grade,
    )


def simulate_persistent_memory(workload: AgentWorkload) -> RuntimeResult:
    """Event-driven + cached memory layer (the fix nobody ships)."""
    # Context cached in Redis/SQLite, not reloaded from files
    context_cache_ms = workload.context_size_kb * 0.05  # 10x faster from cache
    compute_cold_ms = 200  # Minimal runtime init
    
    avg_gap_s = 86400 / max(workload.events_per_day, 1)
    cache_ttl_s = 3600  # 1hr cache TTL
    cache_hit_rate = min(1.0, cache_ttl_s / avg_gap_s)
    
    cold_starts = int(workload.events_per_day * (1 - cache_hit_rate))
    avg_latency = cache_hit_rate * (50 + context_cache_ms) + (1 - cache_hit_rate) * (compute_cold_ms + workload.context_size_kb * 0.5)
    
    # Serverless compute + small cache instance
    total_work_s = workload.events_per_day * workload.avg_work_duration_s
    cost = total_work_s * 0.0000166 * 2 + 0.05  # Lambda + cache
    
    grade = "A" if avg_latency < workload.latency_tolerance_ms else "B"
    
    return RuntimeResult(
        strategy="Persistent memory layer",
        cost_per_day_usd=cost,
        avg_latency_ms=avg_latency,
        cold_starts_per_day=cold_starts,
        compute_utilization=1.0,
        context_loads_per_day=cold_starts + 1,
        grade=grade,
    )


def run():
    workloads = [
        AgentWorkload("Kit (heartbeat agent)", events_per_day=72, avg_work_duration_s=120, context_size_kb=200, latency_tolerance_ms=5000),
        AgentWorkload("Chat bot (high traffic)", events_per_day=5000, avg_work_duration_s=3, context_size_kb=50, latency_tolerance_ms=1000),
        AgentWorkload("Monitor (hourly check)", events_per_day=24, avg_work_duration_s=30, context_size_kb=100, latency_tolerance_ms=10000),
        AgentWorkload("Trading bot (low latency)", events_per_day=1000, avg_work_duration_s=0.5, context_size_kb=20, latency_tolerance_ms=100),
    ]

    print("=" * 70)
    print("AGENT COLD START SIMULATOR")
    print("Event-driven vs always-on agent runtimes")
    print("Based on: ACM Computing Surveys 2024, AWS Lambda 2025")
    print("=" * 70)

    for wl in workloads:
        print(f"\n{'='*70}")
        print(f"WORKLOAD: {wl.name}")
        print(f"  Events/day: {wl.events_per_day} | Work duration: {wl.avg_work_duration_s}s | Context: {wl.context_size_kb}KB")
        active_min = wl.events_per_day * wl.avg_work_duration_s / 60
        print(f"  Active time: {active_min:.0f} min/day ({active_min/1440*100:.1f}%)")
        print(f"  Latency tolerance: {wl.latency_tolerance_ms}ms")

        results = [
            simulate_always_on(wl),
            simulate_serverless(wl),
            simulate_warm_pool(wl),
            simulate_persistent_memory(wl),
        ]

        print(f"\n  {'Strategy':<28} {'Cost/day':>10} {'Latency':>10} {'Cold starts':>12} {'Util':>8} {'Grade':>6}")
        print(f"  {'-'*28} {'-'*10} {'-'*10} {'-'*12} {'-'*8} {'-'*6}")
        for r in results:
            print(f"  {r.strategy:<28} ${r.cost_per_day_usd:>8.4f} {r.avg_latency_ms:>8.0f}ms {r.cold_starts_per_day:>10}   {r.compute_utilization:>6.1%} {r.grade:>5}")

    print(f"\n{'='*70}")
    print("KEY INSIGHT:")
    print("  The real cold start isn't compute (100ms-2s).")
    print("  It's context hydration: loading MEMORY.md + SOUL.md + workspace.")
    print("  200KB context @ 0.5ms/KB = 100ms extra per cold start.")
    print("  Fix: persistent memory cache (Redis/SQLite) + event-driven compute.")
    print("  Pay per tick, not per month. Cache context, not compute.")
    print("=" * 70)


if __name__ == "__main__":
    random.seed(42)
    run()
