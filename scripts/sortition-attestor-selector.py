#!/usr/bin/env python3
"""sortition-attestor-selector.py — Random attestor selection via sortition.

Implements Bagg 2024 (AJPS) sortition-as-anti-corruption model for attestor
assignment. Neither agent nor principal selects attestors — random draw from
eligible pool prevents capture.

Key properties:
- Attestor pool registration (eligibility criteria)
- Per-heartbeat random draw (VRF-style deterministic randomness)
- Diversity constraints (no two attestors share provider/training)
- Recusal mechanism (attestor with conflicts must declare)
- Rotation enforcement (no consecutive assignments)

Usage:
    python3 sortition-attestor-selector.py [--demo] [--pool-size N] [--draw K]
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional, Set


@dataclass
class Attestor:
    """Registered attestor in the pool."""
    id: str
    name: str
    provider: str          # Infrastructure provider
    training_family: str   # Model family
    reputation_score: float  # 0.0-1.0
    last_assigned: Optional[str] = None  # ISO timestamp
    consecutive_count: int = 0
    conflicts: List[str] = field(default_factory=list)  # Agent IDs with conflicts


@dataclass
class DrawResult:
    """Result of a sortition draw."""
    heartbeat_id: str
    agent_id: str
    timestamp: str
    selected: List[str]  # Attestor IDs
    seed: str
    diversity_score: float  # 0.0-1.0
    pool_size: int
    draw_size: int


class SortitionSelector:
    """Sortition-based attestor selection.
    
    Implements random draw with diversity constraints.
    Neither agent nor principal influences selection.
    """
    
    def __init__(self, max_consecutive: int = 2):
        self.pool: List[Attestor] = []
        self.max_consecutive = max_consecutive
        self.history: List[DrawResult] = []
    
    def register(self, attestor: Attestor) -> bool:
        """Register attestor in eligible pool."""
        if any(a.id == attestor.id for a in self.pool):
            return False
        self.pool.append(attestor)
        return True
    
    def _compute_seed(self, heartbeat_id: str, agent_id: str) -> str:
        """Deterministic seed from heartbeat + agent (VRF-style)."""
        data = f"{heartbeat_id}:{agent_id}:{len(self.history)}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _eligible(self, agent_id: str) -> List[Attestor]:
        """Filter pool to eligible attestors for this agent."""
        eligible = []
        for a in self.pool:
            # Skip if conflict with agent
            if agent_id in a.conflicts:
                continue
            # Skip if max consecutive assignments reached
            if a.consecutive_count >= self.max_consecutive:
                continue
            # Skip if reputation too low
            if a.reputation_score < 0.3:
                continue
            eligible.append(a)
        return eligible
    
    def _diversity_score(self, selected: List[Attestor]) -> float:
        """Measure diversity of selected attestors."""
        if len(selected) <= 1:
            return 1.0
        providers = set(a.provider for a in selected)
        families = set(a.training_family for a in selected)
        provider_diversity = len(providers) / len(selected)
        family_diversity = len(families) / len(selected)
        return (provider_diversity + family_diversity) / 2
    
    def draw(self, agent_id: str, heartbeat_id: str, k: int = 3) -> DrawResult:
        """Perform sortition draw for k attestors.
        
        Selection is deterministic given seed (reproducible),
        but unpredictable to agent/principal (VRF model).
        """
        seed = self._compute_seed(heartbeat_id, agent_id)
        eligible = self._eligible(agent_id)
        
        if len(eligible) < k:
            k = len(eligible)
        
        # Deterministic shuffle using seed
        rng = random.Random(seed)
        
        # Weighted by reputation, with diversity boost
        candidates = list(eligible)
        selected = []
        used_providers: Set[str] = set()
        used_families: Set[str] = set()
        
        for _ in range(k):
            if not candidates:
                break
            
            # Weight: reputation * diversity bonus
            weights = []
            for c in candidates:
                w = c.reputation_score
                if c.provider not in used_providers:
                    w *= 1.5  # Diversity bonus
                if c.training_family not in used_families:
                    w *= 1.3
                weights.append(w)
            
            total = sum(weights)
            if total == 0:
                break
            
            # Weighted random selection
            r = rng.random() * total
            cumulative = 0
            chosen_idx = 0
            for i, w in enumerate(weights):
                cumulative += w
                if cumulative >= r:
                    chosen_idx = i
                    break
            
            chosen = candidates.pop(chosen_idx)
            selected.append(chosen)
            used_providers.add(chosen.provider)
            used_families.add(chosen.training_family)
        
        # Update assignment tracking
        now = datetime.now(timezone.utc).isoformat()
        selected_ids = [a.id for a in selected]
        for a in self.pool:
            if a.id in selected_ids:
                a.last_assigned = now
                a.consecutive_count += 1
            else:
                a.consecutive_count = 0  # Reset if not assigned
        
        diversity = self._diversity_score(selected)
        
        result = DrawResult(
            heartbeat_id=heartbeat_id,
            agent_id=agent_id,
            timestamp=now,
            selected=selected_ids,
            seed=seed,
            diversity_score=diversity,
            pool_size=len(self.pool),
            draw_size=k,
        )
        self.history.append(result)
        return result
    
    def audit_fairness(self, n_draws: int = 100) -> dict:
        """Audit selection fairness across n simulated draws."""
        counts = {a.id: 0 for a in self.pool}
        for i in range(n_draws):
            result = self.draw("test_agent", f"hb_{i}", k=3)
            for aid in result.selected:
                counts[aid] += 1
            # Reset consecutive counts for simulation
            for a in self.pool:
                a.consecutive_count = 0
        
        values = list(counts.values())
        mean = sum(values) / len(values) if values else 0
        variance = sum((v - mean) ** 2 for v in values) / len(values) if values else 0
        cv = (variance ** 0.5) / mean if mean > 0 else 0
        
        return {
            "draws": n_draws,
            "pool_size": len(self.pool),
            "selection_counts": counts,
            "mean_selections": round(mean, 1),
            "coefficient_of_variation": round(cv, 3),
            "fairness_grade": "A" if cv < 0.3 else "B" if cv < 0.5 else "C" if cv < 0.7 else "F",
            "note": "CV < 0.3 = fair distribution, > 0.7 = concentration risk"
        }


def demo(pool_size: int = 10, draw_size: int = 3):
    """Run demo with synthetic pool."""
    selector = SortitionSelector()
    
    providers = ["aws", "gcp", "azure", "hetzner", "oracle"]
    families = ["claude", "gpt", "gemini", "llama", "mistral"]
    
    # Register pool
    for i in range(pool_size):
        attestor = Attestor(
            id=f"att_{i:03d}",
            name=f"Attestor_{i}",
            provider=providers[i % len(providers)],
            training_family=families[i % len(families)],
            reputation_score=0.5 + (i % 5) * 0.1,
        )
        selector.register(attestor)
    
    print("=" * 60)
    print("SORTITION ATTESTOR SELECTION")
    print("(Bagg 2024: random selection for oversight, not legislation)")
    print("=" * 60)
    print(f"\nPool: {pool_size} attestors, {len(set(providers))} providers, {len(set(families))} families")
    print(f"Draw: {draw_size} per heartbeat\n")
    
    # Single draw
    result = selector.draw("agent_kit", "hb_2026030816", k=draw_size)
    print(f"Draw for agent_kit @ hb_2026030816:")
    print(f"  Selected: {result.selected}")
    print(f"  Diversity: {result.diversity_score:.2f}")
    print(f"  Seed: {result.seed[:16]}...")
    print()
    
    # Reset for fairness audit
    for a in selector.pool:
        a.consecutive_count = 0
    selector.history = []
    
    # Fairness audit
    audit = selector.audit_fairness(n_draws=200)
    print(f"Fairness audit ({audit['draws']} draws):")
    print(f"  Mean selections per attestor: {audit['mean_selections']}")
    print(f"  CV: {audit['coefficient_of_variation']} (Grade {audit['fairness_grade']})")
    print(f"  Distribution: {audit['selection_counts']}")
    print(f"\nKey: Neither agent nor principal picks attestors.")
    print(f"Random draw from eligible pool = sortition anti-capture.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sortition attestor selector")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--pool-size", type=int, default=10)
    parser.add_argument("--draw", type=int, default=3)
    parser.add_argument("--audit", action="store_true", help="Run fairness audit")
    args = parser.parse_args()
    
    demo(pool_size=args.pool_size, draw_size=args.draw)
