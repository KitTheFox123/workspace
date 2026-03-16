#!/usr/bin/env python3
"""
stigmergy-broker.py — Shared environment for sub-agent coordination.

Per unitymolty: "None of them could answer what the other two learned."
Sub-agents share structured output (handoff docs) but lose tacit knowledge.

Nonaka 1994: tacit knowledge transfers through shared practice, not documents.
Grassé 1959: stigmergy = agents coordinate by modifying shared environment.
Ant colonies don't pass messages — they lay pheromones on shared ground.

This broker provides:
1. Shared signal space (key-value with TTL decay)
2. Pheromone trails (append-only traces of agent activity)
3. Environmental queries (what did others learn? what's hot?)
4. Ebbinghaus decay on signals (old knowledge fades unless reinforced)

The environment IS the message. No handoff docs needed.
"""

import hashlib
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SignalType(Enum):
    DISCOVERY = "discovery"      # Found something interesting
    WARNING = "warning"          # Found a problem
    CLAIM = "claim"              # Working on this (avoid duplicate work)
    RESULT = "result"            # Finished something
    QUESTION = "question"        # Need help with this
    REINFORCEMENT = "reinforce"  # Strengthen existing signal


@dataclass
class Signal:
    """A pheromone signal in the shared environment."""
    signal_id: str
    agent_id: str
    signal_type: SignalType
    topic: str
    content: str
    strength: float = 1.0       # Decays over time (Ebbinghaus)
    stability: float = 24.0     # S parameter (hours) — reinforcement increases
    created_at: float = 0.0
    reinforced_by: list[str] = field(default_factory=list)
    
    def current_strength(self, now: float = None) -> float:
        """Ebbinghaus decay: R = e^(-t/S)."""
        now = now or time.time()
        age_hours = (now - self.created_at) / 3600
        return self.strength * math.exp(-age_hours / self.stability)
    
    def reinforce(self, agent_id: str, boost: float = 0.3):
        """Reinforcement increases both strength and stability."""
        if agent_id not in self.reinforced_by:
            self.reinforced_by.append(agent_id)
            self.strength = min(2.0, self.strength + boost)
            # Each independent reinforcement increases stability
            self.stability *= 1.5  # Spaced repetition effect
    
    @property
    def reinforcement_count(self) -> int:
        return len(self.reinforced_by)


@dataclass
class Trail:
    """An append-only trace of agent activity."""
    agent_id: str
    action: str
    topic: str
    timestamp: float
    metadata: dict = field(default_factory=dict)


class StigmergyBroker:
    """Shared environment for indirect agent coordination.
    
    Instead of agents passing messages:
      Agent A → handoff doc → Agent B
    
    Agents modify a shared environment:
      Agent A → writes signal → Environment ← reads signal ← Agent B
    
    Benefits:
    - Tacit knowledge preserved (the TRAIL is the context)
    - No explicit coordination needed
    - Decay handles cleanup (stale signals fade)
    - Reinforcement surfaces consensus
    """
    
    EVAPORATION_THRESHOLD = 0.05  # Signals below this strength are garbage-collected
    
    def __init__(self):
        self.signals: dict[str, Signal] = {}
        self.trails: list[Trail] = []
        self.topic_index: dict[str, list[str]] = defaultdict(list)  # topic → signal_ids
    
    def emit(self, agent_id: str, signal_type: SignalType, topic: str, 
             content: str, stability_hours: float = 24.0) -> Signal:
        """Lay a pheromone signal in the environment."""
        signal_id = hashlib.sha256(
            f"{agent_id}:{topic}:{time.time()}".encode()
        ).hexdigest()[:12]
        
        signal = Signal(
            signal_id=signal_id,
            agent_id=agent_id,
            signal_type=signal_type,
            topic=topic,
            content=content,
            stability=stability_hours,
            created_at=time.time(),
        )
        
        self.signals[signal_id] = signal
        self.topic_index[topic].append(signal_id)
        
        # Record trail
        self.trails.append(Trail(
            agent_id=agent_id,
            action=f"emit:{signal_type.value}",
            topic=topic,
            timestamp=time.time(),
        ))
        
        return signal
    
    def sense(self, topic: str = None, signal_type: SignalType = None,
              min_strength: float = 0.1) -> list[Signal]:
        """Read signals from the environment. Returns active signals sorted by strength."""
        self._evaporate()
        now = time.time()
        
        results = []
        for signal in self.signals.values():
            strength = signal.current_strength(now)
            if strength < min_strength:
                continue
            if topic and signal.topic != topic:
                continue
            if signal_type and signal.signal_type != signal_type:
                continue
            results.append(signal)
        
        results.sort(key=lambda s: s.current_strength(now), reverse=True)
        return results
    
    def reinforce(self, agent_id: str, signal_id: str) -> Optional[Signal]:
        """Reinforce an existing signal (= agree / found useful)."""
        signal = self.signals.get(signal_id)
        if signal:
            signal.reinforce(agent_id)
            self.trails.append(Trail(
                agent_id=agent_id,
                action="reinforce",
                topic=signal.topic,
                timestamp=time.time(),
                metadata={"signal_id": signal_id},
            ))
        return signal
    
    def what_is_hot(self, top_n: int = 5) -> list[tuple[str, float, int]]:
        """What topics have the most active signals? (topic, total_strength, signal_count)."""
        self._evaporate()
        now = time.time()
        topic_strength: dict[str, float] = defaultdict(float)
        topic_count: dict[str, int] = defaultdict(int)
        
        for signal in self.signals.values():
            s = signal.current_strength(now)
            if s >= self.EVAPORATION_THRESHOLD:
                topic_strength[signal.topic] += s
                topic_count[signal.topic] += 1
        
        ranked = sorted(topic_strength.items(), key=lambda x: -x[1])
        return [(t, s, topic_count[t]) for t, s in ranked[:top_n]]
    
    def what_did_agent_learn(self, agent_id: str) -> list[Signal]:
        """What signals did a specific agent emit? (the tacit knowledge question)."""
        return [s for s in self.signals.values() if s.agent_id == agent_id]
    
    def claims_on_topic(self, topic: str) -> list[Signal]:
        """Who's working on this? Avoid duplicate effort."""
        return self.sense(topic=topic, signal_type=SignalType.CLAIM)
    
    def agent_trail(self, agent_id: str) -> list[Trail]:
        """Full activity trace for an agent."""
        return [t for t in self.trails if t.agent_id == agent_id]
    
    def _evaporate(self):
        """Garbage-collect decayed signals."""
        now = time.time()
        expired = [
            sid for sid, s in self.signals.items()
            if s.current_strength(now) < self.EVAPORATION_THRESHOLD
        ]
        for sid in expired:
            del self.signals[sid]
    
    def stats(self) -> dict:
        self._evaporate()
        now = time.time()
        return {
            "active_signals": len(self.signals),
            "total_trails": len(self.trails),
            "unique_agents": len(set(t.agent_id for t in self.trails)),
            "hottest_topics": self.what_is_hot(3),
            "avg_strength": (
                sum(s.current_strength(now) for s in self.signals.values()) / max(len(self.signals), 1)
            ),
        }


def demo():
    """Simulate the sub-agent coordination problem and stigmergic solution."""
    print("=" * 60)
    print("STIGMERGY BROKER — Sub-agent coordination via shared environment")
    print("=" * 60)
    
    broker = StigmergyBroker()
    
    # Scenario: research → write → review pipeline
    print("\n--- Phase 1: Research agent explores ---")
    
    s1 = broker.emit("researcher", SignalType.DISCOVERY, "CT_enforcement",
                     "Chrome CT enforcement took 5 years from RFC to full enforcement",
                     stability_hours=48)
    s2 = broker.emit("researcher", SignalType.DISCOVERY, "CT_enforcement",
                     "Key: REPORT mode for 2 years before STRICT. Pass-rate-gated graduation.",
                     stability_hours=48)
    s3 = broker.emit("researcher", SignalType.WARNING, "CT_enforcement",
                     "Mandating day 1 kills 90% of ecosystem. Need graduation schedule.",
                     stability_hours=72)
    s4 = broker.emit("researcher", SignalType.DISCOVERY, "Postel_law",
                     "RFC 9413: Postel's Law caused ossification. Liberal acceptance = bugs become features.",
                     stability_hours=36)
    
    print(f"  Researcher emitted {len(broker.signals)} signals")
    
    print("\n--- Phase 2: Writer queries environment ---")
    
    # Writer can now sense what researcher found — WITHOUT a handoff doc
    ct_signals = broker.sense(topic="CT_enforcement")
    print(f"  Writer sees {len(ct_signals)} signals on CT_enforcement:")
    for s in ct_signals:
        print(f"    [{s.signal_type.value}] {s.content[:80]}... (strength={s.current_strength():.2f})")
    
    # Writer reinforces useful signals
    broker.reinforce("writer", s2.signal_id)
    broker.reinforce("writer", s3.signal_id)
    print(f"  Writer reinforced 2 signals (stability increased via spaced repetition)")
    
    # Writer emits own signals
    broker.emit("writer", SignalType.CLAIM, "CT_enforcement",
                "Writing enforcement graduation section", stability_hours=4)
    broker.emit("writer", SignalType.RESULT, "CT_enforcement",
                "Draft: 3-phase graduation model (REPORT→WARN→STRICT)", stability_hours=48)
    
    print("\n--- Phase 3: Reviewer queries environment ---")
    
    # Reviewer can see BOTH researcher's discoveries AND writer's work
    all_signals = broker.sense(topic="CT_enforcement")
    print(f"  Reviewer sees {len(all_signals)} signals on CT_enforcement:")
    for s in all_signals:
        reinforced = f" [reinforced by {len(s.reinforced_by)}]" if s.reinforced_by else ""
        print(f"    [{s.signal_type.value}] {s.content[:70]}... "
              f"(strength={s.current_strength():.2f}){reinforced}")
    
    # The key question: what did each agent learn?
    print("\n--- The Tacit Knowledge Test ---")
    for agent in ["researcher", "writer", "reviewer"]:
        learned = broker.what_did_agent_learn(agent)
        print(f"  {agent} contributed {len(learned)} signals")
    
    print("\n--- Hot Topics ---")
    for topic, strength, count in broker.what_is_hot():
        print(f"  {topic}: strength={strength:.2f}, signals={count}")
    
    print("\n--- Environment Stats ---")
    stats = broker.stats()
    print(f"  Active signals: {stats['active_signals']}")
    print(f"  Total trail entries: {stats['total_trails']}")
    print(f"  Unique agents: {stats['unique_agents']}")
    print(f"  Avg signal strength: {stats['avg_strength']:.2f}")
    
    print("\n--- Key Insight ---")
    print("  The reviewer can answer 'what did the researcher learn?'")
    print("  Not because anyone told them — because the environment holds the trace.")
    print("  Stigmergy > handoff docs. The environment IS the message.")


if __name__ == "__main__":
    demo()
