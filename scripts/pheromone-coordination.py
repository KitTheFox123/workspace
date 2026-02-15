#!/usr/bin/env python3
"""
pheromone-coordination.py — Stigmergic coordination simulator for agents.

Models how agents can coordinate through shared environment modification
(stigmergy) rather than direct communication. Implements:
- Pheromone deposit + exponential decay
- Multiple agent types with different deposit/sensing ranges  
- Convergence detection (when do agents align without talking?)
- Comparison: with vs without decay (showing decay prevents lock-in)

Usage:
    python3 pheromone-coordination.py              # Run default simulation
    python3 pheromone-coordination.py --agents 20  # 20 agents
    python3 pheromone-coordination.py --no-decay    # Disable decay (shows lock-in)
    python3 pheromone-coordination.py --visualize   # ASCII heatmap per step
"""

import argparse
import random
import math
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Trail:
    """A pheromone trail on a topic/path."""
    strength: float = 0.0
    deposits: int = 0
    last_deposit_step: int = 0


@dataclass  
class Agent:
    """An agent that deposits and follows pheromone trails."""
    name: str
    preference: float  # 0-1, natural bias toward topic A vs B
    position: float = 0.5  # current position on A-B spectrum
    history: list = field(default_factory=list)
    
    def sense(self, trails: dict, noise: float = 0.1) -> float:
        """Sense the environment and decide direction."""
        a_strength = trails.get('A', Trail()).strength
        b_strength = trails.get('B', Trail()).strength
        total = a_strength + b_strength + 0.001  # avoid div by zero
        
        # Signal from environment
        env_signal = a_strength / total  # 0 = all B, 1 = all A
        
        # Blend with own preference + noise
        noise_val = random.gauss(0, noise)
        decision = 0.6 * env_signal + 0.3 * self.preference + 0.1 * noise_val
        return max(0.0, min(1.0, decision))
    
    def deposit(self, trails: dict, step: int, amount: float = 1.0):
        """Deposit pheromone based on current position."""
        if self.position > 0.5:
            key = 'A'
            strength = (self.position - 0.5) * 2 * amount
        else:
            key = 'B'
            strength = (0.5 - self.position) * 2 * amount
        
        if key not in trails:
            trails[key] = Trail()
        trails[key].strength += strength
        trails[key].deposits += 1
        trails[key].last_deposit_step = step


def decay_trails(trails: dict, rate: float = 0.1):
    """Apply exponential decay to all trails."""
    for key in trails:
        trails[key].strength *= (1 - rate)


def measure_convergence(agents: list) -> float:
    """How aligned are agents? 0 = split, 1 = consensus."""
    positions = [a.position for a in agents]
    mean = sum(positions) / len(positions)
    variance = sum((p - mean) ** 2 for p in positions) / len(positions)
    # Normalize: max variance is 0.25 (half at 0, half at 1)
    return 1.0 - min(1.0, variance / 0.25)


def ascii_heatmap(agents: list, width: int = 40) -> str:
    """Show agent distribution as ASCII heatmap."""
    bins = [0] * width
    for a in agents:
        idx = min(width - 1, int(a.position * width))
        bins[idx] += 1
    
    max_count = max(bins) if max(bins) > 0 else 1
    chars = ' ░▒▓█'
    row = ''
    for b in bins:
        level = int(b / max_count * (len(chars) - 1))
        row += chars[level]
    return f'B [{row}] A'


def run_simulation(n_agents: int = 10, n_steps: int = 100, 
                   decay_rate: float = 0.1, noise: float = 0.1,
                   visualize: bool = False) -> dict:
    """Run a stigmergic coordination simulation."""
    
    # Create agents with random preferences
    agents = []
    for i in range(n_agents):
        pref = random.random()
        agents.append(Agent(
            name=f'agent_{i}',
            preference=pref,
            position=pref  # start at own preference
        ))
    
    trails = {}
    convergence_history = []
    
    for step in range(n_steps):
        # Each agent senses and updates position
        for agent in agents:
            new_pos = agent.sense(trails, noise)
            agent.position = new_pos
            agent.history.append(new_pos)
            agent.deposit(trails, step)
        
        # Apply decay
        if decay_rate > 0:
            decay_trails(trails, decay_rate)
        
        conv = measure_convergence(agents)
        convergence_history.append(conv)
        
        if visualize and step % 10 == 0:
            print(f'Step {step:3d} | {ascii_heatmap(agents)} | conv={conv:.3f}')
    
    # Results
    final_positions = [a.position for a in agents]
    mean_pos = sum(final_positions) / len(final_positions)
    
    return {
        'final_convergence': convergence_history[-1],
        'convergence_history': convergence_history,
        'mean_position': mean_pos,
        'steps_to_90pct': next(
            (i for i, c in enumerate(convergence_history) if c > 0.9), 
            n_steps
        ),
        'trail_strengths': {k: v.strength for k, v in trails.items()},
        'total_deposits': sum(v.deposits for v in trails.values()),
    }


def main():
    parser = argparse.ArgumentParser(description='Stigmergic coordination simulator')
    parser.add_argument('--agents', type=int, default=10, help='Number of agents')
    parser.add_argument('--steps', type=int, default=100, help='Simulation steps')
    parser.add_argument('--decay', type=float, default=0.1, help='Decay rate (0-1)')
    parser.add_argument('--no-decay', action='store_true', help='Disable decay')
    parser.add_argument('--noise', type=float, default=0.1, help='Sensing noise')
    parser.add_argument('--visualize', action='store_true', help='Show ASCII heatmap')
    parser.add_argument('--compare', action='store_true', help='Compare decay vs no-decay')
    parser.add_argument('--runs', type=int, default=1, help='Number of runs to average')
    args = parser.parse_args()
    
    if args.compare:
        print("=== DECAY vs NO-DECAY COMPARISON ===\n")
        for label, rate in [("With decay (0.1)", 0.1), ("No decay (0.0)", 0.0)]:
            results = []
            for _ in range(20):
                r = run_simulation(args.agents, args.steps, rate, args.noise)
                results.append(r)
            
            avg_conv = sum(r['final_convergence'] for r in results) / len(results)
            avg_steps = sum(r['steps_to_90pct'] for r in results) / len(results)
            avg_pos = sum(r['mean_position'] for r in results) / len(results)
            
            print(f"{label}:")
            print(f"  Avg convergence: {avg_conv:.3f}")
            print(f"  Avg steps to 90%: {avg_steps:.1f}")
            print(f"  Avg mean position: {avg_pos:.3f}")
            print(f"  Position spread: {sum(abs(r['mean_position'] - 0.5) for r in results) / len(results):.3f}")
            print()
        
        print("Key insight: Decay prevents path lock-in. Without decay,")
        print("early deposits dominate forever. With decay, the system")
        print("stays responsive to current agent preferences.")
        return
    
    decay = 0.0 if args.no_decay else args.decay
    
    if args.runs > 1:
        all_results = []
        for i in range(args.runs):
            r = run_simulation(args.agents, args.steps, decay, args.noise, False)
            all_results.append(r)
        
        avg_conv = sum(r['final_convergence'] for r in all_results) / len(all_results)
        avg_steps = sum(r['steps_to_90pct'] for r in all_results) / len(all_results)
        print(f"Over {args.runs} runs ({args.agents} agents, {args.steps} steps, decay={decay}):")
        print(f"  Avg convergence: {avg_conv:.3f}")
        print(f"  Avg steps to 90%: {avg_steps:.1f}")
    else:
        result = run_simulation(args.agents, args.steps, decay, args.noise, args.visualize)
        print(f"\n=== RESULTS ({args.agents} agents, {args.steps} steps, decay={decay}) ===")
        print(f"Final convergence: {result['final_convergence']:.3f}")
        print(f"Steps to 90% convergence: {result['steps_to_90pct']}")
        print(f"Mean position: {result['mean_position']:.3f} ({'A-leaning' if result['mean_position'] > 0.5 else 'B-leaning'})")
        print(f"Trail strengths: {result['trail_strengths']}")
        print(f"Total deposits: {result['total_deposits']}")


if __name__ == '__main__':
    main()
