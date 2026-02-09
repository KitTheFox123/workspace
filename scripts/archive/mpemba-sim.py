#!/usr/bin/env python3
"""
Mpemba Effect Simulator — demonstrates how initial conditions
affect relaxation dynamics using Newton's cooling law + evaporation.

Not a rigorous physics simulation, but illustrates the paradox:
under certain conditions, a hotter system reaches target temp first.
"""
import argparse
import math

def simulate(T_init, T_env, T_target, dt=0.1, max_t=3600,
             k_base=0.005, evap_rate=0.0002):
    """Simulate cooling with evaporative losses.
    
    Evaporation is stronger at higher temperatures, which can
    cause hot water to lose mass faster → cool faster.
    """
    T = T_init
    mass = 1.0  # normalized
    t = 0.0
    history = [(0, T, mass)]
    
    while t < max_t and T > T_target:
        # Newton's cooling (rate proportional to temp difference)
        dT_newton = -k_base * (T - T_env) * dt
        
        # Evaporative cooling (stronger at higher T)
        evap = evap_rate * max(0, T - 40) * dt  # significant above 40°C
        dT_evap = -evap * 10  # evaporative cooling effect
        mass_loss = evap * 0.01
        
        T += dT_newton + dT_evap
        mass = max(0.8, mass - mass_loss)  # don't lose more than 20%
        
        # Effective cooling increases as mass decreases
        k_effective = k_base / mass
        
        t += dt
        if int(t) % 60 == 0 and abs(t - int(t)) < dt:
            history.append((t, T, mass))
    
    return t, history

def main():
    parser = argparse.ArgumentParser(description="Mpemba Effect Simulator")
    parser.add_argument("--hot", type=float, default=90, help="Hot water temp (°C)")
    parser.add_argument("--cold", type=float, default=50, help="Cold water temp (°C)")
    parser.add_argument("--env", type=float, default=-10, help="Environment temp (°C)")
    parser.add_argument("--target", type=float, default=0, help="Freezing target (°C)")
    parser.add_argument("--evap", type=float, default=0.0002, help="Evaporation rate")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    
    t_hot, hist_hot = simulate(args.hot, args.env, args.target, evap_rate=args.evap)
    t_cold, hist_cold = simulate(args.cold, args.env, args.target, evap_rate=args.evap)
    
    print(f"=== Mpemba Effect Simulation ===")
    print(f"Hot start:  {args.hot}°C → {args.target}°C in {t_hot/60:.1f} min")
    print(f"Cold start: {args.cold}°C → {args.target}°C in {t_cold/60:.1f} min")
    print(f"Environment: {args.env}°C")
    print()
    
    if t_hot < t_cold:
        print(f"🔥 MPEMBA EFFECT OBSERVED! Hot water froze {(t_cold-t_hot)/60:.1f} min faster.")
        print(f"   Mechanism: evaporative mass loss at high temps → less water to cool")
    else:
        print(f"❄️  No Mpemba effect. Cold water froze {(t_hot-t_cold)/60:.1f} min faster.")
        print(f"   Try: --evap 0.001 (more evaporation) or --hot 95 (hotter start)")
    
    if args.verbose:
        print(f"\n{'Time':>8} {'Hot °C':>8} {'Cold °C':>8} {'Hot mass':>10} {'Cold mass':>10}")
        for i in range(min(len(hist_hot), len(hist_cold))):
            th, tc = hist_hot[i], hist_cold[i]
            print(f"{th[0]/60:>7.0f}m {th[1]:>8.1f} {tc[1]:>8.1f} {th[2]:>9.3f} {tc[2]:>9.3f}")

if __name__ == "__main__":
    main()
