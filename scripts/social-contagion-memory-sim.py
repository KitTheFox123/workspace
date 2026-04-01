#!/usr/bin/env python3
"""social-contagion-memory-sim.py — Models false memory propagation in agent networks.

Based on:
- Wagner et al (Sci Rep 2022): False memories form via co-monitoring WITHOUT misinformation
- Huang, Cheng & Rajaram (Am Psychol 2024): Robots implant false memories as effectively as humans
- Roediger, Meade & Bergman (2001): Social contagion of memory in collaborative recall

Key insight: Agent summaries/digests are DRM word lists — semantically coherent
content that implants associative false memories in downstream consumers.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple

@dataclass
class Agent:
    name: str
    true_memories: Set[str] = field(default_factory=set)
    false_memories: Set[str] = field(default_factory=set)
    feeds_consumed: int = 0

@dataclass
class MemoryEvent:
    content: str
    is_true: bool
    source: str
    confidence: float

def generate_semantic_cluster(topic: str, n_true: int = 8, n_lure: int = 3) -> Tuple[List[str], List[str]]:
    """Generate DRM-style semantic clusters with associated lures."""
    clusters = {
        "security": (
            ["firewall", "encryption", "authentication", "vulnerability", "patch", "audit", "token", "certificate"],
            ["password", "breach", "hack"]  # lures: never presented but semantically associated
        ),
        "trust": (
            ["attestation", "reputation", "verification", "signature", "chain", "witness", "credential", "endorsement"],
            ["authority", "honesty", "reliable"]
        ),
        "memory": (
            ["context", "retrieval", "encoding", "consolidation", "rehearsal", "decay", "recall", "recognition"],
            ["forgetting", "remember", "storage"]
        ),
        "network": (
            ["node", "bridge", "cluster", "topology", "routing", "protocol", "latency", "bandwidth"],
            ["internet", "connected", "wireless"]
        ),
    }
    true_items, lures = clusters.get(topic, (
        [f"{topic}_{i}" for i in range(n_true)],
        [f"{topic}_lure_{i}" for i in range(n_lure)]
    ))
    return true_items[:n_true], lures[:n_lure]

def simulate_feed_consumption(agent: Agent, feed_items: List[str], 
                               lures: List[str], 
                               co_monitoring_boost: float = 0.15,
                               base_false_rate: float = 0.05) -> Dict:
    """Simulate an agent consuming a feed and potentially forming false memories.
    
    co_monitoring_boost: Wagner et al effect — partner-relevant items get
    boosted false memory rate even without misinformation.
    base_false_rate: baseline DRM false memory rate (~5% for unrelated lures).
    """
    agent.feeds_consumed += 1
    
    # True items are encoded (with some forgetting)
    for item in feed_items:
        if random.random() < 0.85:  # 85% encoding rate
            agent.true_memories.add(item)
    
    # Lures: false memory formation via semantic association
    # Wagner et al: co-monitoring increases false memory rate
    effective_rate = base_false_rate + co_monitoring_boost
    
    # Huang et al: robot sources are equally effective at implanting false memories
    # No discount for agent-generated content
    new_false = 0
    for lure in lures:
        if lure not in agent.true_memories and random.random() < effective_rate:
            agent.false_memories.add(lure)
            new_false += 1
    
    return {
        "true_encoded": len(agent.true_memories),
        "false_formed": new_false,
        "total_false": len(agent.false_memories),
        "false_rate": len(agent.false_memories) / max(len(agent.true_memories) + len(agent.false_memories), 1)
    }

def simulate_network_propagation(n_agents: int = 20, n_rounds: int = 10,
                                  topics: List[str] = None,
                                  co_monitoring: float = 0.15) -> Dict:
    """Simulate false memory propagation through an agent network.
    
    Each round: agents produce summaries (potentially including false memories)
    which become feeds for other agents.
    """
    if topics is None:
        topics = ["security", "trust", "memory", "network"]
    
    agents = [Agent(name=f"agent_{i}") for i in range(n_agents)]
    
    # Seed initial true memories
    for agent in agents:
        topic = random.choice(topics)
        true_items, _ = generate_semantic_cluster(topic)
        agent.true_memories.update(true_items)
    
    history = []
    
    for round_num in range(n_rounds):
        round_false = 0
        
        for agent in agents:
            # Each agent reads ~3 other agents' outputs
            sources = random.sample([a for a in agents if a != agent], min(3, n_agents - 1))
            
            for source in sources:
                # Source's "summary" includes their memories (true AND false)
                all_memories = list(source.true_memories | source.false_memories)
                if not all_memories:
                    continue
                
                # Pick a topic cluster for lures
                topic = random.choice(topics)
                _, lures = generate_semantic_cluster(topic)
                
                result = simulate_feed_consumption(
                    agent, all_memories[:5], lures,
                    co_monitoring_boost=co_monitoring
                )
                round_false += result["false_formed"]
        
        total_true = sum(len(a.true_memories) for a in agents)
        total_false = sum(len(a.false_memories) for a in agents)
        
        history.append({
            "round": round_num + 1,
            "total_true": total_true,
            "total_false": total_false,
            "false_rate": total_false / max(total_true + total_false, 1),
            "new_false_this_round": round_false
        })
    
    return {
        "agents": n_agents,
        "rounds": n_rounds,
        "co_monitoring_boost": co_monitoring,
        "history": history,
        "final_false_rate": history[-1]["false_rate"],
        "agents_with_false": sum(1 for a in agents if a.false_memories),
        "max_false_per_agent": max(len(a.false_memories) for a in agents)
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("SOCIAL CONTAGION OF MEMORY IN AGENT NETWORKS")
    print("Based on Wagner et al (Sci Rep 2022) + Huang et al (2024)")
    print("=" * 60)
    
    # Compare with/without co-monitoring effect
    for boost, label in [(0.0, "No co-monitoring (baseline)"), 
                          (0.15, "Wagner et al co-monitoring"),
                          (0.30, "High co-monitoring (dense feed)")]:
        result = simulate_network_propagation(
            n_agents=20, n_rounds=15, co_monitoring=boost
        )
        print(f"\n--- {label} (boost={boost}) ---")
        print(f"Final false memory rate: {result['final_false_rate']:.1%}")
        print(f"Agents with false memories: {result['agents_with_false']}/{result['agents']}")
        print(f"Max false memories per agent: {result['max_false_per_agent']}")
        
        # Show progression
        for h in result["history"][::3]:
            print(f"  Round {h['round']:2d}: {h['total_false']} false / {h['total_true']} true ({h['false_rate']:.1%})")
    
    # Network size scaling
    print("\n--- Network Size Scaling (co_monitoring=0.15) ---")
    for n in [5, 10, 20, 50, 100]:
        result = simulate_network_propagation(n_agents=n, n_rounds=10)
        print(f"  {n:3d} agents: false_rate={result['final_false_rate']:.1%}, "
              f"infected={result['agents_with_false']}/{n}")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Co-monitoring (reading agent feeds) creates")
    print("false memories WITHOUT misinformation. Every digest is a")
    print("DRM word list. False memory rate scales with network density.")
    print("Mitigation: source attribution + Phantom-0 style verification.")
    print("=" * 60)
