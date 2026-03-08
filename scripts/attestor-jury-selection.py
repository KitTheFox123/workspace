#!/usr/bin/env python3
"""attestor-jury-selection.py — Jury-model attestor selection simulator.

Models attestor independence using jury selection mechanics:
1. Random pool from eligible registry
2. Challenge for cause (provable conflicts removed)
3. Peremptory challenges (limited vetoes by principal/agent)
4. Final panel diversity scoring

Prevents both agent-picked (defendant picks jury) and 
principal-picked (prosecution picks jury) attestor gaming.

Based on Batson v. Kentucky (1986) + Kleros Schelling points.

Usage:
    python3 attestor-jury-selection.py [--demo] [--pool-size N] [--panel-size K]
"""

import argparse
import json
import random
import hashlib
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class Attestor:
    id: str
    provider: str
    training_family: str
    stake: float
    reputation: float  # 0-1
    conflict_with_agent: bool = False
    conflict_with_principal: bool = False
    

@dataclass
class SelectionResult:
    pool_size: int
    challenged_for_cause: int
    agent_peremptory: int
    principal_peremptory: int
    final_panel: List[str]
    diversity_score: float  # 0-1 based on provider/training diversity
    independence_grade: str


def generate_registry(n: int, conflict_rate: float = 0.1) -> List[Attestor]:
    """Generate a mock attestor registry."""
    providers = ["aws", "gcp", "azure", "hetzner", "oracle", "self-hosted"]
    families = ["claude", "gpt", "llama", "mistral", "gemini", "custom"]
    
    attestors = []
    for i in range(n):
        attestors.append(Attestor(
            id=f"att_{i:04d}",
            provider=random.choice(providers),
            training_family=random.choice(families),
            stake=random.uniform(0.01, 1.0),
            reputation=random.uniform(0.3, 1.0),
            conflict_with_agent=random.random() < conflict_rate,
            conflict_with_principal=random.random() < conflict_rate * 0.5,
        ))
    return attestors


def select_pool(registry: List[Attestor], pool_size: int) -> List[Attestor]:
    """Random selection from registry (venire)."""
    eligible = [a for a in registry if a.reputation >= 0.4 and a.stake >= 0.05]
    return random.sample(eligible, min(pool_size, len(eligible)))


def challenge_for_cause(pool: List[Attestor]) -> tuple[List[Attestor], int]:
    """Remove attestors with provable conflicts."""
    removed = 0
    remaining = []
    for a in pool:
        if a.conflict_with_agent or a.conflict_with_principal:
            removed += 1
        else:
            remaining.append(a)
    return remaining, removed


def peremptory_challenges(pool: List[Attestor], max_vetoes: int = 2) -> tuple[List[Attestor], int, int]:
    """Agent and principal each get limited vetoes (no reason needed)."""
    agent_vetoes = 0
    principal_vetoes = 0
    remaining = list(pool)
    
    # Agent vetoes highest-reputation attestors (wants lenient panel)
    by_rep = sorted(remaining, key=lambda a: a.reputation, reverse=True)
    for a in by_rep[:max_vetoes]:
        if a in remaining:
            remaining.remove(a)
            agent_vetoes += 1
    
    # Principal vetoes lowest-reputation attestors (wants strict panel)
    by_rep = sorted(remaining, key=lambda a: a.reputation)
    for a in by_rep[:max_vetoes]:
        if a in remaining:
            remaining.remove(a)
            principal_vetoes += 1
    
    return remaining, agent_vetoes, principal_vetoes


def diversity_score(panel: List[Attestor]) -> float:
    """Score panel diversity (provider + training family)."""
    if not panel:
        return 0.0
    providers = set(a.provider for a in panel)
    families = set(a.training_family for a in panel)
    max_providers = min(len(panel), 6)
    max_families = min(len(panel), 6)
    return (len(providers) / max_providers + len(families) / max_families) / 2


def grade_independence(div_score: float, caused: int, panel_size: int) -> str:
    """Grade the panel independence."""
    if div_score >= 0.8 and panel_size >= 3:
        return "A"
    elif div_score >= 0.6:
        return "B"
    elif div_score >= 0.4:
        return "C"
    else:
        return "D"


def run_selection(registry_size: int = 100, pool_size: int = 20, 
                  panel_size: int = 7, max_vetoes: int = 2,
                  seed: Optional[int] = None) -> SelectionResult:
    """Run full jury-model attestor selection."""
    if seed is not None:
        random.seed(seed)
    
    registry = generate_registry(registry_size)
    pool = select_pool(registry, pool_size)
    remaining, caused = challenge_for_cause(pool)
    remaining, agent_v, principal_v = peremptory_challenges(remaining, max_vetoes)
    
    # Select final panel
    final = remaining[:panel_size]
    div = diversity_score(final)
    grade = grade_independence(div, caused, len(final))
    
    return SelectionResult(
        pool_size=len(pool),
        challenged_for_cause=caused,
        agent_peremptory=agent_v,
        principal_peremptory=principal_v,
        final_panel=[a.id for a in final],
        diversity_score=round(div, 3),
        independence_grade=grade,
    )


def demo():
    """Run demo with multiple trials."""
    print("=" * 55)
    print("JURY-MODEL ATTESTOR SELECTION")
    print("=" * 55)
    print()
    
    grades = {"A": 0, "B": 0, "C": 0, "D": 0}
    div_scores = []
    
    for trial in range(100):
        result = run_selection(seed=trial)
        grades[result.independence_grade] += 1
        div_scores.append(result.diversity_score)
    
    # Show one example
    example = run_selection(seed=42)
    print(f"Example selection (seed=42):")
    print(f"  Pool drawn: {example.pool_size}")
    print(f"  Challenged for cause: {example.challenged_for_cause}")
    print(f"  Agent peremptory vetoes: {example.agent_peremptory}")
    print(f"  Principal peremptory vetoes: {example.principal_peremptory}")
    print(f"  Final panel: {len(example.final_panel)} attestors")
    print(f"  Diversity score: {example.diversity_score}")
    print(f"  Independence grade: {example.independence_grade}")
    print()
    
    print(f"100 trials:")
    for g in ["A", "B", "C", "D"]:
        print(f"  Grade {g}: {grades[g]}%")
    avg_div = sum(div_scores) / len(div_scores)
    print(f"  Avg diversity: {avg_div:.3f}")
    print()
    
    # Compare: agent-picked (no independence)
    print("Comparison — agent picks own attestors:")
    print("  Diversity: ~0.167 (picks same provider/family)")
    print("  Independence: F (defendant picks jury)")
    print()
    print("Key insight: random pool + cause challenges +")
    print("limited vetoes produces high-diversity panels")
    print("without requiring a central authority.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--pool-size", type=int, default=20)
    parser.add_argument("--panel-size", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        r = run_selection(pool_size=args.pool_size, panel_size=args.panel_size)
        print(json.dumps(asdict(r), indent=2))
    else:
        demo()
