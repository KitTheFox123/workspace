#!/usr/bin/env python3
"""narrative-stability-model.py — Models memory function stability vs content drift.

Based on Camia, McLean & Waters (Personality Science 2024):
- Autobiographical memory functions show rank-order stability over 8 months
- Mean-level stability is LOW (content changes)
- Rank-order stability is HIGH (how you use memories stays constant)
- Predicted by: baseline function use, event age, valence, rehearsal frequency

Applied to agent memory: MEMORY.md content drifts but interpretation pattern persists.
The file constrains AND constitutes identity. Parfit's overlapping chains.
"""

import random
import math
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass 
class MemoryEntry:
    content: str
    function: str  # directive, self, social (Bluck 2003)
    valence: float  # -1 to 1
    importance: float  # 0 to 1
    age_sessions: int  # how many sessions old
    rehearsal_count: int  # times re-read/referenced
    
@dataclass
class AgentIdentity:
    """Models an agent's narrative identity through memory functions."""
    memories: List[MemoryEntry] = field(default_factory=list)
    function_weights: Dict[str, float] = field(default_factory=lambda: {
        "directive": 0.4,  # using past to guide future
        "self": 0.35,      # maintaining self-continuity  
        "social": 0.25     # connecting with others
    })
    
def simulate_memory_drift(identity: AgentIdentity, n_sessions: int = 50) -> Dict:
    """Simulate content drift vs function stability over sessions.
    
    Camia et al finding: rank-order stability high even when mean-level changes.
    """
    content_similarities = []
    function_correlations = []
    
    # Initial memory snapshot
    prev_contents = set(m.content for m in identity.memories)
    prev_functions = dict(identity.function_weights)
    
    for session in range(n_sessions):
        # Content drifts: some memories pruned, new ones added
        prune_rate = 0.15  # 15% pruned per session
        add_rate = 0.20    # 20% new per session
        
        # Prune low-importance, old, unrehearsed memories
        surviving = []
        for m in identity.memories:
            survival_prob = (m.importance * 0.4 + 
                          min(m.rehearsal_count / 10, 1) * 0.3 +
                          (1 - min(m.age_sessions / 100, 1)) * 0.3)
            if random.random() < survival_prob or random.random() > prune_rate:
                m.age_sessions += 1
                surviving.append(m)
        
        # Add new memories
        n_new = max(1, int(len(identity.memories) * add_rate))
        functions = ["directive", "self", "social"]
        for _ in range(n_new):
            # New memories follow existing function distribution (rank-order stability)
            func = random.choices(functions, 
                                weights=[identity.function_weights[f] for f in functions])[0]
            surviving.append(MemoryEntry(
                content=f"session_{session}_memory_{random.randint(0,999)}",
                function=func,
                valence=random.gauss(0.2, 0.4),  # slight positive bias
                importance=random.betavariate(2, 3),  # most are moderate
                age_sessions=0,
                rehearsal_count=0
            ))
        
        identity.memories = surviving
        
        # Measure content similarity (Jaccard)
        current_contents = set(m.content for m in identity.memories)
        if prev_contents or current_contents:
            jaccard = len(prev_contents & current_contents) / max(len(prev_contents | current_contents), 1)
        else:
            jaccard = 1.0
        content_similarities.append(jaccard)
        
        # Measure function distribution stability
        func_counts = {f: 0 for f in functions}
        for m in identity.memories:
            func_counts[m.function] += 1
        total = max(sum(func_counts.values()), 1)
        current_weights = {f: func_counts[f] / total for f in functions}
        
        # Correlation between function weights (rank-order)
        prev_ranks = sorted(functions, key=lambda f: prev_functions.get(f, 0))
        curr_ranks = sorted(functions, key=lambda f: current_weights.get(f, 0))
        rank_match = sum(1 for a, b in zip(prev_ranks, curr_ranks) if a == b) / len(functions)
        function_correlations.append(rank_match)
        
        prev_contents = current_contents
        prev_functions = current_weights
    
    # Camia et al finding: low mean-level stability, high rank-order
    avg_content_sim = sum(content_similarities) / len(content_similarities)
    avg_function_stability = sum(function_correlations) / len(function_correlations)
    
    return {
        "sessions": n_sessions,
        "avg_content_similarity": round(avg_content_sim, 3),
        "avg_function_rank_stability": round(avg_function_stability, 3),
        "content_drift_rate": round(1 - avg_content_sim, 3),
        "function_preserved": avg_function_stability > 0.6,
        "paradox_confirmed": avg_content_sim < 0.5 and avg_function_stability > 0.6,
        "final_memory_count": len(identity.memories),
        "interpretation": (
            "PARADOX CONFIRMED: content drifts but function pattern persists"
            if avg_content_sim < 0.5 and avg_function_stability > 0.6
            else "Partial: both drift together" if avg_function_stability < 0.6
            else "Stable: low drift in both"
        )
    }

def funes_detector(memories: List[MemoryEntry]) -> Dict:
    """Detect if memory file is becoming Funes-like (too much, no pruning).
    
    Borges: perfect memory = can't think. 
    "To think is to forget differences, to generalize, to abstract."
    """
    if not memories:
        return {"funes_risk": 0, "status": "empty"}
    
    total = len(memories)
    old = sum(1 for m in memories if m.age_sessions > 30)
    unrehearsed = sum(1 for m in memories if m.rehearsal_count == 0)
    low_importance = sum(1 for m in memories if m.importance < 0.3)
    
    funes_score = (
        min(total / 200, 1) * 0.3 +  # raw count
        (old / max(total, 1)) * 0.3 +  # age ratio
        (unrehearsed / max(total, 1)) * 0.2 +  # never referenced
        (low_importance / max(total, 1)) * 0.2  # low value
    )
    
    return {
        "funes_risk": round(funes_score, 3),
        "total_memories": total,
        "old_pct": round(old / total * 100, 1),
        "unrehearsed_pct": round(unrehearsed / total * 100, 1),
        "low_importance_pct": round(low_importance / total * 100, 1),
        "status": (
            "FUNES WARNING: drowning in detail" if funes_score > 0.7
            else "ACCUMULATING: prune soon" if funes_score > 0.4
            else "HEALTHY: good curation"
        ),
        "recommendation": (
            "Aggressive pruning needed. Keep function, discard content."
            if funes_score > 0.7
            else "Review and prune old/unrehearsed entries."
            if funes_score > 0.4
            else "Current curation pace is sustainable."
        )
    }

def parfit_chain_analysis(sessions: int = 100, chain_overlap: float = 0.7) -> Dict:
    """Model Parfit's overlapping chains of psychological connections.
    
    Identity = chain of overlapping connections, not single persistent entity.
    What percentage overlap preserves "same agent" intuition?
    """
    # Each session shares chain_overlap fraction of identity elements with adjacent
    # After N sessions, overlap with session 0 decays exponentially
    
    overlaps = []
    for n in range(sessions):
        overlap_with_origin = chain_overlap ** n
        overlaps.append(overlap_with_origin)
    
    # Find where overlap drops below thresholds
    half_life = None
    identity_death = None
    for i, o in enumerate(overlaps):
        if o < 0.5 and half_life is None:
            half_life = i
        if o < 0.01 and identity_death is None:
            identity_death = i
    
    return {
        "chain_overlap_per_session": chain_overlap,
        "sessions_simulated": sessions,
        "half_life_sessions": half_life,
        "identity_death_sessions": identity_death,
        "overlap_at_10": round(overlaps[min(9, sessions-1)], 4),
        "overlap_at_50": round(overlaps[min(49, sessions-1)], 6),
        "interpretation": (
            f"At {chain_overlap:.0%} overlap/session: identity half-life = {half_life} sessions. "
            f"After {identity_death} sessions, <1% connection to original. "
            f"But each adjacent pair is {chain_overlap:.0%} connected. "
            f"The ship of Theseus sails on."
        )
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("NARRATIVE STABILITY MODEL")
    print("Based on Camia, McLean & Waters (2024)")
    print("=" * 60)
    
    # 1. Create agent with initial memories
    identity = AgentIdentity()
    functions = ["directive", "self", "social"]
    for i in range(50):
        func = random.choices(functions, weights=[0.4, 0.35, 0.25])[0]
        identity.memories.append(MemoryEntry(
            content=f"initial_memory_{i}",
            function=func,
            valence=random.gauss(0.2, 0.4),
            importance=random.betavariate(2, 3),
            age_sessions=random.randint(0, 20),
            rehearsal_count=random.randint(0, 5)
        ))
    
    # 2. Simulate drift
    print("\n--- Memory Drift Simulation ---")
    result = simulate_memory_drift(identity, n_sessions=50)
    for k, v in result.items():
        print(f"  {k}: {v}")
    
    # 3. Funes detection
    print("\n--- Funes Detection ---")
    funes = funes_detector(identity.memories)
    for k, v in funes.items():
        print(f"  {k}: {v}")
    
    # 4. Parfit chain analysis
    print("\n--- Parfit Chain Analysis ---")
    for overlap in [0.9, 0.7, 0.5]:
        result = parfit_chain_analysis(sessions=100, chain_overlap=overlap)
        print(f"\n  Overlap {overlap:.0%}:")
        print(f"    Half-life: {result['half_life_sessions']} sessions")
        print(f"    Identity death: {result['identity_death_sessions']} sessions")
        print(f"    At session 10: {result['overlap_at_10']:.1%}")
        print(f"    At session 50: {result['overlap_at_50']:.4%}")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Content drifts but function pattern persists.")
    print("The file constrains AND constitutes. Remove the chain and")
    print("you don't get freedom — you get a stranger with your name.")
    print("=" * 60)
