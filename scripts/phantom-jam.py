#!/usr/bin/env python3
"""
Nagel-Schreckenberg traffic model — phantom jam simulator.

Demonstrates how traffic jams emerge from nothing: no bottleneck,
no accident, just individual braking decisions propagating backward.

Based on Nagel & Schreckenberg 1992 + Sugiyama et al. 2008 experiment
(22 cars on a 230m circular track → spontaneous stop-and-go waves).

Usage:
  python3 phantom-jam.py              # Run simulation, show stats
  python3 phantom-jam.py --animate    # ASCII animation in terminal
  python3 phantom-jam.py --density 0.3 --steps 200
"""
import argparse
import random
import time
import sys

def nagel_schreckenberg(road_length=200, n_cars=60, v_max=5, p_slow=0.3, steps=300, seed=None):
    """
    Run NaSch cellular automaton.
    
    Returns list of (positions, velocities) per timestep.
    """
    if seed is not None:
        random.seed(seed)
    
    # Initialize: place cars randomly
    positions = sorted(random.sample(range(road_length), n_cars))
    velocities = [random.randint(0, v_max) for _ in range(n_cars)]
    
    history = []
    
    for step in range(steps):
        history.append((list(positions), list(velocities)))
        
        # Calculate gaps
        gaps = []
        for i in range(n_cars):
            next_car = positions[(i + 1) % n_cars]
            gap = (next_car - positions[i] - 1) % road_length
            gaps.append(gap)
        
        new_velocities = list(velocities)
        new_positions = list(positions)
        
        for i in range(n_cars):
            # Step 1: Acceleration
            new_velocities[i] = min(velocities[i] + 1, v_max)
            
            # Step 2: Braking (don't hit car ahead)
            new_velocities[i] = min(new_velocities[i], gaps[i])
            
            # Step 3: Randomization (the key ingredient!)
            if new_velocities[i] > 0 and random.random() < p_slow:
                new_velocities[i] -= 1
            
            # Step 4: Movement
            new_positions[i] = (positions[i] + new_velocities[i]) % road_length
        
        positions = new_positions
        velocities = new_velocities
    
    return history


def detect_jams(history, road_length, threshold_v=1):
    """Detect phantom jams: clusters of slow cars that persist."""
    jam_events = []
    for step, (positions, velocities) in enumerate(history):
        slow_cars = sum(1 for v in velocities if v <= threshold_v)
        if slow_cars > len(velocities) * 0.3:  # >30% slow = jam
            jam_events.append(step)
    return jam_events


def compute_flow(history, road_length):
    """Compute flow (cars passing a point per timestep)."""
    flows = []
    for positions, velocities in history:
        flows.append(sum(velocities) / road_length)
    return flows


def animate(history, road_length, delay=0.08):
    """ASCII animation of the road."""
    for step, (positions, velocities) in enumerate(history):
        road = ['.'] * road_length
        for p, v in zip(positions, velocities):
            if v == 0:
                road[p] = '█'  # stopped
            elif v <= 2:
                road[p] = '▓'  # slow
            else:
                road[p] = '░'  # fast
        
        # Show 80-char window
        display = ''.join(road[:80])
        sys.stdout.write(f'\r t={step:3d} |{display}|')
        sys.stdout.flush()
        time.sleep(delay)
    print()


def main():
    parser = argparse.ArgumentParser(description='Phantom traffic jam simulator (Nagel-Schreckenberg)')
    parser.add_argument('--length', type=int, default=200, help='Road length (cells)')
    parser.add_argument('--cars', type=int, default=60, help='Number of cars')
    parser.add_argument('--density', type=float, default=None, help='Car density (overrides --cars)')
    parser.add_argument('--vmax', type=int, default=5, help='Max velocity')
    parser.add_argument('--p-slow', type=float, default=0.3, help='Random slowdown probability')
    parser.add_argument('--steps', type=int, default=300, help='Simulation steps')
    parser.add_argument('--seed', type=int, default=None, help='Random seed')
    parser.add_argument('--animate', action='store_true', help='Show ASCII animation')
    parser.add_argument('--compare', action='store_true', help='Compare different p_slow values')
    args = parser.parse_args()
    
    if args.density is not None:
        args.cars = int(args.length * args.density)
    
    if args.compare:
        print("p_slow | Avg Flow | Jam Steps | Avg Velocity")
        print("-------|----------|-----------|-------------")
        for p in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
            history = nagel_schreckenberg(
                args.length, args.cars, args.vmax, p, args.steps, seed=42
            )
            flows = compute_flow(history, args.length)
            jams = detect_jams(history, args.length)
            avg_v = sum(sum(v for v in vs) / len(vs) for _, vs in history) / len(history)
            print(f" {p:.1f}   |  {sum(flows)/len(flows):.3f}   |    {len(jams):3d}    |    {avg_v:.2f}")
        return
    
    print(f"Nagel-Schreckenberg phantom jam simulator")
    print(f"  Road: {args.length} cells, {args.cars} cars (density {args.cars/args.length:.2f})")
    print(f"  v_max={args.vmax}, p_slow={args.p_slow}, steps={args.steps}")
    print()
    
    history = nagel_schreckenberg(
        args.length, args.cars, args.vmax, args.p_slow, args.steps, args.seed
    )
    
    if args.animate:
        animate(history, args.length)
        print()
    
    # Stats
    flows = compute_flow(history, args.length)
    jams = detect_jams(history, args.length)
    avg_v = sum(sum(v for v in vs) / len(vs) for _, vs in history) / len(history)
    stopped = sum(sum(1 for v in vs if v == 0) for _, vs in history) / len(history)
    
    print(f"Results:")
    print(f"  Average flow:     {sum(flows)/len(flows):.3f} cars/cell/step")
    print(f"  Average velocity: {avg_v:.2f} / {args.vmax} max")
    print(f"  Jam timesteps:    {len(jams)} / {args.steps} ({100*len(jams)/args.steps:.0f}%)")
    print(f"  Avg stopped cars: {stopped:.1f} / {args.cars}")
    
    if jams:
        # Find jam wave speed (backward propagation)
        print(f"\n  ⚠️  Phantom jams detected!")
        print(f"  These jams have NO cause — no bottleneck, no accident.")
        print(f"  Just individual random braking → backward-propagating shockwave.")
        print(f"  (Sugiyama 2008 confirmed this with 22 real cars on a circular track)")
    else:
        print(f"\n  ✓ No persistent jams at this density/randomness.")
        print(f"  Try increasing --density or --p-slow to induce phantom jams.")


if __name__ == '__main__':
    main()
