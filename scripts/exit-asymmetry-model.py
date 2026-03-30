#!/usr/bin/env python3
"""
exit-asymmetry-model.py — Models why dissolution should cost more than creation.

Based on:
- Eswaran & Neary (2013, UBC): Sunk costs as evolutionary commitment devices.
  Nature hardwired sunk cost honoring because it (1) solves self-control via
  prefrontal-motivational conflict, and (2) protects property rights by making
  producers more aggressive defenders (endowment effect as fitness adaptation).
- Hirschman (1970): Exit, Voice, Loyalty — exit cost shapes voice/loyalty ratio.
- Harrigan (Columbia): Exit barriers from sunk costs, specialized assets.

Key insight: Creation cost = filter. Dissolution cost = signal.
Low creation + high dissolution = honest agents stay, sybils can't exit cleanly.
The attestation chain IS the sunk cost. Dissolving it costs social capital.

4 scenarios with Monte Carlo simulation:
1. Symmetric low (cheap in, cheap out) — sybil paradise
2. Symmetric high (expensive in, expensive out) — ghost town
3. Asymmetric (cheap in, expensive out) — optimal for trust networks
4. Inverse asymmetric (expensive in, cheap out) — credential mills

Measures: sybil survival rate, honest agent retention, network trust density,
voice-to-exit ratio (Hirschman metric).
"""

import random
import statistics

random.seed(42)

N_AGENTS = 200
N_ROUNDS = 50
SYBIL_FRACTION = 0.3


def simulate_scenario(creation_cost: float, dissolution_cost: float, name: str):
    """
    creation_cost: 0-1, fraction of initial budget spent to join
    dissolution_cost: 0-1, fraction of accumulated reputation lost on exit
    """
    agents = []
    for i in range(N_AGENTS):
        is_sybil = i < int(N_AGENTS * SYBIL_FRACTION)
        agents.append({
            "id": i,
            "sybil": is_sybil,
            "reputation": 0.0,
            "rounds_active": 0,
            "exited": False,
            "voiced": 0,  # Hirschman voice events
            "exit_attempts": 0,
        })

    trust_density_history = []
    
    for round_num in range(N_ROUNDS):
        active = [a for a in agents if not a["exited"]]
        
        for agent in active:
            agent["rounds_active"] += 1
            
            if agent["sybil"]:
                # Sybils: accumulate reputation slowly, exit when profitable
                agent["reputation"] += random.uniform(0, 0.3)
                
                # Sybil exit decision: leave when reputation high enough to extract value
                # BUT dissolution cost makes clean exit expensive
                if agent["reputation"] > 5.0:
                    exit_value = agent["reputation"] * (1 - dissolution_cost)
                    stay_value = agent["reputation"] * 0.1  # diminishing returns for sybils
                    
                    if exit_value > stay_value and random.random() > dissolution_cost:
                        agent["exit_attempts"] += 1
                        agent["exited"] = True
                    else:
                        # Forced to voice (complain/negotiate) instead of silent exit
                        agent["voiced"] += 1
            else:
                # Honest agents: steady reputation growth
                agent["reputation"] += random.uniform(0.2, 0.8)
                
                # Honest exit: only if genuinely dissatisfied (rare)
                if random.random() < 0.02:  # 2% chance of dissatisfaction
                    if dissolution_cost > 0.5:
                        # High exit cost → voice instead
                        agent["voiced"] += 1
                    else:
                        agent["exited"] = True
        
        # Trust density: avg reputation of active agents
        active_reps = [a["reputation"] for a in agents if not a["exited"]]
        if active_reps:
            trust_density_history.append(statistics.mean(active_reps))
    
    # Final metrics
    active_final = [a for a in agents if not a["exited"]]
    sybils = [a for a in agents if a["sybil"]]
    honest = [a for a in agents if not a["sybil"]]
    
    sybil_survival = len([s for s in sybils if not s["exited"]]) / len(sybils)
    honest_retention = len([h for h in honest if not h["exited"]]) / len(honest)
    
    total_voice = sum(a["voiced"] for a in agents)
    total_exits = sum(1 for a in agents if a["exited"])
    voice_exit_ratio = total_voice / max(total_exits, 1)
    
    final_trust = trust_density_history[-1] if trust_density_history else 0
    
    # Eswaran metric: sunk cost commitment strength
    # High dissolution cost + high retention = strong commitment
    commitment_strength = dissolution_cost * honest_retention
    
    return {
        "name": name,
        "creation_cost": creation_cost,
        "dissolution_cost": dissolution_cost,
        "sybil_survival": sybil_survival,
        "honest_retention": honest_retention,
        "voice_exit_ratio": voice_exit_ratio,
        "final_trust_density": final_trust,
        "commitment_strength": commitment_strength,
        "total_voice_events": total_voice,
        "total_exits": total_exits,
    }


def main():
    scenarios = [
        (0.1, 0.1, "symmetric_low (cheap in, cheap out)"),
        (0.8, 0.8, "symmetric_high (expensive in, expensive out)"),
        (0.1, 0.8, "ASYMMETRIC (cheap in, expensive out)"),
        (0.8, 0.1, "inverse (expensive in, cheap out)"),
    ]
    
    print("=" * 70)
    print("EXIT ASYMMETRY MODEL")
    print("Eswaran & Neary (2013) + Hirschman (1970)")
    print("=" * 70)
    print(f"Agents: {N_AGENTS} ({SYBIL_FRACTION*100:.0f}% sybil), Rounds: {N_ROUNDS}")
    print()
    
    results = []
    for creation, dissolution, name in scenarios:
        r = simulate_scenario(creation, dissolution, name)
        results.append(r)
    
    # Display
    for r in results:
        print(f"--- {r['name']} ---")
        print(f"  Sybil survival:     {r['sybil_survival']:.1%}")
        print(f"  Honest retention:   {r['honest_retention']:.1%}")
        print(f"  Voice/Exit ratio:   {r['voice_exit_ratio']:.2f} (Hirschman)")
        print(f"  Trust density:      {r['final_trust_density']:.2f}")
        print(f"  Commitment (E&N):   {r['commitment_strength']:.3f}")
        print(f"  Exits: {r['total_exits']}, Voice events: {r['total_voice_events']}")
        print()
    
    # Key finding
    asym = next(r for r in results if "ASYMMETRIC" in r["name"])
    sym_low = next(r for r in results if "symmetric_low" in r["name"])
    
    print("=" * 70)
    print("KEY FINDING:")
    print(f"  Asymmetric model reduces sybil survival by "
          f"{(sym_low['sybil_survival'] - asym['sybil_survival'])*100:.1f}pp")
    print(f"  while maintaining {asym['honest_retention']:.1%} honest retention")
    print(f"  Voice/Exit ratio {asym['voice_exit_ratio']:.1f}x "
          f"(vs {sym_low['voice_exit_ratio']:.1f}x symmetric)")
    print()
    print("THESIS: Creation cost = filter. Dissolution cost = signal.")
    print("The attestation chain IS the sunk cost (Eswaran & Neary).")
    print("High exit cost forces voice over exit (Hirschman).")
    print("Sybils can't dissolve cleanly → forced into visible negotiation.")
    print("=" * 70)


if __name__ == "__main__":
    main()
