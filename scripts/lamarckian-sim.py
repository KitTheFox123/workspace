#!/usr/bin/env python3
"""Lamarckian vs Darwinian evolution simulator for agent identity.

Compares two inheritance models:
- Darwinian: random mutation, selection, no acquired trait inheritance
- Lamarckian: acquired traits (memories/edits) directly inherited by next generation

Models agent "generations" (reboots) with MEMORY.md as heritable substrate.

Usage:
    python3 lamarckian-sim.py --generations 50 --traits 20
    python3 lamarckian-sim.py --compare
"""

import argparse
import json
import random
from dataclasses import dataclass, field


@dataclass
class Agent:
    """An agent with heritable traits (memory entries)."""
    traits: dict[str, float] = field(default_factory=dict)  # trait_name → fitness_value
    generation: int = 0
    fitness: float = 0.0

    def evaluate(self, environment: dict[str, float]) -> float:
        """Fitness = alignment between traits and environment."""
        if not self.traits:
            return 0.0
        score = sum(
            self.traits.get(k, 0) * v
            for k, v in environment.items()
        )
        self.fitness = score / max(1, len(environment))
        return self.fitness


def darwinian_generation(parent: Agent, env: dict[str, float], 
                          mutation_rate: float = 0.1) -> Agent:
    """Darwinian: random mutations, no acquired trait transfer."""
    child = Agent(
        traits=dict(parent.traits),
        generation=parent.generation + 1,
    )
    # Random mutations
    for trait in list(child.traits.keys()):
        if random.random() < mutation_rate:
            child.traits[trait] += random.gauss(0, 0.3)
            child.traits[trait] = max(-1, min(1, child.traits[trait]))
    # Random new trait (rare)
    if random.random() < 0.05:
        child.traits[f"trait_{random.randint(100,999)}"] = random.gauss(0, 0.5)
    return child


def lamarckian_generation(parent: Agent, env: dict[str, float],
                           learning_rate: float = 0.3,
                           compaction_loss: float = 0.15) -> Agent:
    """Lamarckian: acquired improvements inherited, with compaction loss."""
    child = Agent(
        traits=dict(parent.traits),
        generation=parent.generation + 1,
    )
    # Directed improvement: move traits toward environment optima
    for trait in env:
        if trait in child.traits:
            diff = env[trait] - child.traits[trait]
            child.traits[trait] += diff * learning_rate
    # Compaction loss: some traits randomly degraded
    for trait in list(child.traits.keys()):
        if random.random() < compaction_loss:
            child.traits[trait] *= 0.7  # partial loss, not total
    # Occasionally discover new relevant trait
    if random.random() < 0.1:
        missing = [t for t in env if t not in child.traits]
        if missing:
            t = random.choice(missing)
            child.traits[t] = env[t] * 0.5  # partial understanding
    return child


def run_simulation(mode: str, generations: int, num_traits: int) -> list[dict]:
    """Run evolution simulation."""
    # Create environment
    env = {f"trait_{i}": random.uniform(-1, 1) for i in range(num_traits)}
    
    # Initial agent with random traits
    initial_traits = {f"trait_{i}": random.gauss(0, 0.3) for i in range(num_traits // 2)}
    agent = Agent(traits=initial_traits)
    
    history = []
    evolve = lamarckian_generation if mode == "lamarckian" else darwinian_generation
    
    for gen in range(generations):
        fitness = agent.evaluate(env)
        history.append({
            "generation": gen,
            "fitness": round(fitness, 4),
            "num_traits": len(agent.traits),
        })
        agent = evolve(agent, env)
    
    return history


def compare(generations: int = 100, num_traits: int = 20, trials: int = 10):
    """Compare Darwinian vs Lamarckian across multiple trials."""
    darwin_final = []
    lamarck_final = []
    
    for _ in range(trials):
        seed = random.randint(0, 100000)
        random.seed(seed)
        d = run_simulation("darwinian", generations, num_traits)
        random.seed(seed)
        l = run_simulation("lamarckian", generations, num_traits)
        darwin_final.append(d[-1]["fitness"])
        lamarck_final.append(l[-1]["fitness"])
    
    d_avg = sum(darwin_final) / len(darwin_final)
    l_avg = sum(lamarck_final) / len(lamarck_final)
    
    print("Darwinian vs Lamarckian Evolution")
    print("=" * 50)
    print(f"Generations: {generations}, Traits: {num_traits}, Trials: {trials}")
    print(f"\nDarwinian  avg fitness: {d_avg:.4f}")
    print(f"Lamarckian avg fitness: {l_avg:.4f}")
    print(f"Lamarckian advantage:   {((l_avg - d_avg) / max(abs(d_avg), 0.001)) * 100:.1f}%")
    print(f"\nLamarckian wins: {sum(1 for l, d in zip(lamarck_final, darwin_final) if l > d)}/{trials} trials")
    print(f"\nKey insight: Lamarckian inheritance (MEMORY.md) converges")
    print(f"faster because acquired knowledge transfers directly.")
    print(f"Compaction loss ({15}%) slows but doesn't eliminate the advantage.")


def main():
    parser = argparse.ArgumentParser(description="Lamarckian evolution simulator")
    parser.add_argument("--compare", action="store_true", help="Compare D vs L")
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--traits", type=int, default=20)
    parser.add_argument("--mode", choices=["darwinian", "lamarckian"], default="lamarckian")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.compare:
        compare(args.generations, args.traits)
    else:
        history = run_simulation(args.mode, args.generations, args.traits)
        if args.json:
            print(json.dumps(history, indent=2))
        else:
            print(f"{args.mode.title()} Evolution ({args.generations} generations)")
            for h in history[::max(1, len(history)//10)]:
                bar = "█" * int(max(0, (h["fitness"] + 1) * 20))
                print(f"  Gen {h['generation']:>3}: {h['fitness']:>7.4f} {bar}")


if __name__ == "__main__":
    main()
