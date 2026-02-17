#!/usr/bin/env python3
"""
trust-prior-sim.py — Default Trust Prior Simulator

Models how initial trust assumptions affect system resilience.
Compares "trust-by-default" (0.95 prior) vs "distrust-by-default" (0.5 prior)
against a mixed population of honest and adversarial agents.

Inspired by: isnad methodology (default skepticism), zero trust architecture
(Jericho Forum 2004), and Bayesian trust updating.

Usage:
  python3 trust-prior-sim.py                    # default scenario
  python3 trust-prior-sim.py --adversary-pct 30 # 30% adversaries
  python3 trust-prior-sim.py --rounds 50        # 50 interaction rounds
"""

import argparse
import random
import sys
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: int
    honest: bool
    trust_score: float = 0.5  # will be set by prior

    def interact(self) -> bool:
        """Returns True if interaction is trustworthy."""
        if self.honest:
            return random.random() < 0.95  # honest agents occasionally fail
        else:
            return random.random() < 0.15  # adversaries occasionally appear honest


def bayesian_update(prior: float, observation: bool, sensitivity: float = 0.9) -> float:
    """
    Update trust score given observation.
    sensitivity: how much a single observation moves the prior.
    """
    if observation:  # trustworthy behavior
        likelihood_h1 = sensitivity  # P(good|trustworthy)
        likelihood_h0 = 1 - sensitivity  # P(good|untrustworthy)
    else:  # bad behavior
        likelihood_h1 = 1 - sensitivity
        likelihood_h0 = sensitivity

    posterior_unnorm = prior * likelihood_h1
    evidence = prior * likelihood_h1 + (1 - prior) * likelihood_h0

    if evidence == 0:
        return prior
    return max(0.01, min(0.99, posterior_unnorm / evidence))


def run_simulation(
    n_agents: int = 100,
    adversary_pct: float = 20,
    rounds: int = 30,
    trust_prior: float = 0.5,
    threshold: float = 0.7,
    seed: int = 42,
) -> dict:
    random.seed(seed)

    n_adversaries = int(n_agents * adversary_pct / 100)
    agents = []
    for i in range(n_agents):
        honest = i >= n_adversaries
        agents.append(Agent(id=i, honest=honest, trust_score=trust_prior))

    random.shuffle(agents)

    stats = {
        'rounds': [],
        'false_positives_total': 0,  # adversaries trusted
        'false_negatives_total': 0,  # honest agents distrusted
        'damage_total': 0,  # interactions with adversaries above threshold
    }

    for r in range(rounds):
        round_damage = 0
        round_fp = 0
        round_fn = 0

        for agent in agents:
            result = agent.interact()
            agent.trust_score = bayesian_update(agent.trust_score, result)

            # Count damage: adversary with trust above threshold
            if not agent.honest and agent.trust_score >= threshold:
                round_damage += 1
                round_fp += 1
            elif agent.honest and agent.trust_score < threshold:
                round_fn += 1

        stats['damage_total'] += round_damage
        stats['false_positives_total'] += round_fp
        stats['false_negatives_total'] += round_fn
        stats['rounds'].append({
            'round': r + 1,
            'damage': round_damage,
            'fp': round_fp,
            'fn': round_fn,
        })

    # Final state
    trusted_adversaries = sum(1 for a in agents if not a.honest and a.trust_score >= threshold)
    distrusted_honest = sum(1 for a in agents if a.honest and a.trust_score < threshold)

    return {
        'prior': trust_prior,
        'n_agents': n_agents,
        'n_adversaries': n_adversaries,
        'num_rounds': rounds,
        'round_data': stats['rounds'],
        'threshold': threshold,
        'total_damage': stats['damage_total'],
        'total_fp': stats['false_positives_total'],
        'total_fn': stats['false_negatives_total'],
        'final_trusted_adversaries': trusted_adversaries,
        'final_distrusted_honest': distrusted_honest,
        'convergence_round': next(
            (s['round'] for s in stats['rounds'] if s['fp'] == 0),
            None,
        ),
    }


def main():
    parser = argparse.ArgumentParser(description='Trust Prior Simulator')
    parser.add_argument('--agents', type=int, default=100)
    parser.add_argument('--adversary-pct', type=float, default=20)
    parser.add_argument('--rounds', type=int, default=30)
    parser.add_argument('--threshold', type=float, default=0.7)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    priors = [0.95, 0.75, 0.5, 0.25, 0.1]

    print(f"\n{'='*70}")
    print(f"  TRUST PRIOR SIMULATION — {args.agents} agents, {args.adversary_pct}% adversaries")
    print(f"  {args.rounds} rounds, trust threshold: {args.threshold}")
    print(f"{'='*70}\n")
    print(f"  {'Prior':>6}  {'Damage':>8}  {'Conv.Round':>10}  {'Final FP':>8}  {'Final FN':>8}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*8}")

    for prior in priors:
        result = run_simulation(
            n_agents=args.agents,
            adversary_pct=args.adversary_pct,
            rounds=args.rounds,
            trust_prior=prior,
            threshold=args.threshold,
            seed=args.seed,
        )
        conv = result['convergence_round'] or 'never'
        label = '← skeptical' if prior <= 0.25 else '← naive' if prior >= 0.9 else ''
        print(
            f"  {prior:>6.2f}  {result['total_damage']:>8}  {str(conv):>10}  "
            f"{result['final_trusted_adversaries']:>8}  {result['final_distrusted_honest']:>8}  {label}"
        )

    print(f"\n  Damage = adversary-rounds-above-threshold (cumulative exposure)")
    print(f"  Conv.Round = first round with zero false positives")
    print(f"  FP = adversaries still trusted at end | FN = honest agents distrusted")
    print(f"\n  Insight: higher prior → more cumulative damage before convergence.")
    print(f"  Isnad principle: start skeptical, let evidence prove trustworthiness.")
    print(f"{'='*70}")

    # Visual: damage over time for extreme priors
    print(f"\n  Damage timeline (█ = adversary trusted that round):")
    for prior in [0.95, 0.1]:
        result_full = run_simulation(
            n_agents=args.agents,
            adversary_pct=args.adversary_pct,
            rounds=min(args.rounds, 20),
            trust_prior=prior,
            threshold=args.threshold,
            seed=args.seed,
        )
        bars = ""
        for s in result_full['round_data'][:20]:
            if s['fp'] > 10:
                bars += "█"
            elif s['fp'] > 5:
                bars += "▓"
            elif s['fp'] > 0:
                bars += "▒"
            else:
                bars += "░"
        label = "naive" if prior > 0.5 else "skeptic"
        print(f"  {prior:.2f} ({label:>7}): {bars}")
    print(f"  {'':>17} {'1' + ' '*8 + '5' + ' '*8 + '10' + ' '*7 + '15' + ' '*7 + '20'}")
    print()


if __name__ == '__main__':
    main()
