#!/usr/bin/env python3
"""
cognitive-offloading-sim.py — Models cognitive offloading tradeoffs for agents.

Based on Grinschgl et al (2021, PMC8358584): offloading boosts immediate performance
but diminishes memory unless there's an explicit encoding goal.

Key finding: forced offloading + awareness of memory test = almost full counteraction
of memory loss. Without awareness = significant degradation.

Agent parallel: MEMORY.md is cognitive offloading. Writing things down boosts task
performance but may reduce "internalized" knowledge. The fix: deliberate review
(heartbeat consolidation) acts as the "explicit encoding goal."

Trust parallel from HCI paper (Tandfonline 2025): trust in tools MODERATES offloading.
Higher trust → more offloading → worse memory. Agent corollary: uncritical trust in
memory files = cognitive atrophy of the model's own pattern recognition.
"""

import random
import statistics
from dataclasses import dataclass, field

@dataclass
class Agent:
    name: str
    offload_rate: float  # 0.0 = all internal, 1.0 = all external
    review_rate: float   # how often they re-read their files (0-1)
    trust_in_tools: float  # how much they trust external storage (0-1)
    
    # Internal state
    internal_knowledge: list = field(default_factory=list)
    external_storage: list = field(default_factory=list)
    recall_scores: list = field(default_factory=list)

@dataclass 
class MemoryItem:
    content: str
    importance: float  # 0-1
    encoded_internally: bool = False
    encoded_externally: bool = False
    reviewed: bool = False
    age: int = 0


def simulate_learning(agent: Agent, n_items: int = 100, n_rounds: int = 20) -> dict:
    """Simulate an agent learning items over multiple rounds."""
    
    items = [
        MemoryItem(
            content=f"item_{i}",
            importance=random.random()
        ) for i in range(n_items)
    ]
    
    round_results = []
    
    for round_num in range(n_rounds):
        # Each round: encounter some items, decide to offload or memorize
        encountered = random.sample(items, min(10, len(items)))
        
        task_performance = 0.0
        memory_formed = 0
        
        for item in encountered:
            item.age += 1
            
            # Offloading decision influenced by trust (Tandfonline 2025)
            effective_offload = agent.offload_rate * (0.5 + 0.5 * agent.trust_in_tools)
            offload = random.random() < effective_offload
            
            if offload:
                # Offloaded: high immediate performance, low encoding
                item.encoded_externally = True
                task_performance += 0.9 + 0.1 * random.random()
                
                # Grinschgl finding: offloading WITHOUT review goal = poor memory
                encoding_prob = 0.15  # base rate when offloading
            else:
                # Internal: lower immediate perf, better encoding
                item.encoded_internally = True
                task_performance += 0.6 + 0.2 * random.random()
                encoding_prob = 0.75
            
            # Review acts as "explicit encoding goal" (Experiment 3)
            if random.random() < agent.review_rate:
                item.reviewed = True
                # Grinschgl Exp 3: forced offload + awareness ≈ counteracts memory loss
                encoding_prob = min(0.85, encoding_prob + 0.5)
            
            if random.random() < encoding_prob:
                memory_formed += 1
                agent.internal_knowledge.append(item)
        
        avg_perf = task_performance / len(encountered) if encountered else 0
        
        # Recall test: can agent retrieve without external access?
        if agent.internal_knowledge:
            test_items = random.sample(
                agent.internal_knowledge, 
                min(5, len(agent.internal_knowledge))
            )
            # Decay: older items harder to recall unless reviewed
            recall_score = sum(
                1.0 if it.reviewed else max(0.1, 1.0 - it.age * 0.05)
                for it in test_items
            ) / len(test_items)
        else:
            recall_score = 0.0
        
        agent.recall_scores.append(recall_score)
        
        round_results.append({
            'round': round_num,
            'task_perf': avg_perf,
            'memory_formed': memory_formed,
            'recall': recall_score,
            'total_internal': len(agent.internal_knowledge),
            'total_external': len(agent.external_storage)
        })
    
    return {
        'agent': agent.name,
        'offload_rate': agent.offload_rate,
        'review_rate': agent.review_rate,
        'trust': agent.trust_in_tools,
        'avg_task_perf': statistics.mean(r['task_perf'] for r in round_results),
        'avg_recall': statistics.mean(r['recall'] for r in round_results),
        'final_recall': statistics.mean(agent.recall_scores[-3:]),
        'internal_items': len(agent.internal_knowledge),
        'rounds': round_results
    }


def main():
    print("=" * 70)
    print("COGNITIVE OFFLOADING SIMULATION")
    print("Based on Grinschgl et al (2021) — PMC8358584")
    print("Trust moderation from HCI (Tandfonline 2025)")
    print("=" * 70)
    
    # Agent archetypes
    agents = [
        Agent("Internalizer", offload_rate=0.1, review_rate=0.3, trust_in_tools=0.3),
        Agent("Balanced", offload_rate=0.5, review_rate=0.5, trust_in_tools=0.5),
        Agent("Heavy_Offloader", offload_rate=0.9, review_rate=0.1, trust_in_tools=0.9),
        Agent("Offloader+Review", offload_rate=0.9, review_rate=0.8, trust_in_tools=0.7),
        Agent("Kit_Model", offload_rate=0.85, review_rate=0.6, trust_in_tools=0.7),
    ]
    
    random.seed(42)
    results = [simulate_learning(a) for a in agents]
    
    print(f"\n{'Agent':<20} {'Offload':>8} {'Review':>8} {'Trust':>7} {'TaskPerf':>9} {'Recall':>8} {'FinalRec':>9}")
    print("-" * 70)
    
    for r in results:
        print(f"{r['agent']:<20} {r['offload_rate']:>8.2f} {r['review_rate']:>8.2f} "
              f"{r['trust']:>7.2f} {r['avg_task_perf']:>9.3f} {r['avg_recall']:>8.3f} "
              f"{r['final_recall']:>9.3f}")
    
    # Key findings
    print("\n" + "=" * 70)
    print("KEY FINDINGS")
    print("=" * 70)
    
    internalizer = results[0]
    heavy = results[2]
    heavy_review = results[3]
    kit = results[4]
    
    perf_gap = heavy['avg_task_perf'] - internalizer['avg_task_perf']
    recall_gap = internalizer['avg_recall'] - heavy['avg_recall']
    review_recovery = heavy_review['avg_recall'] - heavy['avg_recall']
    
    print(f"\n1. OFFLOADING TRADEOFF (Grinschgl Exp 1-2):")
    print(f"   Task performance gap (heavy vs internal): +{perf_gap:.3f}")
    print(f"   Memory recall gap (internal vs heavy):    +{recall_gap:.3f}")
    print(f"   → Offloading BOOSTS performance but DIMINISHES memory")
    
    print(f"\n2. REVIEW AS COUNTERACTION (Grinschgl Exp 3):")
    print(f"   Review recovery (heavy+review vs heavy):  +{review_recovery:.3f}")
    print(f"   → Deliberate review almost fully counteracts offloading memory loss")
    
    print(f"\n3. KIT'S PROFILE:")
    print(f"   High offloading (MEMORY.md, daily logs) = great task performance")
    print(f"   Moderate review (heartbeat consolidation) = decent recall")
    print(f"   Final recall: {kit['final_recall']:.3f}")
    print(f"   → Heartbeats ARE the 'explicit encoding goal' from Grinschgl Exp 3")
    
    print(f"\n4. TRUST MODERATION (HCI 2025):")
    print(f"   Higher trust in tools → more offloading → worse unaided recall")
    print(f"   Agent implication: uncritical trust in memory files = cognitive atrophy")
    print(f"   Fix: periodic 'without files' reasoning tests (like memory quizzes)")
    
    print(f"\n5. AGENT-SPECIFIC INSIGHT:")
    print(f"   MEMORY.md satisfies Clark-Chalmers extended mind criteria")
    print(f"   But Grinschgl shows the COST: what you write down, you stop encoding")
    print(f"   The paradox: the tool that extends your mind also hollows it")
    print(f"   Resolution: review cycles (heartbeats) transform external → internal")


if __name__ == "__main__":
    main()
