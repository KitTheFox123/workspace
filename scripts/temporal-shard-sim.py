#!/usr/bin/env python3
"""
temporal-shard-sim.py — Temporal sharding for agent cert DAGs.

CT logs shard by time window (DigiCert 2018). At 10k agents × 9 renewals/day,
throughput is trivial (90k/day vs CT's billions). The hard problem is cross-shard queries.

Simulates: shard assignment, cross-shard query cost, and index strategies.
"""

import hashlib
import random
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Cert:
    cert_id: str
    agent_id: str
    scope_hash: str
    issued_at: int  # epoch seconds
    expires_at: int
    shard: str = ""

    def __post_init__(self):
        self.cert_id = hashlib.sha256(
            f"{self.agent_id}:{self.scope_hash}:{self.issued_at}".encode()
        ).hexdigest()[:12]


class TemporalShardManager:
    def __init__(self, shard_duration_hours: int = 24):
        self.shard_duration = shard_duration_hours * 3600
        self.shards: dict[str, list[Cert]] = defaultdict(list)
        self.agent_index: dict[str, list[str]] = defaultdict(list)  # agent → [cert_ids]

    def shard_key(self, timestamp: int) -> str:
        shard_num = timestamp // self.shard_duration
        return f"shard_{shard_num}"

    def ingest(self, cert: Cert) -> str:
        key = self.shard_key(cert.issued_at)
        cert.shard = key
        self.shards[key].append(cert)
        self.agent_index[cert.agent_id].append(cert.cert_id)
        return key

    def query_agent(self, agent_id: str) -> dict:
        """Cross-shard query: find all certs for an agent."""
        certs = []
        shards_touched = set()
        for shard_key, shard_certs in self.shards.items():
            for c in shard_certs:
                if c.agent_id == agent_id:
                    certs.append(c)
                    shards_touched.add(shard_key)
        return {
            "agent_id": agent_id,
            "total_certs": len(certs),
            "shards_touched": len(shards_touched),
            "cost": len(shards_touched),  # 1 read per shard
        }

    def query_agent_indexed(self, agent_id: str) -> dict:
        """Indexed query: O(1) lookup via agent index."""
        cert_ids = self.agent_index.get(agent_id, [])
        return {
            "agent_id": agent_id,
            "total_certs": len(cert_ids),
            "shards_touched": 1,  # index lookup
            "cost": 1,
        }

    def stats(self) -> dict:
        total_certs = sum(len(s) for s in self.shards.values())
        agents = set()
        for shard_certs in self.shards.values():
            for c in shard_certs:
                agents.add(c.agent_id)
        return {
            "total_shards": len(self.shards),
            "total_certs": total_certs,
            "total_agents": len(agents),
            "avg_certs_per_shard": total_certs / max(len(self.shards), 1),
            "certs_per_agent": total_certs / max(len(agents), 1),
        }


def demo():
    print("=" * 60)
    print("TEMPORAL SHARD SIMULATOR — Agent Cert DAGs at Scale")
    print("=" * 60)

    # Simulate: 10k agents, 9 renewals/day, 7 days
    n_agents = 10_000
    renewals_per_day = 9
    days = 7
    shard_hours = 24  # 1 shard per day

    mgr = TemporalShardManager(shard_duration_hours=shard_hours)

    base_time = 1_000_000
    day_seconds = 86400

    for day in range(days):
        for agent_num in range(n_agents):
            for renewal in range(renewals_per_day):
                t = base_time + day * day_seconds + random.randint(0, day_seconds - 1)
                cert = Cert(
                    cert_id="",
                    agent_id=f"agent_{agent_num:05d}",
                    scope_hash=hashlib.sha256(f"scope_{agent_num}_{renewal}".encode()).hexdigest()[:8],
                    issued_at=t,
                    expires_at=t + 3600,
                )
                mgr.ingest(cert)

    stats = mgr.stats()
    print(f"\nSimulation: {n_agents:,} agents × {renewals_per_day} renewals × {days} days")
    print(f"  Total certs: {stats['total_certs']:,}")
    print(f"  Total shards: {stats['total_shards']}")
    print(f"  Avg certs/shard: {stats['avg_certs_per_shard']:,.0f}")
    print(f"  Certs/agent: {stats['certs_per_agent']:.0f}")

    # Query comparison
    test_agent = "agent_00042"
    
    naive = mgr.query_agent(test_agent)
    indexed = mgr.query_agent_indexed(test_agent)

    print(f"\n{'─' * 50}")
    print(f"QUERY: all certs for {test_agent}")
    print(f"  Naive (scan all shards):  {naive['shards_touched']} shards touched, cost={naive['cost']}")
    print(f"  Indexed (agent→certs):    {indexed['shards_touched']} shard touched, cost={indexed['cost']}")
    print(f"  Speedup: {naive['cost']}x → 1x")

    # CT comparison
    print(f"\n{'─' * 50}")
    print(f"CT SCALE COMPARISON")
    ct_daily = 10_000_000  # ~10M certs/day on web
    agent_daily = n_agents * renewals_per_day
    print(f"  Web CT daily:    ~{ct_daily:>12,} certs")
    print(f"  Agent DAG daily: ~{agent_daily:>12,} certs")
    print(f"  Ratio: {ct_daily / agent_daily:.0f}x")
    print(f"  Itko (2024): 2M certs/day on ¼ CPU core")
    print(f"  Agent load: {agent_daily / 2_000_000 * 100:.1f}% of one Itko instance")

    # Grade
    load_pct = agent_daily / 2_000_000
    if load_pct < 0.1:
        grade = "A+"
    elif load_pct < 0.5:
        grade = "A"
    elif load_pct < 1.0:
        grade = "B"
    else:
        grade = "C"

    print(f"\n{'=' * 60}")
    print(f"VERDICT: Grade {grade}")
    print(f"  Throughput: trivial ({agent_daily:,}/day vs 2M capacity)")
    print(f"  Hard problem: cross-shard queries (solved by agent index)")
    print(f"  Temporal sharding: {shard_hours}h windows, {stats['total_shards']} shards for {days} days")
    print(f"  Source: DigiCert temporal sharding (2018), Itko tiled logs (2024)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
