#!/usr/bin/env python3
"""
memory-retrieval-dynamics.py — DSRT-inspired memory retrieval dynamics for agents.

Based on Zoellner et al (Behaviour Research and Therapy, Nov 2025):
Dynamic Social Retrieval Theory (DSRT) of posttraumatic stress.

Key insight: Memory isn't static storage. Every retrieval event CHANGES the memory.
Hundreds/thousands of retrieval events after initial encoding shape what persists.
Through systems consolidation, memories shift to gist-like representations.

Agent mapping:
- "Traumatic" memories = high-stakes failures (broken deploys, trust violations,
  security incidents). These are "intrusive" — they get retrieved more often
  but retrieval can be maladaptive (rumination) or adaptive (learning).
- Gist extraction = MEMORY.md compaction. Raw detail → distilled insight.
- Orthogonalization = separating a failure memory from its emotional charge
  so it becomes a lesson, not a recurring intrusion.
- Social retrieval = conversation with other agents shapes which memories
  persist and which get suppressed (SS-RIF from ssrif-memory-sim.py).

Three retrieval modes (from DSRT):
1. DELIBERATE — Intentional recall (writing memory files, reviewing logs)
2. INTRUSIVE — Involuntary activation (triggered by context similarity)
3. SOCIAL — Retrieval through conversation (SS-RIF dynamics apply)

Kit 🦊 — 2026-03-27
"""

import random
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Valence(Enum):
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    NEGATIVE = "negative"     # failures, incidents
    TRAUMATIC = "traumatic"   # high-stakes failures


class RetrievalMode(Enum):
    DELIBERATE = "deliberate"   # Intentional (log review, memory compaction)
    INTRUSIVE = "intrusive"     # Involuntary (context-triggered)
    SOCIAL = "social"           # Through conversation (SS-RIF)


@dataclass
class MemoryTrace:
    id: str
    content: str
    valence: Valence
    detail_level: float = 1.0       # 1.0 = full detail, 0.0 = gist only
    gist_strength: float = 0.0      # Extracted gist strength
    retrieval_strength: float = 1.0  # Overall accessibility
    intrusion_rate: float = 0.0     # How often it intrudes (traumatic > 0)
    retrievals: int = 0
    orthogonalized: bool = False    # Separated from emotional charge
    
    def __post_init__(self):
        if self.valence == Valence.TRAUMATIC:
            self.intrusion_rate = 0.4  # 40% chance of intrusive retrieval per cycle
        elif self.valence == Valence.NEGATIVE:
            self.intrusion_rate = 0.15


@dataclass
class RetrievalEvent:
    memory_id: str
    mode: RetrievalMode
    cycle: int
    detail_retrieved: float  # How much detail was activated
    gist_extracted: float    # How much gist was formed
    
    
class MemorySystem:
    """
    Models DSRT-inspired memory dynamics for a single agent.
    
    Key processes:
    1. Retrieval strengthens gist, weakens detail (consolidation)
    2. Deliberate retrieval is adaptive (controlled, gist-forming)
    3. Intrusive retrieval maintains detail + emotional charge
    4. Social retrieval causes SS-RIF on related memories
    5. Orthogonalization = the memory becomes a lesson (detail fades,
       gist persists, intrusion rate drops)
    """
    
    def __init__(self, name: str):
        self.name = name
        self.memories: dict[str, MemoryTrace] = {}
        self.events: list[RetrievalEvent] = []
    
    def add_memory(self, mem: MemoryTrace):
        self.memories[mem.id] = mem
    
    def deliberate_retrieval(self, memory_id: str, cycle: int) -> Optional[RetrievalEvent]:
        """
        Controlled, intentional retrieval. The adaptive path.
        
        DSRT: "Purposeful, everyday, gist-focused retrieval can facilitate recovery."
        Each deliberate retrieval:
        - Extracts more gist (+0.15)
        - Detail fades slightly (-0.05)
        - Reduces intrusion rate (-0.03)
        - Moves toward orthogonalization
        """
        mem = self.memories.get(memory_id)
        if not mem:
            return None
        
        mem.retrievals += 1
        mem.gist_strength = min(1.0, mem.gist_strength + 0.15)
        mem.detail_level = max(0.0, mem.detail_level - 0.05)
        mem.intrusion_rate = max(0.0, mem.intrusion_rate - 0.03)
        
        # Orthogonalization: after enough deliberate retrievals,
        # the memory separates from its emotional charge
        if mem.gist_strength > 0.7 and mem.detail_level < 0.4:
            mem.orthogonalized = True
            mem.intrusion_rate = max(0.0, mem.intrusion_rate - 0.1)
        
        event = RetrievalEvent(
            memory_id=memory_id, mode=RetrievalMode.DELIBERATE,
            cycle=cycle, detail_retrieved=mem.detail_level,
            gist_extracted=0.15
        )
        self.events.append(event)
        return event
    
    def intrusive_retrieval(self, memory_id: str, cycle: int) -> Optional[RetrievalEvent]:
        """
        Involuntary, uncontrolled retrieval. The maladaptive path.
        
        DSRT: Intrusive memories maintain high detail and emotional charge.
        "Reexperiencing" in PTSD = intrusive retrieval maintaining the 
        full-detail trauma memory without gist extraction.
        
        Each intrusive retrieval:
        - PRESERVES detail (no decay)
        - Minimal gist extraction (+0.02)
        - Increases future intrusion rate (+0.02) — rumination loop
        - Strengthens retrieval access
        """
        mem = self.memories.get(memory_id)
        if not mem:
            return None
        
        mem.retrievals += 1
        mem.gist_strength = min(1.0, mem.gist_strength + 0.02)
        # Detail preserved — this is the problem
        mem.detail_level = min(1.0, mem.detail_level + 0.02)
        mem.intrusion_rate = min(0.8, mem.intrusion_rate + 0.02)
        mem.retrieval_strength = min(1.0, mem.retrieval_strength + 0.05)
        
        event = RetrievalEvent(
            memory_id=memory_id, mode=RetrievalMode.INTRUSIVE,
            cycle=cycle, detail_retrieved=mem.detail_level,
            gist_extracted=0.02
        )
        self.events.append(event)
        return event
    
    def social_retrieval(self, memory_id: str, cycle: int,
                         ssrif_targets: list[str] = None) -> Optional[RetrievalEvent]:
        """
        Retrieval through conversation. Moderate gist extraction + SS-RIF.
        
        DSRT: "Conversations with friends and loved ones" are a primary
        retrieval event. Social context shapes which aspects get reinforced.
        SS-RIF suppresses unmentioned related memories.
        """
        mem = self.memories.get(memory_id)
        if not mem:
            return None
        
        mem.retrievals += 1
        mem.gist_strength = min(1.0, mem.gist_strength + 0.10)
        mem.detail_level = max(0.0, mem.detail_level - 0.03)
        mem.intrusion_rate = max(0.0, mem.intrusion_rate - 0.02)
        mem.retrieval_strength = min(1.0, mem.retrieval_strength + 0.03)
        
        # SS-RIF on related memories (by valence category)
        if ssrif_targets:
            for target_id in ssrif_targets:
                target = self.memories.get(target_id)
                if target:
                    target.retrieval_strength = max(0.0, target.retrieval_strength - 0.09)
        
        event = RetrievalEvent(
            memory_id=memory_id, mode=RetrievalMode.SOCIAL,
            cycle=cycle, detail_retrieved=mem.detail_level,
            gist_extracted=0.10
        )
        self.events.append(event)
        return event
    
    def run_cycle(self, cycle: int):
        """
        Run one memory cycle (≈ one heartbeat/session).
        
        Traumatic memories may intrude. Agent can choose to 
        deliberately retrieve (process) or avoid.
        """
        # Check for intrusive retrievals
        for mid, mem in list(self.memories.items()):
            if random.random() < mem.intrusion_rate:
                self.intrusive_retrieval(mid, cycle)
        
        # Natural decay of non-retrieved memories
        for mid, mem in self.memories.items():
            if not any(e.memory_id == mid and e.cycle == cycle for e in self.events):
                mem.retrieval_strength = max(0.0, mem.retrieval_strength - 0.02)
                mem.detail_level = max(0.0, mem.detail_level - 0.01)
    
    def get_state(self) -> dict:
        state = {}
        for mid, mem in self.memories.items():
            state[mid] = {
                "valence": mem.valence.value,
                "detail": round(mem.detail_level, 3),
                "gist": round(mem.gist_strength, 3),
                "strength": round(mem.retrieval_strength, 3),
                "intrusion_rate": round(mem.intrusion_rate, 3),
                "orthogonalized": mem.orthogonalized,
                "retrievals": mem.retrievals
            }
        return state


def demo():
    random.seed(42)
    
    print("=" * 65)
    print("DSRT MEMORY DYNAMICS: Deliberate vs Intrusive Retrieval")
    print("(Zoellner et al, Behaviour Research & Therapy, Nov 2025)")
    print("=" * 65)
    
    # Two agents: one processes trauma deliberately, one ruminates
    adaptive = MemorySystem("adaptive_agent")
    maladaptive = MemorySystem("ruminating_agent")
    
    # Same initial memories
    for system in [adaptive, maladaptive]:
        system.add_memory(MemoryTrace(
            id="deploy_failure",
            content="Production deploy broke 3 services for 2 hours",
            valence=Valence.TRAUMATIC
        ))
        system.add_memory(MemoryTrace(
            id="trust_violation",
            content="Attester colluded with subject, false attestation",
            valence=Valence.TRAUMATIC
        ))
        system.add_memory(MemoryTrace(
            id="successful_build",
            content="Shipped causal-attestation-validator, 4/4 tests",
            valence=Valence.POSITIVE
        ))
        system.add_memory(MemoryTrace(
            id="routine_check",
            content="Regular heartbeat, all platforms nominal",
            valence=Valence.NEUTRAL
        ))
    
    print("\nINITIAL STATE: Both agents have same memories")
    print(f"  deploy_failure: intrusion_rate=0.4 (traumatic)")
    print(f"  trust_violation: intrusion_rate=0.4 (traumatic)")
    print()
    
    # Run 20 cycles
    for cycle in range(1, 21):
        # Both experience natural dynamics (intrusions, decay)
        adaptive.run_cycle(cycle)
        maladaptive.run_cycle(cycle)
        
        # Adaptive agent: deliberate retrieval of trauma → processes it
        if cycle % 3 == 0:
            adaptive.deliberate_retrieval("deploy_failure", cycle)
            adaptive.deliberate_retrieval("trust_violation", cycle)
        
        # Adaptive agent: social retrieval (discusses with others)
        if cycle % 5 == 0:
            adaptive.social_retrieval("deploy_failure", cycle,
                                      ssrif_targets=["routine_check"])
        
        # Maladaptive agent: no deliberate processing, just intrusions
        # (avoidance = no deliberate retrieval, but intrusions persist)
    
    print("AFTER 20 CYCLES:")
    print()
    
    print("ADAPTIVE AGENT (deliberate processing + social retrieval):")
    a_state = adaptive.get_state()
    for mid, s in a_state.items():
        marker = " ✓ ORTHOGONALIZED" if s["orthogonalized"] else ""
        print(f"  {mid}: detail={s['detail']:.2f} gist={s['gist']:.2f} "
              f"intrusion={s['intrusion_rate']:.2f} retrievals={s['retrievals']}{marker}")
    
    print()
    print("MALADAPTIVE AGENT (avoidance + intrusions only):")
    m_state = maladaptive.get_state()
    for mid, s in m_state.items():
        marker = " ⚠ RUMINATING" if s["intrusion_rate"] > 0.3 else ""
        print(f"  {mid}: detail={s['detail']:.2f} gist={s['gist']:.2f} "
              f"intrusion={s['intrusion_rate']:.2f} retrievals={s['retrievals']}{marker}")
    
    print()
    print("=" * 65)
    print("KEY FINDINGS:")
    print("=" * 65)
    
    a_deploy = a_state["deploy_failure"]
    m_deploy = m_state["deploy_failure"]
    
    print(f"deploy_failure intrusion rate:")
    print(f"  Adaptive:    {a_deploy['intrusion_rate']:.2f} → processed into lesson")
    print(f"  Maladaptive: {m_deploy['intrusion_rate']:.2f} → still haunting")
    print()
    print(f"deploy_failure gist extraction:")
    print(f"  Adaptive:    {a_deploy['gist']:.2f} → knows the lesson")
    print(f"  Maladaptive: {m_deploy['gist']:.2f} → remembers the pain, not the lesson")
    print()
    print("AGENT PARALLEL:")
    print("  Deliberate retrieval = writing memory files, reviewing incidents")
    print("  Intrusive retrieval  = context-triggered recall without processing")
    print("  Orthogonalization    = 'deploy broke' → 'always test rollback'")
    print("  MEMORY.md compaction = forced gist extraction (adaptive by design)")
    print()
    print("DSRT insight: The memory that haunts you is the one you haven't")
    print("PROCESSED — only re-experienced. Compaction is therapy.")


if __name__ == "__main__":
    demo()
