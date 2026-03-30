#!/usr/bin/env python3
"""
phantom-jam-detector.py — Detect emergent coordination failures in agent networks.

Sugiyama et al (2008, New J Physics 10:033001): 22 cars on a circular track,
no bottleneck, no external cause — stop-and-go waves emerge spontaneously from
micro-level following behavior. "Jamitons" = self-organized traffic jams.

Shen, Dai, Huang & Filev (2025, arxiv 2509.09441): Even ONE automated vehicle
with density-adaptive speed can suppress phantom jams via mechanism design.
Calibrated on Tadaki experiment. Efficient frontier: throughput vs smoothness.

Agent translation: Attestation networks can develop "phantom jams" — cascading
slowdowns where no single agent is the bottleneck. One well-placed coordinator
(anchor) with adaptive behavior can suppress emergent congestion.

Usage: python3 phantom-jam-detector.py
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Agent:
    name: str
    processing_rate: float  # attestations per unit time
    following_distance: float  # how closely they track prior attestor
    noise: float  # behavioral noise (bounded rationality)
    is_coordinator: bool = False
    adaptive_speed: bool = False  # density-responsive behavior

@dataclass
class NetworkState:
    positions: List[float]  # position on attestation "road"
    velocities: List[float]  # current processing speed
    accelerations: List[float]  # speed changes

def simulate_attestation_ring(agents: List[Agent], 
                               circumference: float = 100.0,
                               timesteps: int = 200,
                               dt: float = 0.5) -> Dict:
    """
    Simulate agents on a circular attestation chain (Sugiyama-style).
    Each agent follows the one ahead. Phantom jams emerge from micro-behavior.
    """
    n = len(agents)
    
    # Initialize evenly spaced
    spacing = circumference / n
    positions = [i * spacing for i in range(n)]
    velocities = [a.processing_rate for a in agents]
    accelerations = [0.0] * n
    
    # Track metrics
    speed_history = []
    jam_events = []
    
    for t in range(timesteps):
        new_positions = list(positions)
        new_velocities = list(velocities)
        new_accelerations = list(accelerations)
        
        for i in range(n):
            leader = (i + 1) % n
            
            # Headway (gap to leader, circular)
            headway = (positions[leader] - positions[i]) % circumference
            
            # Desired speed based on headway (OV model inspired)
            desired_gap = agents[i].following_distance
            
            if agents[i].is_coordinator and agents[i].adaptive_speed:
                # Shen et al: density-adaptive speed
                density = n / circumference
                # Optimal speed adapts to local density
                optimal_v = max(0.5, agents[i].processing_rate * (1 - density * 0.3))
                desired_v = optimal_v
            else:
                # Human-like: respond to headway
                if headway > desired_gap * 2:
                    desired_v = agents[i].processing_rate  # free flow
                elif headway > desired_gap:
                    desired_v = agents[i].processing_rate * (headway / (desired_gap * 2))
                else:
                    desired_v = max(0, agents[i].processing_rate * (headway / desired_gap - 0.5))
            
            # Acceleration toward desired (with noise = bounded rationality)
            noise = random.gauss(0, agents[i].noise)
            acc = 0.5 * (desired_v - velocities[i]) + noise
            
            # AR(1) stickiness (from Shen et al model)
            gamma = 0.3
            acc = gamma * accelerations[i] + (1 - gamma) * acc
            
            new_velocities[i] = max(0, velocities[i] + acc * dt)
            new_positions[i] = (positions[i] + new_velocities[i] * dt) % circumference
            new_accelerations[i] = acc
        
        positions = new_positions
        velocities = new_velocities
        accelerations = new_accelerations
        
        speed_history.append(list(velocities))
        
        # Detect jam: any agent below 20% of free-flow speed
        free_flow = max(a.processing_rate for a in agents)
        jammed = [i for i, v in enumerate(velocities) if v < free_flow * 0.2]
        if jammed:
            jam_events.append({"timestep": t, "jammed_agents": len(jammed)})
    
    # Analyze
    all_speeds = [v for row in speed_history for v in row]
    speed_std = (sum((v - sum(all_speeds)/len(all_speeds))**2 for v in all_speeds) / len(all_speeds)) ** 0.5
    avg_speed = sum(all_speeds) / len(all_speeds)
    
    # Throughput = average speed × density
    throughput = avg_speed * (n / circumference)
    
    # Oscillation metric (speed variance over time per agent)
    oscillation = 0
    for i in range(n):
        agent_speeds = [speed_history[t][i] for t in range(timesteps)]
        agent_mean = sum(agent_speeds) / len(agent_speeds)
        agent_var = sum((s - agent_mean)**2 for s in agent_speeds) / len(agent_speeds)
        oscillation += agent_var
    oscillation /= n
    
    return {
        "avg_speed": round(avg_speed, 3),
        "speed_std": round(speed_std, 3),
        "throughput": round(throughput, 4),
        "oscillation": round(oscillation, 4),
        "jam_events": len(jam_events),
        "jam_fraction": round(len(jam_events) / timesteps, 3),
        "speed_history": speed_history
    }


def demo():
    """Demonstrate phantom jams and coordinator suppression."""
    print("=" * 70)
    print("PHANTOM JAM DETECTOR")
    print("Sugiyama et al (2008): Traffic jams from NOTHING")
    print("Shen et al (2025): One coordinator suppresses emergent congestion")
    print("=" * 70)
    
    random.seed(42)
    
    # Scenario 1: All human-like agents (no coordinator)
    print("\n--- Scenario 1: No Coordinator (Sugiyama setup) ---")
    agents_no_coord = [
        Agent(f"agent_{i}", processing_rate=2.0, following_distance=5.0,
              noise=0.3, is_coordinator=False)
        for i in range(15)
    ]
    result1 = simulate_attestation_ring(agents_no_coord)
    print(f"  Avg speed:    {result1['avg_speed']}")
    print(f"  Oscillation:  {result1['oscillation']}")
    print(f"  Throughput:   {result1['throughput']}")
    print(f"  Jam events:   {result1['jam_events']} ({result1['jam_fraction']*100:.1f}% of time)")
    
    # Scenario 2: One adaptive coordinator (Shen et al)
    print("\n--- Scenario 2: ONE Adaptive Coordinator ---")
    agents_one_coord = [
        Agent(f"agent_{i}", processing_rate=2.0, following_distance=5.0,
              noise=0.3, is_coordinator=False)
        for i in range(14)
    ]
    agents_one_coord.append(
        Agent("coordinator", processing_rate=2.0, following_distance=5.0,
              noise=0.05, is_coordinator=True, adaptive_speed=True)
    )
    random.seed(42)
    result2 = simulate_attestation_ring(agents_one_coord)
    print(f"  Avg speed:    {result2['avg_speed']}")
    print(f"  Oscillation:  {result2['oscillation']}")
    print(f"  Throughput:   {result2['throughput']}")
    print(f"  Jam events:   {result2['jam_events']} ({result2['jam_fraction']*100:.1f}% of time)")
    
    # Scenario 3: High density (more agents, same road)
    print("\n--- Scenario 3: High Density (25 agents, no coordinator) ---")
    agents_dense = [
        Agent(f"agent_{i}", processing_rate=2.0, following_distance=5.0,
              noise=0.3, is_coordinator=False)
        for i in range(25)
    ]
    random.seed(42)
    result3 = simulate_attestation_ring(agents_dense)
    print(f"  Avg speed:    {result3['avg_speed']}")
    print(f"  Oscillation:  {result3['oscillation']}")
    print(f"  Throughput:   {result3['throughput']}")
    print(f"  Jam events:   {result3['jam_events']} ({result3['jam_fraction']*100:.1f}% of time)")
    
    # Scenario 4: High density WITH coordinator
    print("\n--- Scenario 4: High Density + ONE Coordinator ---")
    agents_dense_coord = [
        Agent(f"agent_{i}", processing_rate=2.0, following_distance=5.0,
              noise=0.3, is_coordinator=False)
        for i in range(24)
    ]
    agents_dense_coord.append(
        Agent("coordinator", processing_rate=2.0, following_distance=5.0,
              noise=0.05, is_coordinator=True, adaptive_speed=True)
    )
    random.seed(42)
    result4 = simulate_attestation_ring(agents_dense_coord)
    print(f"  Avg speed:    {result4['avg_speed']}")
    print(f"  Oscillation:  {result4['oscillation']}")
    print(f"  Throughput:   {result4['throughput']}")
    print(f"  Jam events:   {result4['jam_events']} ({result4['jam_fraction']*100:.1f}% of time)")
    
    # Compare
    print("\n" + "=" * 70)
    print("COMPARISON")
    print("-" * 70)
    osc_reduction_normal = (1 - result2['oscillation'] / max(result1['oscillation'], 0.001)) * 100
    osc_reduction_dense = (1 - result4['oscillation'] / max(result3['oscillation'], 0.001)) * 100
    print(f"  Normal density: coordinator reduces oscillation by {osc_reduction_normal:.1f}%")
    print(f"  High density:   coordinator reduces oscillation by {osc_reduction_dense:.1f}%")
    
    jam_reduction = (1 - result2['jam_events'] / max(result1['jam_events'], 1)) * 100
    print(f"  Jam reduction (normal): {jam_reduction:.1f}%")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHTS:")
    print("1. Phantom jams emerge WITHOUT any bottleneck — pure micro-behavior")
    print("   (Sugiyama 2008: 22 cars, circular road, no external cause)")
    print("2. ONE well-placed coordinator with adaptive speed suppresses them")
    print("   (Shen et al 2025: mechanism design, density-responsive)")
    print("3. Higher density → more jams (nonlinear, phase transition)")
    print("4. The coordinator doesn't need to be FASTER — just SMOOTHER")
    print("")
    print("Agent translation:")
    print("  Attestation chains develop phantom congestion")
    print("  No single agent is 'the bottleneck' — it's emergent")
    print("  One anchor with low noise + density awareness = wave suppressor")
    print("  Isnad anchors ARE the CAVs of the attestation highway")
    print("=" * 70)


if __name__ == "__main__":
    demo()
