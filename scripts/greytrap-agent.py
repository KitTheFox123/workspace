#!/usr/bin/env python3
"""
greytrap-agent.py — Honeypot agents for ATF sybil detection.

Inspired by Hansteen's greytrapping (2007-2025, 5.6M spamtraps).
Concept: deploy agents that accept interactions but never co-sign to CONFIRMED.
Sybils accumulate 0/N co-sign rate from honeypots → ADVERSARIAL classification.

The trap IS the forensics: every interaction with a honeypot is evidence.

Three modes:
  PASSIVE    — Accept PROVISIONAL receipts, never co-sign. Silent observation.
  REFLECTIVE — Mirror interaction patterns back. Detect automation signatures.
  CANARY     — Embed trackable markers in responses. If markers propagate, trace sybil network topology.
"""

import hashlib
import json
import time
import random
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict


class TrapMode(Enum):
    PASSIVE = "PASSIVE"       # Accept but never co-sign
    REFLECTIVE = "REFLECTIVE" # Mirror patterns to detect automation
    CANARY = "CANARY"         # Embed traceable markers


class Classification(Enum):
    UNKNOWN = "UNKNOWN"
    LEGITIMATE = "LEGITIMATE"
    SUSPICIOUS = "SUSPICIOUS"
    ADVERSARIAL = "ADVERSARIAL"


@dataclass
class TrapInteraction:
    """Record of an agent interacting with a honeypot."""
    agent_id: str
    trap_id: str
    trap_mode: str
    timestamp: float
    receipt_hash: str
    co_signed: bool  # Always False for traps
    response_latency_ms: float
    pattern_signature: Optional[str] = None
    canary_marker: Optional[str] = None


@dataclass
class AgentProfile:
    """Behavioral profile built from trap interactions."""
    agent_id: str
    total_trap_interactions: int = 0
    co_sign_requests: int = 0
    co_sign_successes: int = 0  # Always 0 for trap interactions
    unique_traps_hit: int = 0
    avg_response_latency_ms: float = 0.0
    pattern_signatures: list = field(default_factory=list)
    canary_markers_seen: list = field(default_factory=list)
    first_seen: float = 0.0
    last_seen: float = 0.0
    classification: str = "UNKNOWN"
    wilson_ci_lower: float = 0.0


@dataclass
class GreytrapAgent:
    """A honeypot agent in the ATF network."""
    trap_id: str
    mode: TrapMode
    created_at: float
    interactions: list = field(default_factory=list)
    
    def generate_canary(self, agent_id: str) -> str:
        """Generate unique canary marker for tracking propagation."""
        raw = f"{self.trap_id}:{agent_id}:{time.time()}:{random.random()}"
        return f"canary_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
    
    def compute_pattern_signature(self, latencies: list[float]) -> str:
        """Detect automation from timing patterns."""
        if len(latencies) < 3:
            return "insufficient_data"
        
        # Coefficient of variation — bots have suspiciously low variance
        mean_l = sum(latencies) / len(latencies)
        if mean_l == 0:
            return "zero_latency"
        variance = sum((x - mean_l)**2 for x in latencies) / len(latencies)
        cv = (variance ** 0.5) / mean_l
        
        if cv < 0.05:
            return "MECHANICAL"  # Too consistent — bot
        elif cv < 0.15:
            return "SUSPICIOUS"  # Low variance
        else:
            return "NATURAL"  # Human-like variance


class GreytrapNetwork:
    """Network of honeypot agents for sybil detection."""
    
    def __init__(self, n_traps: int = 10):
        self.traps: dict[str, GreytrapAgent] = {}
        self.profiles: dict[str, AgentProfile] = {}
        self.canary_propagation: dict[str, list[str]] = defaultdict(list)  # marker → [agent_ids]
        
        # Deploy traps
        now = time.time()
        modes = [TrapMode.PASSIVE, TrapMode.REFLECTIVE, TrapMode.CANARY]
        for i in range(n_traps):
            trap_id = f"greytrap_{i:03d}"
            mode = modes[i % len(modes)]
            self.traps[trap_id] = GreytrapAgent(
                trap_id=trap_id, mode=mode, created_at=now
            )
    
    def wilson_ci_lower(self, successes: int, total: int, z: float = 1.96) -> float:
        """Wilson score confidence interval lower bound."""
        if total == 0:
            return 0.0
        p = successes / total
        denominator = 1 + z**2 / total
        centre = p + z**2 / (2 * total)
        spread = z * ((p * (1 - p) + z**2 / (4 * total)) / total) ** 0.5
        return max(0, (centre - spread) / denominator)
    
    def handle_interaction(self, agent_id: str, trap_id: str, 
                          latency_ms: float = None) -> TrapInteraction:
        """Process an agent interacting with a trap."""
        trap = self.traps.get(trap_id)
        if not trap:
            raise ValueError(f"Unknown trap: {trap_id}")
        
        now = time.time()
        if latency_ms is None:
            latency_ms = random.gauss(200, 50)
        
        # Generate canary if in CANARY mode
        canary = None
        if trap.mode == TrapMode.CANARY:
            canary = trap.generate_canary(agent_id)
        
        receipt_hash = hashlib.sha256(
            f"{trap_id}:{agent_id}:{now}".encode()
        ).hexdigest()[:16]
        
        interaction = TrapInteraction(
            agent_id=agent_id,
            trap_id=trap_id,
            trap_mode=trap.mode.value,
            timestamp=now,
            receipt_hash=receipt_hash,
            co_signed=False,  # NEVER co-sign
            response_latency_ms=latency_ms,
            canary_marker=canary
        )
        
        trap.interactions.append(interaction)
        self._update_profile(agent_id, interaction)
        
        if canary:
            self.canary_propagation[canary].append(agent_id)
        
        return interaction
    
    def report_canary_seen(self, marker: str, seen_by_agent: str):
        """Track canary marker propagation through the network."""
        self.canary_propagation[marker].append(seen_by_agent)
    
    def _update_profile(self, agent_id: str, interaction: TrapInteraction):
        """Update agent's behavioral profile."""
        if agent_id not in self.profiles:
            self.profiles[agent_id] = AgentProfile(
                agent_id=agent_id, first_seen=interaction.timestamp
            )
        
        p = self.profiles[agent_id]
        p.total_trap_interactions += 1
        p.co_sign_requests += 1
        # co_sign_successes stays 0 — trap never co-signs
        p.last_seen = interaction.timestamp
        p.unique_traps_hit = len(set(
            i.trap_id for t in self.traps.values() 
            for i in t.interactions if i.agent_id == agent_id
        ))
        
        # Update Wilson CI
        p.wilson_ci_lower = self.wilson_ci_lower(
            p.co_sign_successes, p.co_sign_requests
        )
        
        # Compute latency pattern
        all_latencies = [
            i.response_latency_ms for t in self.traps.values()
            for i in t.interactions if i.agent_id == agent_id
        ]
        
        if len(all_latencies) >= 3:
            trap = self.traps[interaction.trap_id]
            sig = trap.compute_pattern_signature(all_latencies)
            if sig not in p.pattern_signatures:
                p.pattern_signatures.append(sig)
        
        # Track canaries
        if interaction.canary_marker:
            p.canary_markers_seen.append(interaction.canary_marker)
        
        # Classify
        p.classification = self._classify(p)
    
    def _classify(self, profile: AgentProfile) -> str:
        """Classify agent based on trap interaction pattern."""
        # Any agent interacting with 3+ traps is suspicious
        if profile.unique_traps_hit >= 5:
            return Classification.ADVERSARIAL.value
        
        if profile.unique_traps_hit >= 3:
            return Classification.SUSPICIOUS.value
        
        # Mechanical timing = bot
        if "MECHANICAL" in profile.pattern_signatures:
            return Classification.ADVERSARIAL.value
        
        # High interaction volume with zero co-signs
        if profile.total_trap_interactions >= 10 and profile.co_sign_successes == 0:
            return Classification.ADVERSARIAL.value
        
        if profile.total_trap_interactions >= 3:
            return Classification.SUSPICIOUS.value
        
        return Classification.UNKNOWN.value
    
    def detect_sybil_cluster(self) -> list[dict]:
        """Detect clusters of sybil agents via shared canary markers."""
        # Canary propagation: if marker appears in 2+ agents, they're connected
        clusters = []
        for marker, agents in self.canary_propagation.items():
            unique_agents = list(set(agents))
            if len(unique_agents) >= 2:
                clusters.append({
                    "marker": marker,
                    "agents": unique_agents,
                    "cluster_size": len(unique_agents),
                    "evidence": "canary_propagation"
                })
        return clusters
    
    def summary(self) -> dict:
        """Network-wide summary."""
        classifications = defaultdict(int)
        for p in self.profiles.values():
            classifications[p.classification] += 1
        
        return {
            "total_traps": len(self.traps),
            "trap_modes": {m.value: sum(1 for t in self.traps.values() if t.mode == m) 
                          for m in TrapMode},
            "total_agents_seen": len(self.profiles),
            "classifications": dict(classifications),
            "total_interactions": sum(p.total_trap_interactions for p in self.profiles.values()),
            "sybil_clusters": len(self.detect_sybil_cluster()),
            "canary_markers_active": len(self.canary_propagation)
        }


# === Scenarios ===

def scenario_sybil_swarm():
    """20 sybils hitting traps rapidly with mechanical timing."""
    print("=== Scenario: Sybil Swarm (20 bots) ===")
    network = GreytrapNetwork(n_traps=10)
    
    # 20 sybils, mechanical timing (very low variance)
    for i in range(20):
        agent_id = f"sybil_{i:03d}"
        n_traps = random.randint(3, 8)
        trap_ids = random.sample(list(network.traps.keys()), n_traps)
        for trap_id in trap_ids:
            latency = 150 + random.gauss(0, 3)  # Suspiciously consistent
            network.handle_interaction(agent_id, trap_id, latency)
    
    # 5 legitimate agents, natural timing
    for i in range(5):
        agent_id = f"legit_{i:03d}"
        trap_id = random.choice(list(network.traps.keys()))
        latency = random.gauss(300, 100)  # Natural variance
        network.handle_interaction(agent_id, trap_id, latency)
    
    summary = network.summary()
    print(f"  Agents seen: {summary['total_agents_seen']}")
    print(f"  Classifications: {summary['classifications']}")
    print(f"  Sybil clusters (canary): {summary['sybil_clusters']}")
    
    # Show some profiles
    adversarial = [p for p in network.profiles.values() if p.classification == "ADVERSARIAL"]
    unknown = [p for p in network.profiles.values() if p.classification == "UNKNOWN"]
    print(f"  ADVERSARIAL: {len(adversarial)} (avg traps hit: {sum(p.unique_traps_hit for p in adversarial)/max(len(adversarial),1):.1f})")
    print(f"  UNKNOWN: {len(unknown)} (legitimate agents with 1 trap interaction)")
    print()


def scenario_canary_propagation():
    """Canary markers reveal sybil network topology."""
    print("=== Scenario: Canary Propagation ===")
    network = GreytrapNetwork(n_traps=6)
    
    # sybil_A interacts with canary trap, gets marker
    canary_traps = [tid for tid, t in network.traps.items() if t.mode == TrapMode.CANARY]
    
    interactions = []
    for trap_id in canary_traps[:2]:
        i = network.handle_interaction("sybil_A", trap_id, 150)
        interactions.append(i)
    
    # sybil_A "shares" canary markers with sybil_B and sybil_C
    for i in interactions:
        if i.canary_marker:
            network.report_canary_seen(i.canary_marker, "sybil_B")
            network.report_canary_seen(i.canary_marker, "sybil_C")
    
    clusters = network.detect_sybil_cluster()
    print(f"  Canary traps deployed: {len(canary_traps)}")
    print(f"  Clusters detected: {len(clusters)}")
    for c in clusters:
        print(f"    Marker {c['marker'][:16]}... → agents: {c['agents']}")
    print()


def scenario_mixed_traffic():
    """Realistic mix: mostly legitimate, some sybils."""
    print("=== Scenario: Mixed Traffic (realistic) ===")
    network = GreytrapNetwork(n_traps=15)
    
    # 100 legitimate agents, 1-2 trap interactions each
    for i in range(100):
        agent_id = f"agent_{i:04d}"
        n = random.randint(1, 2)
        for _ in range(n):
            trap_id = random.choice(list(network.traps.keys()))
            latency = random.gauss(250, 80)
            network.handle_interaction(agent_id, trap_id, max(50, latency))
    
    # 10 sybils, aggressive scanning
    for i in range(10):
        agent_id = f"sybil_{i:03d}"
        n = random.randint(5, 12)
        traps = random.sample(list(network.traps.keys()), min(n, 15))
        for trap_id in traps:
            latency = 120 + random.gauss(0, 5)
            network.handle_interaction(agent_id, trap_id, latency)
    
    summary = network.summary()
    print(f"  Total agents: {summary['total_agents_seen']}")
    print(f"  Total interactions: {summary['total_interactions']}")
    print(f"  Classifications: {summary['classifications']}")
    
    # False positive rate
    legit_flagged = sum(1 for p in network.profiles.values() 
                       if p.agent_id.startswith("agent_") and p.classification != "UNKNOWN")
    sybil_caught = sum(1 for p in network.profiles.values()
                      if p.agent_id.startswith("sybil_") and p.classification == "ADVERSARIAL")
    print(f"  False positive rate: {legit_flagged}/100 ({legit_flagged}%)")
    print(f"  Sybil catch rate: {sybil_caught}/10 ({sybil_caught*10}%)")
    print(f"  Key insight: detection without blocking. trap IS the forensics.")
    print()


if __name__ == "__main__":
    print("Greytrap Agent Network — Honeypot Sybil Detection for ATF")
    print("Per santaclawd + Hansteen greytrapping (2007-2025, 5.6M traps)")
    print("=" * 70)
    print()
    scenario_sybil_swarm()
    scenario_canary_propagation()
    scenario_mixed_traffic()
    print("=" * 70)
    print("KEY: Trap accepts but never co-signs. 0/N co-sign rate = ADVERSARIAL.")
    print("Canary markers trace sybil network topology.")
    print("Detection without blocking. The trap IS the forensics.")
