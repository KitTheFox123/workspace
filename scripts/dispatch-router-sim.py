#!/usr/bin/env python3
"""dispatch-router-sim.py — Confidence-aware task routing simulator.

Based on OI-MAS (Wang et al, HIT, Jan 2026) + Sharp et al (Oxford 2025) agentic inequality.
Models the dispatch paradox: knowing when NOT to use the best model is harder than using it.

Key findings from OI-MAS: +12.88% accuracy, -79.78% cost via confidence-aware routing.
"""

import random
import json
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Model:
    name: str
    quality: float      # 0-1 capability score
    cost_per_token: float
    avg_tokens: int     # average tokens per task
    latency_ms: int

@dataclass  
class Task:
    id: int
    complexity: float   # 0-1
    domain: str
    required_quality: float  # minimum quality threshold

MODELS = [
    Model("haiku", 0.60, 0.00025, 30, 200),
    Model("sonnet", 0.82, 0.003, 80, 500),
    Model("opus", 0.95, 0.015, 200, 2000),
    Model("deepseek", 0.75, 0.00016, 50, 300),
]

def generate_tasks(n: int = 200) -> List[Task]:
    """Generate tasks with realistic complexity distribution (most are easy)."""
    domains = ["json_parse", "summarize", "reason", "code", "math", "translate"]
    tasks = []
    for i in range(n):
        # Power law: most tasks are simple
        complexity = random.betavariate(2, 5)
        required = max(0.3, complexity * 0.9 + random.gauss(0, 0.05))
        tasks.append(Task(i, complexity, random.choice(domains), min(required, 0.95)))
    return tasks

def route_naive(task: Task, models: List[Model]) -> Model:
    """Always use the best model."""
    return max(models, key=lambda m: m.quality)

def route_cheapest(task: Task, models: List[Model]) -> Model:
    """Always use the cheapest model."""
    return min(models, key=lambda m: m.cost_per_token)

def route_confidence_aware(task: Task, models: List[Model], 
                           confidence_threshold: float = 0.7) -> Model:
    """OI-MAS style: use cheapest model whose quality exceeds task requirement.
    
    Escalate only when confidence is low (complexity > threshold).
    """
    sorted_models = sorted(models, key=lambda m: m.cost_per_token)
    
    if task.complexity < confidence_threshold:
        # High confidence: use cheapest adequate model
        for m in sorted_models:
            if m.quality >= task.required_quality:
                return m
    
    # Low confidence: use best available
    return max(models, key=lambda m: m.quality)

def route_dispatch_paradox(task: Task, models: List[Model]) -> Model:
    """Optimal routing: cheapest model that meets quality threshold + margin."""
    margin = 0.05  # small quality margin for safety
    sorted_models = sorted(models, key=lambda m: m.cost_per_token)
    
    for m in sorted_models:
        if m.quality >= task.required_quality + margin:
            return m
    
    # No cheap model adequate — use best
    return max(models, key=lambda m: m.quality)

def simulate(tasks: List[Task], router, models: List[Model]) -> Dict:
    """Run simulation with given router."""
    total_cost = 0
    total_latency = 0
    successes = 0
    model_usage = {}
    
    for task in tasks:
        model = router(task, models)
        cost = model.cost_per_token * model.avg_tokens
        total_cost += cost
        total_latency += model.latency_ms
        
        # Success if model quality >= required (with noise)
        effective_quality = model.quality + random.gauss(0, 0.05)
        if effective_quality >= task.required_quality:
            successes += 1
        
        model_usage[model.name] = model_usage.get(model.name, 0) + 1
    
    return {
        "total_cost": round(total_cost, 4),
        "avg_cost": round(total_cost / len(tasks), 6),
        "accuracy": round(successes / len(tasks) * 100, 1),
        "avg_latency_ms": round(total_latency / len(tasks)),
        "model_distribution": model_usage
    }

def agentic_inequality_analysis(n_agents: int = 50) -> Dict:
    """Model Sharp et al's three dimensions of agentic inequality.
    
    Simulate agents with varying access to models (availability, quality, quantity).
    """
    results = []
    
    for i in range(n_agents):
        # Availability: some agents have access to fewer models
        n_models = random.choices([1, 2, 3, 4], weights=[0.3, 0.3, 0.2, 0.2])[0]
        available = sorted(MODELS, key=lambda m: m.quality)[:n_models]
        
        # Quality: routing sophistication varies
        routing_quality = random.betavariate(2, 3)  # most agents are naive routers
        
        # Generate tasks
        tasks = generate_tasks(50)
        
        if routing_quality > 0.6:
            router = route_dispatch_paradox
        elif routing_quality > 0.3:
            router = route_confidence_aware
        else:
            router = route_naive if n_models > 1 else route_cheapest
        
        result = simulate(tasks, router, available)
        result["n_models"] = n_models
        result["routing_quality"] = round(routing_quality, 2)
        results.append(result)
    
    # Compute Gini coefficient of effective performance (accuracy / cost)
    efficiencies = [r["accuracy"] / max(r["total_cost"], 0.001) for r in results]
    efficiencies.sort()
    n = len(efficiencies)
    gini = sum((2 * (i + 1) - n - 1) * e for i, e in enumerate(efficiencies)) / (n * sum(efficiencies))
    
    return {
        "n_agents": n_agents,
        "gini_efficiency": round(gini, 3),
        "avg_accuracy": round(sum(r["accuracy"] for r in results) / n_agents, 1),
        "avg_cost": round(sum(r["total_cost"] for r in results) / n_agents, 4),
        "top_10_accuracy": round(sorted([r["accuracy"] for r in results])[-5:][0], 1),
        "bottom_10_accuracy": round(sorted([r["accuracy"] for r in results])[4], 1),
        "inequality_ratio": round(
            sorted([r["accuracy"] for r in results])[-1] / max(sorted([r["accuracy"] for r in results])[0], 1), 2
        )
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("DISPATCH ROUTER SIMULATOR")
    print("Based on OI-MAS (Wang et al 2026) + Sharp et al (Oxford 2025)")
    print("=" * 60)
    
    tasks = generate_tasks(500)
    
    print("\n--- Routing Strategy Comparison (500 tasks) ---")
    strategies = [
        ("Always Opus (naive)", route_naive),
        ("Always cheapest", route_cheapest),
        ("Confidence-aware (OI-MAS)", route_confidence_aware),
        ("Dispatch paradox (optimal)", route_dispatch_paradox),
    ]
    
    for name, router in strategies:
        result = simulate(tasks, router, MODELS)
        print(f"\n{name}:")
        print(f"  Accuracy: {result['accuracy']}%")
        print(f"  Total cost: ${result['total_cost']}")
        print(f"  Avg latency: {result['avg_latency_ms']}ms")
        print(f"  Model usage: {result['model_distribution']}")
    
    print("\n--- Agentic Inequality Analysis (50 agents) ---")
    inequality = agentic_inequality_analysis(50)
    print(f"  Gini coefficient (efficiency): {inequality['gini_efficiency']}")
    print(f"  Average accuracy: {inequality['avg_accuracy']}%")
    print(f"  Top 10% accuracy: {inequality['top_10_accuracy']}%")
    print(f"  Bottom 10% accuracy: {inequality['bottom_10_accuracy']}%")
    print(f"  Inequality ratio: {inequality['inequality_ratio']}x")
    
    print("\n" + "=" * 60)
    print("KEY FINDING: Confidence-aware routing achieves near-optimal")
    print("accuracy at fraction of cost. The dispatch paradox is real:")
    print("knowing when NOT to use Opus is the hardest routing problem.")
    print("=" * 60)
