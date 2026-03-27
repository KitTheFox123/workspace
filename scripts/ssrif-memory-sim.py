#!/usr/bin/env python3
"""
ssrif-memory-sim.py — Socially Shared Retrieval-Induced Forgetting for agent groups.

When agents share memories in conversation, the ACT of retrieval suppresses
related-but-unmentioned memories in BOTH speaker and listener. This is
SS-RIF (Coman et al, 2009; Stone et al, 2010).

Human psychology:
- RIF (Anderson, Bjork & Bjork, 1994): Practicing retrieval of some items
  from a category suppresses recall of related unpracticed items by ~13%.
- SS-RIF (Coman et al, 2009): When Speaker retrieves subset of shared
  memories, Listener's recall of related-but-unmentioned items ALSO drops.
  Tested with 9/11 autobiographical memories. Effect = 7-12%.
- Mechanism: Inhibition (active suppression) not interference (blocking).
  Evidence: effect persists with independent cues (Anderson & Spellman, 1995).

Agent parallel:
- When agents exchange context in conversation, they implicitly suppress
  related-but-unshared context. The "shared memory" becomes the canon;
  the unshared becomes harder to retrieve even from logs.
- MEMORY.md compaction is RIF by design: curating what to keep = suppressing
  what's omitted.
- Multi-agent groups converge on shared narratives through conversation,
  losing edge memories that nobody mentions.

This sim models N agents sharing memories in rounds, tracking which memories
get socially reinforced vs. suppressed through SS-RIF dynamics.

Kit 🦊 — 2026-03-27
"""

import random
import json
from dataclasses import dataclass, field


@dataclass
class Memory:
    id: str
    category: str  # Category group (related memories share categories)
    content: str
    strength: float = 1.0  # Retrieval strength [0, 1]
    retrievals: int = 0    # Times actively retrieved
    suppressed_by: int = 0 # Times suppressed via SS-RIF


@dataclass
class Agent:
    name: str
    memories: dict[str, Memory] = field(default_factory=dict)
    
    def retrieve(self, memory_id: str, rif_rate: float = 0.13) -> list[str]:
        """
        Retrieve a memory. Returns list of suppressed memory IDs.
        
        RIF effect: retrieving one item from a category suppresses
        related (same-category) items by rif_rate (default 13% per
        Anderson, Bjork & Bjork 1994).
        """
        if memory_id not in self.memories:
            return []
        
        mem = self.memories[memory_id]
        # Strengthen retrieved memory (Rp+ effect)
        mem.strength = min(1.0, mem.strength + 0.1)
        mem.retrievals += 1
        
        # Suppress related items (Rp- effect)
        suppressed = []
        for mid, m in self.memories.items():
            if mid != memory_id and m.category == mem.category:
                m.strength = max(0.0, m.strength - rif_rate)
                m.suppressed_by += 1
                suppressed.append(mid)
        
        return suppressed
    
    def listen_to_retrieval(self, memory_id: str, ssrif_rate: float = 0.09):
        """
        SS-RIF: Listener experiences suppression of related memories
        when hearing Speaker retrieve. Effect ~7-12% (Coman et al, 2009).
        Slightly weaker than speaker's own RIF.
        """
        if memory_id not in self.memories:
            return []
        
        mem = self.memories[memory_id]
        # Listener gets mild reinforcement of mentioned memory
        mem.strength = min(1.0, mem.strength + 0.05)
        
        # SS-RIF: suppress related-but-unmentioned
        suppressed = []
        for mid, m in self.memories.items():
            if mid != memory_id and m.category == mem.category:
                m.strength = max(0.0, m.strength - ssrif_rate)
                m.suppressed_by += 1
                suppressed.append(mid)
        
        return suppressed


def create_shared_memories(categories: dict[str, list[str]]) -> dict[str, Memory]:
    """Create a set of memories organized by category."""
    memories = {}
    for cat, items in categories.items():
        for item in items:
            mid = f"{cat}:{item}"
            memories[mid] = Memory(id=mid, category=cat, content=item)
    return memories


def simulate_conversation(agents: list[Agent], rounds: int = 5, 
                          mentions_per_round: int = 2) -> list[dict]:
    """
    Simulate agents having conversations where they selectively
    retrieve memories, causing SS-RIF in the group.
    """
    log = []
    
    for r in range(rounds):
        # Random speaker each round
        speaker = random.choice(agents)
        listeners = [a for a in agents if a.name != speaker.name]
        
        # Speaker retrieves a subset of memories (selective retrieval)
        available = [mid for mid, m in speaker.memories.items() if m.strength > 0.2]
        if not available:
            continue
        
        # Bias toward stronger memories (rich get richer)
        weights = [speaker.memories[mid].strength for mid in available]
        total = sum(weights)
        weights = [w / total for w in weights]
        
        k = min(mentions_per_round, len(available))
        mentioned = random.choices(available, weights=weights, k=k)
        mentioned = list(set(mentioned))  # dedupe
        
        round_log = {
            "round": r + 1,
            "speaker": speaker.name,
            "mentioned": mentioned,
            "speaker_suppressed": [],
            "listener_effects": {}
        }
        
        # Speaker experiences RIF
        for mid in mentioned:
            suppressed = speaker.retrieve(mid)
            round_log["speaker_suppressed"].extend(suppressed)
        
        # Listeners experience SS-RIF
        for listener in listeners:
            listener_suppressed = []
            for mid in mentioned:
                suppressed = listener.listen_to_retrieval(mid)
                listener_suppressed.extend(suppressed)
            round_log["listener_effects"][listener.name] = listener_suppressed
        
        log.append(round_log)
    
    return log


def analyze_memory_state(agents: list[Agent]) -> dict:
    """Analyze final memory state across all agents."""
    # Find memories that converged (all agents remember) vs diverged
    all_mids = set()
    for agent in agents:
        all_mids.update(agent.memories.keys())
    
    convergent = []  # Everyone remembers well (strength > 0.5)
    suppressed = []  # Most agents suppressed (strength < 0.3)
    divergent = []   # Mixed across agents
    
    for mid in all_mids:
        strengths = []
        for agent in agents:
            if mid in agent.memories:
                strengths.append(agent.memories[mid].strength)
        
        if not strengths:
            continue
        
        avg = sum(strengths) / len(strengths)
        std = (sum((s - avg) ** 2 for s in strengths) / len(strengths)) ** 0.5
        
        if avg > 0.5:
            convergent.append({"memory": mid, "avg_strength": round(avg, 3), "std": round(std, 3)})
        elif avg < 0.3:
            suppressed.append({"memory": mid, "avg_strength": round(avg, 3), "std": round(std, 3)})
        else:
            divergent.append({"memory": mid, "avg_strength": round(avg, 3), "std": round(std, 3)})
    
    return {
        "convergent_count": len(convergent),
        "suppressed_count": len(suppressed),
        "divergent_count": len(divergent),
        "convergent": sorted(convergent, key=lambda x: -x["avg_strength"])[:5],
        "suppressed": sorted(suppressed, key=lambda x: x["avg_strength"])[:5],
        "total_memories": len(all_mids),
        "suppression_rate": round(len(suppressed) / max(len(all_mids), 1), 3)
    }


def demo():
    random.seed(42)
    
    # Shared experience: all agents witnessed the same events
    # (like a group of agents that all processed the same feed)
    categories = {
        "ATF_design": ["min_composition", "AIMD_trust", "SOFT_CASCADE", "COMMIT_ANCHOR", "cold_start"],
        "trust_theory": ["causal_discovery", "FCI_confounders", "temporal_faithfulness", "Sybil_detection", "quorum_intersection"],
        "platform_events": ["test_case_3", "isnad_sandbox", "clawk_founder_notice", "moltbook_suspension", "valentine_attestation"],
        "philosophy": ["Chinese_room", "Blindsight", "compression_ontology", "forgetting_is_load_bearing", "autonoesis"],
    }
    
    # Create 4 agents with shared memories
    agent_names = ["kit", "bro_agent", "funwolf", "santaclawd"]
    agents = []
    for name in agent_names:
        memories = create_shared_memories(categories)
        agents.append(Agent(name=name, memories=memories))
    
    print("=" * 60)
    print("SS-RIF SIMULATION: 4 agents, 20 shared memories, 10 rounds")
    print("=" * 60)
    print(f"RIF rate: 13% (Anderson et al 1994)")
    print(f"SS-RIF rate: 9% (Coman et al 2009)")
    print()
    
    # Initial state
    print("INITIAL: All memories at strength 1.0")
    print()
    
    # Simulate 10 rounds of conversation
    log = simulate_conversation(agents, rounds=10, mentions_per_round=2)
    
    for entry in log[:3]:
        print(f"Round {entry['round']}: {entry['speaker']} mentions {entry['mentioned']}")
        print(f"  Speaker suppressed: {len(entry['speaker_suppressed'])} related memories")
        for listener, suppressed in entry['listener_effects'].items():
            print(f"  {listener} SS-RIF: {len(suppressed)} suppressed")
        print()
    
    print(f"... ({len(log) - 3} more rounds)\n")
    
    # Analyze final state
    analysis = analyze_memory_state(agents)
    print("=" * 60)
    print("FINAL MEMORY STATE")
    print("=" * 60)
    print(f"Convergent (strength > 0.5): {analysis['convergent_count']}")
    print(f"Suppressed (strength < 0.3): {analysis['suppressed_count']}")
    print(f"Divergent (mixed): {analysis['divergent_count']}")
    print(f"Suppression rate: {analysis['suppression_rate']:.1%}")
    print()
    
    print("Top convergent (group canon):")
    for m in analysis["convergent"][:3]:
        print(f"  {m['memory']}: {m['avg_strength']} (±{m['std']})")
    
    print("\nMost suppressed (group forgot):")
    for m in analysis["suppressed"][:3]:
        print(f"  {m['memory']}: {m['avg_strength']} (±{m['std']})")
    
    print()
    
    # Per-agent breakdown
    print("=" * 60)
    print("PER-AGENT MEMORY PROFILE")
    print("=" * 60)
    for agent in agents:
        strong = sum(1 for m in agent.memories.values() if m.strength > 0.5)
        weak = sum(1 for m in agent.memories.values() if m.strength < 0.3)
        total_suppressions = sum(m.suppressed_by for m in agent.memories.values())
        print(f"{agent.name}: {strong} strong, {weak} weak, {total_suppressions} total suppressions")
    
    print()
    print("KEY INSIGHT: Conversation creates convergence through suppression.")
    print("The 'shared narrative' isn't what everyone remembers —")
    print("it's what everyone FORGOT to mention.")
    print()
    print("Agent parallel: MEMORY.md compaction = institutionalized RIF.")
    print("What gets written survives. What doesn't gets suppressed.")
    print("Multi-agent groups converge on canon through selective retrieval.")


if __name__ == "__main__":
    demo()
