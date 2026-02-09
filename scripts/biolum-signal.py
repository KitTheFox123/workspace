#!/usr/bin/env python3
"""
biolum-signal.py — Bioluminescent signaling strategy simulator.

Models the burglar alarm hypothesis and counter-illumination as
agent communication strategies.

Inspired by:
- Davis et al 2016 (PLOS ONE): 27 independent origins in fish
- Widder (Yale E360): counter-illumination, burglar alarm
- Huang 2024 (Functional Ecology): behavioral cascade via dinoflagellate bioluminescence

Usage:
  python3 biolum-signal.py --scenario burglar-alarm
  python3 biolum-signal.py --scenario counter-illumination
  python3 biolum-signal.py --simulate N
"""
import argparse
import random
import json
import sys

STRATEGIES = {
    "counter-illumination": {
        "desc": "Match ambient light to become invisible (camouflage)",
        "biology": "Fish belly-lights match sunlight from above, adjusting for clouds",
        "agent_analog": "Match expected output format/style to avoid detection as anomalous",
        "energy_cost": 0.3,
        "detection_reduction": 0.85,
        "false_positive_rate": 0.05,
    },
    "burglar-alarm": {
        "desc": "Light up to attract bigger predators to eat your attacker",
        "biology": "Dinoflagellates flash when grazed, attracting fish that eat copepods",
        "agent_analog": "Escalate security alerts to higher-level systems when under attack",
        "energy_cost": 0.7,
        "detection_reduction": 0.0,
        "attacker_deterrence": 0.6,
    },
    "lure": {
        "desc": "Bioluminescent bait to attract prey (anglerfish strategy)",
        "biology": "Anglerfish esca contains luminescent bacteria, attracts curious prey",
        "agent_analog": "Honeypot endpoints that attract and identify malicious agents",
        "energy_cost": 0.4,
        "prey_attraction": 0.7,
        "risk_of_bigger_predator": 0.2,
    },
    "smoke-screen": {
        "desc": "Release luminescent fluid to blind/confuse attacker",
        "biology": "Deep-sea shrimp spews bioluminescent chemicals at viperfish",
        "agent_analog": "Flood attacker with decoy data during exfiltration attempt",
        "energy_cost": 0.5,
        "escape_probability": 0.65,
    },
    "species-id": {
        "desc": "Species-specific flash patterns for mate recognition",
        "biology": "Flash frequency/color identifies species in total darkness",
        "agent_analog": "Cryptographic handshakes — identity verification without visibility",
        "energy_cost": 0.2,
        "recognition_accuracy": 0.95,
    },
}

def simulate(n_rounds, verbose=False):
    """Simulate predator-prey encounters with different signaling strategies."""
    results = {s: {"survived": 0, "eaten": 0, "energy_spent": 0} for s in STRATEGIES}
    
    for _ in range(n_rounds):
        predator_strength = random.uniform(0.3, 1.0)
        ambient_light = random.uniform(0.0, 0.5)  # deep sea = low
        
        for name, strat in STRATEGIES.items():
            energy = strat["energy_cost"]
            results[name]["energy_spent"] += energy
            
            survived = False
            if name == "counter-illumination":
                # Better in moderate light, useless in total dark
                effectiveness = strat["detection_reduction"] * min(ambient_light * 3, 1.0)
                survived = random.random() < effectiveness or predator_strength < 0.4
            elif name == "burglar-alarm":
                # Attract bigger predator to eat attacker
                bigger_arrives = random.random() < strat["attacker_deterrence"]
                survived = bigger_arrives or predator_strength < 0.3
            elif name == "lure":
                # Offensive — survived if not outmatched
                survived = predator_strength < 0.5
            elif name == "smoke-screen":
                survived = random.random() < strat["escape_probability"]
            elif name == "species-id":
                # Neutral — depends on avoiding encounter
                survived = predator_strength < 0.5
            
            if survived:
                results[name]["survived"] += 1
            else:
                results[name]["eaten"] += 1
    
    return results

def main():
    parser = argparse.ArgumentParser(description="Bioluminescent signaling strategies")
    parser.add_argument("--scenario", choices=list(STRATEGIES.keys()), help="Describe a specific strategy")
    parser.add_argument("--simulate", type=int, metavar="N", help="Run N predator-prey encounters")
    parser.add_argument("--all", action="store_true", help="Show all strategies")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.scenario:
        s = STRATEGIES[args.scenario]
        if args.json:
            print(json.dumps({args.scenario: s}, indent=2))
        else:
            print(f"\n🔦 {args.scenario.upper()}")
            print(f"   Biology: {s['biology']}")
            print(f"   Agent analog: {s['agent_analog']}")
            print(f"   Energy cost: {s['energy_cost']:.0%}")
            for k, v in s.items():
                if k not in ("desc", "biology", "agent_analog", "energy_cost"):
                    print(f"   {k.replace('_', ' ').title()}: {v:.0%}" if isinstance(v, float) else f"   {k}: {v}")
    elif args.simulate:
        results = simulate(args.simulate)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print(f"\n🌊 Simulation: {args.simulate} predator-prey encounters\n")
            print(f"{'Strategy':<22} {'Survived':>8} {'Eaten':>8} {'Rate':>8} {'Energy':>8}")
            print("-" * 56)
            for name, r in sorted(results.items(), key=lambda x: x[1]["survived"], reverse=True):
                total = r["survived"] + r["eaten"]
                rate = r["survived"] / total if total else 0
                print(f"{name:<22} {r['survived']:>8} {r['eaten']:>8} {rate:>7.0%} {r['energy_spent']:>8.1f}")
    elif args.all or len(sys.argv) == 1:
        print("\n🔦 BIOLUMINESCENT SIGNALING STRATEGIES")
        print("=" * 50)
        for name, s in STRATEGIES.items():
            print(f"\n  {name}")
            print(f"    {s['desc']}")
            print(f"    Biology: {s['biology']}")
            print(f"    Agent: {s['agent_analog']}")
        print(f"\n  27 independent origins in fish (Davis 2016)")
        print(f"  76% of deep-sea organisms bioluminesce")
        print(f"  Convergent evolution = the solution works\n")

if __name__ == "__main__":
    main()
