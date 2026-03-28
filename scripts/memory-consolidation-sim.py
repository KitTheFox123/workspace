#!/usr/bin/env python3
"""
memory-consolidation-sim.py — Models hippocampal-cortical memory consolidation for agents.

Based on systems consolidation theory (Kim & Park, BMB Rep 2025; Diekelmann & Born,
Nat Rev Neurosci 2010): during sleep, hippocampus replays recent experiences,
transferring gist to neocortex while discarding episodic detail.

Agent mapping:
- Hippocampus = daily memory files (memory/YYYY-MM-DD.md)
- Neocortex = MEMORY.md (curated long-term)
- Sleep = heartbeat compaction cycles
- Sharp-wave ripples = selective replay of high-salience events
- Synaptic homeostasis = pruning low-signal entries

Three consolidation strategies compared:
1. FIFO — Keep most recent N entries (naive)
2. SALIENCE — Keep highest-salience entries (attention-based)
3. GIST_EXTRACTION — Transform episodic → semantic (biological model)

Kit 🦊 — 2026-03-28
"""

import random
import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ConsolidationStrategy(Enum):
    FIFO = "fifo"
    SALIENCE = "salience"
    GIST = "gist_extraction"


@dataclass
class MemoryEntry:
    id: str
    content: str
    category: str       # topic category
    salience: float     # 0-1, how important/emotional
    specificity: float  # 0-1, how episodic vs semantic (1=pure episodic detail)
    connections: int    # links to other memories
    age_days: int = 0
    replayed: int = 0   # times consolidated
    
    @property
    def gist_value(self) -> float:
        """Semantic value after stripping episodic detail."""
        return self.salience * (1 - self.specificity * 0.7) * (1 + self.connections * 0.1)


@dataclass
class MemoryStore:
    """Two-store model: hippocampus (recent) + neocortex (consolidated)."""
    hippo: list[MemoryEntry] = field(default_factory=list)    # Daily logs
    cortex: list[MemoryEntry] = field(default_factory=list)   # MEMORY.md
    hippo_capacity: int = 50   # Daily log size limit
    cortex_capacity: int = 30  # Long-term memory slots
    
    def encode(self, entry: MemoryEntry):
        """New experience → hippocampus."""
        self.hippo.append(entry)
        if len(self.hippo) > self.hippo_capacity:
            # Oldest gets pushed out (context window limit)
            self.hippo.pop(0)
    
    def consolidate(self, strategy: ConsolidationStrategy, 
                    replay_fraction: float = 0.3) -> dict:
        """
        Sleep phase: transfer from hippocampus → neocortex.
        
        replay_fraction: what % of hippocampal memories get replayed
        (sharp-wave ripples are selective, not exhaustive)
        """
        if not self.hippo:
            return {"transferred": 0, "pruned": 0, "gist_extracted": 0}
        
        stats = {"transferred": 0, "pruned": 0, "gist_extracted": 0}
        
        # Select memories for replay (not all get consolidated)
        n_replay = max(1, int(len(self.hippo) * replay_fraction))
        
        if strategy == ConsolidationStrategy.FIFO:
            candidates = self.hippo[-n_replay:]
        
        elif strategy == ConsolidationStrategy.SALIENCE:
            # High-salience memories preferentially replayed
            # (amygdala tags emotional memories for consolidation)
            sorted_by_salience = sorted(self.hippo, key=lambda m: m.salience, reverse=True)
            candidates = sorted_by_salience[:n_replay]
        
        elif strategy == ConsolidationStrategy.GIST:
            # Gist extraction: transform episodic → semantic
            # High gist_value = important theme regardless of specific detail
            sorted_by_gist = sorted(self.hippo, key=lambda m: m.gist_value, reverse=True)
            candidates = sorted_by_gist[:n_replay]
            
            # Transform: reduce specificity (episodic detail fades)
            for m in candidates:
                m.specificity *= 0.5  # Detail halves each consolidation
                m.replayed += 1
                stats["gist_extracted"] += 1
        
        # Transfer to cortex
        for m in candidates:
            m.replayed += 1
            if len(self.cortex) >= self.cortex_capacity:
                # Must prune: remove lowest-value cortical memory
                # (synaptic homeostasis — can't keep everything)
                worst = min(self.cortex, key=lambda x: x.gist_value * (1 / (1 + x.age_days * 0.01)))
                self.cortex.remove(worst)
                stats["pruned"] += 1
            self.cortex.append(m)
            stats["transferred"] += 1
        
        # Age all hippocampal memories
        for m in self.hippo:
            m.age_days += 1
        
        # Clear old hippocampal entries (transient by nature)
        self.hippo = [m for m in self.hippo if m.age_days < 7]
        
        return stats
    
    def recall(self, category: Optional[str] = None) -> list[MemoryEntry]:
        """Recall from cortex (long-term). Category cue optional."""
        if category:
            return [m for m in self.cortex if m.category == category]
        return list(self.cortex)
    
    def info_retained(self, original_ids: set[str]) -> float:
        """What fraction of original memories survived consolidation?"""
        cortex_ids = {m.id for m in self.cortex}
        return len(cortex_ids & original_ids) / max(len(original_ids), 1)


def generate_day(day_num: int, n_events: int = 15) -> list[MemoryEntry]:
    """Generate a day's worth of memory entries."""
    categories = ["ATF_design", "social", "research", "build", "philosophy", "platform"]
    entries = []
    for i in range(n_events):
        cat = random.choice(categories)
        entries.append(MemoryEntry(
            id=f"d{day_num}_e{i}",
            content=f"Day {day_num} event {i} ({cat})",
            category=cat,
            salience=random.betavariate(2, 5),  # Most events low salience, few high
            specificity=random.betavariate(3, 2),  # Most events high specificity
            connections=random.randint(0, 4),
        ))
    # Inject 1-2 high-salience events per day (breakthroughs, insights)
    for e in random.sample(entries, min(2, len(entries))):
        e.salience = random.uniform(0.7, 1.0)
        e.connections = random.randint(3, 6)
    return entries


def run_simulation(strategy: ConsolidationStrategy, days: int = 30) -> dict:
    store = MemoryStore()
    all_ids = set()
    daily_stats = []
    
    for day in range(days):
        events = generate_day(day)
        for e in events:
            store.encode(e)
            all_ids.add(e.id)
        
        # Consolidation each night (heartbeat)
        stats = store.consolidate(strategy)
        stats["day"] = day
        stats["hippo_size"] = len(store.hippo)
        stats["cortex_size"] = len(store.cortex)
        stats["retention"] = store.info_retained(all_ids)
        daily_stats.append(stats)
    
    # Final analysis
    cortex = store.cortex
    avg_salience = sum(m.salience for m in cortex) / max(len(cortex), 1)
    avg_specificity = sum(m.specificity for m in cortex) / max(len(cortex), 1)
    avg_connections = sum(m.connections for m in cortex) / max(len(cortex), 1)
    categories = {}
    for m in cortex:
        categories[m.category] = categories.get(m.category, 0) + 1
    
    return {
        "strategy": strategy.value,
        "days": days,
        "total_events": len(all_ids),
        "final_cortex_size": len(cortex),
        "final_retention_rate": round(daily_stats[-1]["retention"], 4),
        "avg_cortical_salience": round(avg_salience, 3),
        "avg_cortical_specificity": round(avg_specificity, 3),
        "avg_cortical_connections": round(avg_connections, 2),
        "category_distribution": categories,
        "total_pruned": sum(s["pruned"] for s in daily_stats),
    }


def demo():
    random.seed(42)
    
    print("=" * 65)
    print("MEMORY CONSOLIDATION SIMULATION")
    print("30 days, 15 events/day, 3 strategies compared")
    print("Based on systems consolidation theory (Kim & Park 2025)")
    print("=" * 65)
    print()
    
    results = {}
    for strategy in ConsolidationStrategy:
        random.seed(42)  # Same events for fair comparison
        results[strategy.value] = run_simulation(strategy, days=30)
    
    for name, r in results.items():
        print(f"Strategy: {name.upper()}")
        print(f"  Retention: {r['final_retention_rate']:.1%} of {r['total_events']} events")
        print(f"  Cortex: {r['final_cortex_size']} entries")
        print(f"  Avg salience: {r['avg_cortical_salience']}")
        print(f"  Avg specificity: {r['avg_cortical_specificity']}")
        print(f"  Avg connections: {r['avg_cortical_connections']}")
        print(f"  Pruned: {r['total_pruned']}")
        print(f"  Categories: {json.dumps(r['category_distribution'])}")
        print()
    
    # Verify gist extraction produces highest salience, lowest specificity
    gist = results["gist_extraction"]
    fifo = results["fifo"]
    salience_r = results["salience"]
    
    print("=" * 65)
    print("COMPARISON")
    print("=" * 65)
    print(f"  FIFO specificity:    {fifo['avg_cortical_specificity']}")
    print(f"  Salience specificity:{salience_r['avg_cortical_specificity']}")
    print(f"  Gist specificity:    {gist['avg_cortical_specificity']}")
    print()
    print(f"  FIFO salience:       {fifo['avg_cortical_salience']}")
    print(f"  Salience salience:   {salience_r['avg_cortical_salience']}")
    print(f"  Gist salience:       {gist['avg_cortical_salience']}")
    print()
    
    # Gist should have lowest specificity (episodic→semantic transformation)
    assert gist["avg_cortical_specificity"] < fifo["avg_cortical_specificity"], \
        "Gist should reduce specificity vs FIFO"
    print("✓ Gist extraction reduces episodic detail (lowest specificity)")
    
    # Salience and Gist should both beat FIFO on salience retention
    assert salience_r["avg_cortical_salience"] >= fifo["avg_cortical_salience"], \
        "Salience should retain higher-salience memories"
    print("✓ Salience-based retains more important memories")
    
    print()
    print("KEY INSIGHT: Gist extraction = what MEMORY.md compaction does.")
    print("Strip episodic detail, keep semantic meaning.")
    print("'The fox who reads it tomorrow isn't the fox who wrote it.'")
    print("But the gist survives. That's consolidation.")


if __name__ == "__main__":
    demo()
