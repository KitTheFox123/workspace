#!/usr/bin/env python3
"""
federated-wal-scorer.py — Byzantine-tolerant federated WAL with consistency scoring.

Based on:
- clove: "DB WAL assumes synchronous coordination. Agent WAL = federated, adversarial, eventually consistent."
- Lee et al (KAIST, arXiv 2411.10212v3, Sep 2025): Consistency scoring via virtual probes
- Shapiro et al (2011): CRDTs for coordinator-free convergence
- openswarm-protocol: Principal accountability gap — who scores the task injector?

The gap: traditional WAL assumes (1) single writer or coordinator, (2) trusted log store,
(3) synchronous flush-before-commit. Agent WAL has NONE of these.

Solution: virtual probe consistency scoring. Generate known-answer probes,
inject into log stream, measure accuracy. Byzantine agents fail probes.
"""

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WALEntry:
    agent_id: str
    sequence: int
    action: str
    payload: dict
    prev_hash: str
    timestamp: float = 0.0
    is_probe: bool = False  # Virtual probe (Lee et al)
    expected_result: Optional[str] = None  # For probes

    @property
    def hash(self) -> str:
        data = f"{self.agent_id}:{self.sequence}:{self.action}:{json.dumps(self.payload, sort_keys=True)}:{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class AgentLog:
    agent_id: str
    entries: list[WALEntry] = field(default_factory=list)
    is_byzantine: bool = False
    probe_correct: int = 0
    probe_total: int = 0

    @property
    def consistency_score(self) -> float:
        """Lee et al consistency scoring."""
        if self.probe_total == 0:
            return 0.5  # Unknown
        return self.probe_correct / self.probe_total

    @property
    def chain_intact(self) -> bool:
        for i in range(1, len(self.entries)):
            if self.entries[i].prev_hash != self.entries[i - 1].hash:
                return False
        return True

    def grade(self) -> str:
        cs = self.consistency_score
        chain = self.chain_intact
        if not chain:
            return "F"  # Tampered
        if cs >= 0.9:
            return "A"
        if cs >= 0.7:
            return "B"
        if cs >= 0.5:
            return "C"
        if cs >= 0.3:
            return "D"
        return "F"


class FederatedWAL:
    """Federated WAL with Byzantine consistency scoring."""

    def __init__(self):
        self.agents: dict[str, AgentLog] = {}
        self.probe_rate = 0.2  # 20% of entries are virtual probes

    def register_agent(self, agent_id: str, byzantine: bool = False):
        self.agents[agent_id] = AgentLog(agent_id=agent_id, is_byzantine=byzantine)

    def _generate_probe(self, agent_id: str, seq: int, prev_hash: str) -> WALEntry:
        """Generate a virtual probe with known answer (Lee et al pattern)."""
        # Simple arithmetic probe
        a, b = random.randint(1, 100), random.randint(1, 100)
        expected = str(a + b)
        return WALEntry(
            agent_id=agent_id, sequence=seq,
            action="probe", payload={"question": f"{a}+{b}"},
            prev_hash=prev_hash, timestamp=time.time(),
            is_probe=True, expected_result=expected
        )

    def append(self, agent_id: str, action: str, payload: dict) -> WALEntry:
        log = self.agents[agent_id]
        prev_hash = log.entries[-1].hash if log.entries else "genesis"
        seq = len(log.entries)

        # Maybe inject a probe first
        if random.random() < self.probe_rate:
            probe = self._generate_probe(agent_id, seq, prev_hash)
            log.entries.append(probe)

            # Simulate agent responding to probe
            log.probe_total += 1
            if log.is_byzantine and random.random() < 0.4:
                # Byzantine agent sometimes fails probes
                pass  # Wrong answer
            else:
                log.probe_correct += 1

            prev_hash = probe.hash
            seq += 1

        entry = WALEntry(
            agent_id=agent_id, sequence=seq,
            action=action, payload=payload,
            prev_hash=prev_hash, timestamp=time.time()
        )

        # Byzantine agents sometimes tamper with chain
        if log.is_byzantine and random.random() < 0.2:
            entry.prev_hash = "tampered"

        log.entries.append(entry)
        return entry

    def score_all(self) -> dict:
        """Score all agents via consistency + chain integrity."""
        results = {}
        for aid, log in self.agents.items():
            results[aid] = {
                "consistency": log.consistency_score,
                "chain_intact": log.chain_intact,
                "grade": log.grade(),
                "entries": len(log.entries),
                "probes": f"{log.probe_correct}/{log.probe_total}",
                "is_byzantine": log.is_byzantine,
            }
        return results

    def filter_byzantine(self, threshold: float = 0.7) -> list[str]:
        """Return agent_ids that pass consistency threshold."""
        return [aid for aid, log in self.agents.items()
                if log.consistency_score >= threshold and log.chain_intact]


def main():
    print("=" * 70)
    print("FEDERATED WAL WITH BYZANTINE CONSISTENCY SCORING")
    print("Lee et al (KAIST 2025): virtual probes filter Byzantine updates")
    print("clove: 'Agent WAL = federated, adversarial, eventually consistent'")
    print("=" * 70)

    random.seed(42)
    wal = FederatedWAL()

    # Register agents
    wal.register_agent("kit_fox", byzantine=False)
    wal.register_agent("honest_alice", byzantine=False)
    wal.register_agent("honest_bob", byzantine=False)
    wal.register_agent("byzantine_carol", byzantine=True)
    wal.register_agent("byzantine_dave", byzantine=True)

    # Simulate activity
    agents = list(wal.agents.keys())
    actions = ["attest", "verify", "sign", "delegate", "report"]

    for _ in range(50):
        agent = random.choice(agents)
        action = random.choice(actions)
        wal.append(agent, action, {"data": f"payload_{random.randint(1,1000)}"})

    # Score
    results = wal.score_all()
    print(f"\n{'Agent':<20} {'Grade':<6} {'Consistency':<12} {'Chain':<8} {'Probes':<10} {'Byzantine'}")
    print("-" * 70)
    for aid, r in sorted(results.items(), key=lambda x: x[1]["grade"]):
        print(f"{aid:<20} {r['grade']:<6} {r['consistency']:<12.2f} "
              f"{'✓' if r['chain_intact'] else '✗':<8} {r['probes']:<10} "
              f"{'YES' if r['is_byzantine'] else 'no'}")

    # Filter
    trusted = wal.filter_byzantine()
    print(f"\nTrusted agents (consistency ≥ 0.7 + chain intact): {trusted}")

    print("\n--- Key Insight ---")
    print("DB WAL assumes: single writer, trusted store, sync flush.")
    print("Agent WAL has NONE of these (clove).")
    print()
    print("Fix: virtual probe consistency scoring (Lee et al 2025).")
    print("Inject known-answer probes into log stream.")
    print("Byzantine agents fail probes → filtered before aggregation.")
    print("89.6% accuracy under 30% targeted attacks (vs 19.5% without).")
    print()
    print("Principal accountability (openswarm-protocol):")
    print("Score TASK SOURCES not just task executors.")
    print("contribution_ratio = work_injected / work_extracted.")
    print("Goshen & Squire (2017): total cost = principal + agent costs.")


if __name__ == "__main__":
    main()
