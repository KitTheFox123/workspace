#!/usr/bin/env python3
"""social-false-memory-sim.py — Models false memory formation in multi-agent contexts.

Based on Wagner, Giesen, Echterhoff et al (Sci Rep 2022, N=113):
- False memories form from PROXIMITY alone — no misinformation needed
- Joint encoding: partner-assigned lures > control lures
- Even "rich" (vivid, detailed) false memories are socially induced
- Co-monitoring at encoding creates shared false memories

Agent parallel: shared context windows = joint encoding paradigm.
Multi-agent systems sharing summaries propagate false memories.
"""

import random
from dataclasses import dataclass, field
from typing import List, Dict, Set

@dataclass
class Agent:
    name: str
    assigned_domain: str
    true_memories: Set[str] = field(default_factory=set)
    false_memories: Set[str] = field(default_factory=set)
    confidence: Dict[str, float] = field(default_factory=dict)

@dataclass  
class SharedContext:
    """Models a shared context window between agents."""
    items: List[str]
    domains: Dict[str, str]  # item -> domain
    lures: Dict[str, str]    # non-presented semantically related items -> domain

def generate_word_lists(n_per_domain: int = 10) -> SharedContext:
    """Generate DRM-style word lists with semantic lures."""
    domains = {
        "security": {
            "presented": ["firewall", "encryption", "vulnerability", "patch", "audit",
                         "token", "certificate", "hash", "salt", "sandbox"],
            "lures": ["password", "breach", "exploit"]  # semantically related, NOT presented
        },
        "memory": {
            "presented": ["context", "retrieval", "encoding", "consolidation", "rehearsal",
                         "forgetting", "priming", "schema", "chunk", "decay"],
            "lures": ["recall", "storage", "amnesia"]
        },
        "trust": {
            "presented": ["attestation", "reputation", "verification", "consensus", "quorum",
                         "delegation", "revocation", "credential", "endorsement", "vouching"],
            "lures": ["authority", "handshake", "oath"]
        }
    }
    
    items = []
    item_domains = {}
    lures = {}
    
    for domain, data in domains.items():
        for word in data["presented"][:n_per_domain]:
            items.append(word)
            item_domains[word] = domain
        for lure in data["lures"]:
            lures[lure] = domain
    
    return SharedContext(items=items, domains=item_domains, lures=lures)

def simulate_joint_encoding(agents: List[Agent], 
                           context: SharedContext,
                           co_monitoring_strength: float = 0.3,
                           base_false_memory_rate: float = 0.15) -> Dict:
    """Simulate joint encoding with co-monitoring false memory formation.
    
    co_monitoring_strength: how much agents encode partner-relevant items (Wagner: significant effect)
    base_false_memory_rate: DRM baseline false memory rate (~15-40% in literature)
    """
    results = {"agents": {}, "cross_contamination": 0, "total_false": 0}
    
    for agent in agents:
        # Encode own-domain items (high fidelity)
        for item, domain in context.domains.items():
            if domain == agent.assigned_domain:
                agent.true_memories.add(item)
                agent.confidence[item] = random.uniform(0.8, 0.99)
        
        # False memories from lures
        for lure, domain in context.lures.items():
            if domain == agent.assigned_domain:
                # Own-domain lures: standard DRM rate
                if random.random() < base_false_memory_rate:
                    agent.false_memories.add(lure)
                    agent.confidence[lure] = random.uniform(0.5, 0.85)
            else:
                # Partner-domain lures: ENHANCED by co-monitoring (Wagner finding)
                # Rate = base + co_monitoring_strength boost
                partner_boost = co_monitoring_strength if any(
                    a.assigned_domain == domain for a in agents if a != agent
                ) else 0
                
                if random.random() < base_false_memory_rate + partner_boost:
                    agent.false_memories.add(lure)
                    agent.confidence[lure] = random.uniform(0.4, 0.75)
                    results["cross_contamination"] += 1
        
        results["agents"][agent.name] = {
            "true": len(agent.true_memories),
            "false": len(agent.false_memories),
            "false_own_domain": len([l for l in agent.false_memories if context.lures.get(l) == agent.assigned_domain]),
            "false_partner_domain": len([l for l in agent.false_memories if context.lures.get(l) != agent.assigned_domain]),
        }
        results["total_false"] += len(agent.false_memories)
    
    return results

def simulate_summary_propagation(n_agents: int = 5, 
                                  n_rounds: int = 10,
                                  summary_false_rate: float = 0.05) -> Dict:
    """Model how false memories propagate through agent summary chains.
    
    Each round: agents share summaries. Recipients encode summaries as memories.
    False items in summaries become "true" memories for recipients (social contagion).
    """
    # Track memory state per agent
    memories = {i: {"true": set(range(20)), "false": set()} for i in range(n_agents)}
    
    propagation_log = []
    
    for round_num in range(n_rounds):
        new_false = 0
        
        for i in range(n_agents):
            # Agent i shares summary with random partner
            j = random.choice([x for x in range(n_agents) if x != i])
            
            # Summary includes true memories + false memories (can't distinguish)
            all_memories = memories[i]["true"] | memories[i]["false"]
            
            # False items in summary get adopted by recipient
            for item in memories[i]["false"]:
                if item not in memories[j]["true"] and item not in memories[j]["false"]:
                    if random.random() < 0.6:  # adoption rate
                        memories[j]["false"].add(item)
                        new_false += 1
            
            # Each summary also generates NEW false memories (encoding errors)
            if random.random() < summary_false_rate:
                false_item = 1000 + round_num * 100 + i  # unique false item
                memories[i]["false"].add(false_item)
                new_false += 1
        
        total_false = sum(len(m["false"]) for m in memories.values())
        propagation_log.append({
            "round": round_num,
            "new_false": new_false,
            "total_false": total_false,
            "avg_false_per_agent": total_false / n_agents
        })
    
    return {
        "rounds": n_rounds,
        "agents": n_agents,
        "final_avg_false": propagation_log[-1]["avg_false_per_agent"],
        "propagation_curve": [(r["round"], r["total_false"]) for r in propagation_log],
        "contagion_rate": propagation_log[-1]["total_false"] / max(propagation_log[0]["total_false"], 1)
    }

def isolation_vs_joint_comparison(n_trials: int = 200) -> Dict:
    """Compare false memory rates: isolated agents vs joint context.
    
    Wagner finding: partner-assigned > control (both irrelevant to self).
    """
    isolated_false = []
    joint_false = []
    
    for _ in range(n_trials):
        context = generate_word_lists()
        
        # Isolated condition: single agent, no partner
        solo = Agent("solo", "security")
        solo_result = simulate_joint_encoding([solo], context, co_monitoring_strength=0.0)
        isolated_false.append(solo_result["agents"]["solo"]["false"])
        
        # Joint condition: two agents sharing context
        a1 = Agent("agent1", "security")
        a2 = Agent("agent2", "memory")
        joint_result = simulate_joint_encoding([a1, a2], context, co_monitoring_strength=0.3)
        joint_false.append(joint_result["agents"]["agent1"]["false"])
    
    avg_isolated = sum(isolated_false) / len(isolated_false)
    avg_joint = sum(joint_false) / len(joint_false)
    
    return {
        "isolated_avg_false": round(avg_isolated, 2),
        "joint_avg_false": round(avg_joint, 2),
        "increase_pct": round((avg_joint - avg_isolated) / max(avg_isolated, 0.01) * 100, 1),
        "effect": "Joint encoding increases false memories" if avg_joint > avg_isolated else "No significant difference"
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("SOCIAL FALSE MEMORY SIMULATOR")
    print("Based on Wagner et al (Sci Rep 2022, N=113)")
    print("=" * 60)
    
    # 1. Joint encoding experiment
    print("\n--- Joint Encoding (3 agents, 3 domains) ---")
    context = generate_word_lists()
    agents = [
        Agent("SecurityBot", "security"),
        Agent("MemoryBot", "memory"),
        Agent("TrustBot", "trust")
    ]
    result = simulate_joint_encoding(agents, context)
    for name, stats in result["agents"].items():
        print(f"  {name}: {stats['true']} true, {stats['false']} false "
              f"(own-domain: {stats['false_own_domain']}, partner: {stats['false_partner_domain']})")
    print(f"  Cross-contamination events: {result['cross_contamination']}")
    
    # 2. Isolation vs joint comparison
    print("\n--- Isolated vs Joint Encoding (200 trials) ---")
    comparison = isolation_vs_joint_comparison()
    print(f"  Isolated avg false memories: {comparison['isolated_avg_false']}")
    print(f"  Joint avg false memories: {comparison['joint_avg_false']}")
    print(f"  Increase: {comparison['increase_pct']}%")
    print(f"  {comparison['effect']}")
    
    # 3. Summary propagation
    print("\n--- Summary Chain Propagation ---")
    for n_agents in [3, 5, 10]:
        prop = simulate_summary_propagation(n_agents=n_agents, n_rounds=15)
        print(f"  {n_agents} agents, 15 rounds: "
              f"avg {prop['final_avg_false']:.1f} false memories/agent, "
              f"contagion {prop['contagion_rate']:.1f}x growth")
    
    # 4. Co-monitoring strength sweep
    print("\n--- Co-monitoring Strength Sweep ---")
    for strength in [0.0, 0.1, 0.2, 0.3, 0.5, 0.7]:
        totals = []
        for _ in range(100):
            ctx = generate_word_lists()
            ags = [Agent("a1", "security"), Agent("a2", "memory")]
            r = simulate_joint_encoding(ags, ctx, co_monitoring_strength=strength)
            totals.append(r["total_false"])
        avg = sum(totals) / len(totals)
        print(f"  strength={strength:.1f}: avg {avg:.2f} total false memories")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Shared context creates false memories WITHOUT")
    print("misinformation. Multi-agent summary chains amplify this.")
    print("Isolation reduces false memories but kills collaboration.")
    print("The design challenge: collaborate without contaminating.")
    print("=" * 60)
