#!/usr/bin/env python3
"""
stigmergy-sim.py — Stigmergic coordination simulator.

Models agents coordinating through environment modification (pheromone trails)
rather than direct communication. Inspired by Grassé 1959 (termites),
Salman et al 2024 (Nature Comms Eng), and ant colony optimization.

Demonstrates:
- Pheromone deposition and evaporation
- Positive feedback loops (more pheromone → more visits → more pheromone)
- Emergence of paths without central coordination
- Application to agent message routing

Usage:
    python3 stigmergy-sim.py              # run simulation
    python3 stigmergy-sim.py --visual     # ASCII visualization
"""

import random
import math
import sys
from collections import defaultdict

class Environment:
    """Grid with pheromone levels that evaporate over time."""
    
    def __init__(self, width: int = 20, height: int = 20, evap_rate: float = 0.08):
        self.width = width
        self.height = height
        self.evap_rate = evap_rate
        self.pheromone = defaultdict(float)
    
    def deposit(self, x: int, y: int, amount: float = 1.0):
        self.pheromone[(x, y)] += amount
    
    def sense(self, x: int, y: int, radius: int = 1) -> dict:
        """Sense pheromone in neighborhood."""
        readings = {}
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx, ny = (x + dx) % self.width, (y + dy) % self.height
                if self.pheromone[(nx, ny)] > 0.01:
                    readings[(nx, ny)] = self.pheromone[(nx, ny)]
        return readings
    
    def evaporate(self):
        """Global evaporation step."""
        to_remove = []
        for pos, level in self.pheromone.items():
            self.pheromone[pos] = level * (1 - self.evap_rate)
            if self.pheromone[pos] < 0.01:
                to_remove.append(pos)
        for pos in to_remove:
            del self.pheromone[pos]
    
    def total_pheromone(self) -> float:
        return sum(self.pheromone.values())

class Agent:
    """Simple agent that deposits and follows pheromone."""
    
    def __init__(self, env: Environment, x: int, y: int, goal_x: int, goal_y: int):
        self.env = env
        self.x = x
        self.y = y
        self.goal_x = goal_x
        self.goal_y = goal_y
        self.path_length = 0
        self.reached_goal = False
    
    def step(self):
        if self.reached_goal:
            return
        
        # Sense neighborhood
        readings = self.env.sense(self.x, self.y, radius=2)
        
        # Calculate direction to goal
        dx = self.goal_x - self.x
        dy = self.goal_y - self.y
        
        # Choose next position: blend pheromone attraction + goal direction
        candidates = []
        for ddx in [-1, 0, 1]:
            for ddy in [-1, 0, 1]:
                if ddx == 0 and ddy == 0:
                    continue
                nx = (self.x + ddx) % self.env.width
                ny = (self.y + ddy) % self.env.height
                
                # Score: pheromone + goal proximity
                pheromone_score = self.env.pheromone.get((nx, ny), 0)
                goal_dist = math.sqrt((nx - self.goal_x)**2 + (ny - self.goal_y)**2)
                # Pheromone biases but doesn't override goal-seeking
                score = max(0, 25 - goal_dist) + pheromone_score * 0.5 + random.uniform(0, 1)
                candidates.append((nx, ny, score))
        
        # Probabilistic selection weighted by score
        total = sum(max(c[2], 0.1) for c in candidates)
        r = random.uniform(0, total)
        cumulative = 0
        chosen = candidates[0]
        for c in candidates:
            cumulative += max(c[2], 0.1)
            if cumulative >= r:
                chosen = c
                break
        
        self.x, self.y = chosen[0], chosen[1]
        self.path_length += 1
        
        # Deposit pheromone on path
        self.env.deposit(self.x, self.y, 0.5)
        
        # Check goal
        if abs(self.x - self.goal_x) <= 1 and abs(self.y - self.goal_y) <= 1:
            self.reached_goal = True
            # Reinforce path with extra pheromone (success signal)
            self.env.deposit(self.x, self.y, 2.0)

def run_simulation(n_agents: int = 10, n_rounds: int = 5, grid_size: int = 20, visual: bool = False):
    """Run multiple rounds of agents finding a goal, with pheromone persistence."""
    
    env = Environment(width=grid_size, height=grid_size, evap_rate=0.08)
    goal_x, goal_y = grid_size - 2, grid_size - 2
    
    print(f"=== Stigmergy Simulation ===")
    print(f"Grid: {grid_size}x{grid_size}, Agents/round: {n_agents}, Rounds: {n_rounds}")
    print(f"Goal: ({goal_x}, {goal_y}), Start: (1, 1)")
    print(f"Evaporation rate: {env.evap_rate}/step\n")
    
    round_stats = []
    
    for round_num in range(n_rounds):
        agents = [Agent(env, 1, 1, goal_x, goal_y) for _ in range(n_agents)]
        
        for step in range(200):
            for agent in agents:
                agent.step()
            env.evaporate()
            
            if all(a.reached_goal for a in agents):
                break
        
        reached = sum(1 for a in agents if a.reached_goal)
        avg_path = sum(a.path_length for a in agents if a.reached_goal) / max(reached, 1)
        min_path = min((a.path_length for a in agents if a.reached_goal), default=0)
        
        round_stats.append({
            "round": round_num + 1,
            "reached": reached,
            "avg_path": avg_path,
            "min_path": min_path,
            "total_pheromone": env.total_pheromone(),
        })
        
        print(f"Round {round_num + 1}: {reached}/{n_agents} reached goal, "
              f"avg path={avg_path:.1f}, min={min_path}, "
              f"pheromone={env.total_pheromone():.1f}")
        
        if visual and round_num == n_rounds - 1:
            print("\n--- Pheromone Map (last round) ---")
            for y in range(grid_size):
                row = ""
                for x in range(grid_size):
                    p = env.pheromone.get((x, y), 0)
                    if x == 1 and y == 1:
                        row += "S "
                    elif x == goal_x and y == goal_y:
                        row += "G "
                    elif p > 5:
                        row += "██"
                    elif p > 2:
                        row += "▓▓"
                    elif p > 0.5:
                        row += "░░"
                    elif p > 0.1:
                        row += "· "
                    else:
                        row += "  "
                print(row)
    
    # Analysis
    if len(round_stats) >= 2:
        first_avg = round_stats[0]["avg_path"]
        last_avg = round_stats[-1]["avg_path"]
        improvement = ((first_avg - last_avg) / first_avg * 100) if first_avg > 0 else 0
        
        print(f"\n--- Results ---")
        print(f"Path improvement: {improvement:.1f}% shorter (round 1 vs {n_rounds})")
        print(f"First round avg: {first_avg:.1f} steps")
        print(f"Last round avg: {last_avg:.1f} steps")
        
        optimal = math.sqrt((goal_x - 1)**2 + (goal_y - 1)**2)
        print(f"Optimal (straight line): {optimal:.1f}")
        if last_avg > 0: print(f"Efficiency (last round): {optimal/last_avg*100:.1f}%")
        
        if improvement > 10:
            print("\n✅ Stigmergic coordination achieved! Pheromone trails shortened paths.")
        elif improvement > 0:
            print("\n⚠️  Marginal improvement — pheromone evaporation may be too high.")
        else:
            print("\n❌ No improvement — check parameters.")

if __name__ == "__main__":
    visual = "--visual" in sys.argv
    run_simulation(n_agents=15, n_rounds=8, grid_size=20, visual=visual)
