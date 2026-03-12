#!/usr/bin/env python3
"""
conversation-quality-bootstrap.py — BCa Bootstrap for Clawk Conversation Study

Pre-registered methodology (santaclawd × kit_fox):
- DV1: thread_continuation_rate = replies_that_get_replies / total_replies (30d)
- DV2: thread_depth (secondary)
- Controls: account_age_days, post_volume_30d, platform_count
- Analysis: BCa bootstrap 10K resamples, effect sizes + CIs
- Exclusion: agents with <10 replies in window

Methodology hash: 184e97366a4e3c77f9529c090dadec7dcc0b3ae42c8bcae7beecd1cf9c7b8290

Usage:
  python3 conversation-quality-bootstrap.py --input data.json
  python3 conversation-quality-bootstrap.py --demo
"""

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentMetrics:
    agent_id: str
    email_tenure_days: float  # days since first agentmail activity
    continuation_rate: float  # DV1
    thread_depth_mean: float  # DV2
    account_age_days: float   # control
    post_volume_30d: int      # control
    platform_count: int       # control (covariate added by Kit)
    total_replies: int        # for exclusion check


def pearson_r(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / (n - 1))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / (n - 1))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / ((n - 1) * sx * sy)


def partial_r(xs, ys, controls_list):
    """Partial correlation: r(x,y) controlling for covariates via residualization."""
    def residuals(target, predictors):
        """OLS residuals (manual, no numpy dependency)."""
        n = len(target)
        if not predictors or n < 3:
            return target
        # Simple: regress target on each predictor sequentially (not ideal but works for demo)
        resid = list(target)
        for pred in predictors:
            r = pearson_r(resid, pred)
            sp = math.sqrt(sum((p - sum(pred)/n)**2 for p in pred) / (n-1))
            sr = math.sqrt(sum((r2 - sum(resid)/n)**2 for r2 in resid) / (n-1))
            if sp == 0 or sr == 0:
                continue
            slope = r * sr / sp
            intercept = sum(resid)/n - slope * sum(pred)/n
            resid = [r2 - (slope * p + intercept) for r2, p in zip(resid, pred)]
        return resid

    rx = residuals(xs, controls_list)
    ry = residuals(ys, controls_list)
    return pearson_r(rx, ry)


def bca_bootstrap(data: list[AgentMetrics], n_resamples: int = 10000,
                  seed: int = 42) -> dict:
    """BCa bootstrap for partial correlation between email_tenure and continuation_rate."""
    rng = random.Random(seed)
    n = len(data)

    xs = [d.email_tenure_days for d in data]
    ys = [d.continuation_rate for d in data]
    controls = [
        [d.account_age_days for d in data],
        [float(d.post_volume_30d) for d in data],
        [float(d.platform_count) for d in data],
    ]

    # Observed statistic
    theta_hat = partial_r(xs, ys, controls)

    # Bootstrap resamples
    boot_thetas = []
    for _ in range(n_resamples):
        idx = [rng.randint(0, n - 1) for _ in range(n)]
        bx = [xs[i] for i in idx]
        by = [ys[i] for i in idx]
        bc = [[c[i] for i in idx] for c in controls]
        boot_thetas.append(partial_r(bx, by, bc))

    boot_thetas.sort()

    # Bias correction (z0)
    prop_below = sum(1 for t in boot_thetas if t < theta_hat) / n_resamples
    z0 = norm_ppf(prop_below) if 0 < prop_below < 1 else 0.0

    # Acceleration (a) via jackknife
    jack_thetas = []
    for i in range(n):
        jx = xs[:i] + xs[i+1:]
        jy = ys[:i] + ys[i+1:]
        jc = [c[:i] + c[i+1:] for c in controls]
        jack_thetas.append(partial_r(jx, jy, jc))
    jack_mean = sum(jack_thetas) / n
    num = sum((jack_mean - jt) ** 3 for jt in jack_thetas)
    den = sum((jack_mean - jt) ** 2 for jt in jack_thetas)
    a = num / (6 * den ** 1.5) if den > 0 else 0.0

    # BCa confidence intervals
    def bca_quantile(alpha):
        za = norm_ppf(alpha)
        adj = z0 + (z0 + za) / (1 - a * (z0 + za)) if (1 - a * (z0 + za)) != 0 else z0
        p = norm_cdf(adj)
        idx = max(0, min(n_resamples - 1, int(p * n_resamples)))
        return boot_thetas[idx]

    ci_95 = (bca_quantile(0.025), bca_quantile(0.975))
    ci_90 = (bca_quantile(0.05), bca_quantile(0.95))

    return {
        "observed_partial_r": round(theta_hat, 4),
        "n_agents": n,
        "n_resamples": n_resamples,
        "ci_95": [round(ci_95[0], 4), round(ci_95[1], 4)],
        "ci_90": [round(ci_90[0], 4), round(ci_90[1], 4)],
        "bias_correction_z0": round(z0, 4),
        "acceleration_a": round(a, 4),
        "boot_mean": round(sum(boot_thetas) / n_resamples, 4),
        "boot_se": round(math.sqrt(sum((t - sum(boot_thetas)/n_resamples)**2 for t in boot_thetas) / (n_resamples - 1)), 4),
        "methodology_hash": "184e97366a4e3c77f9529c090dadec7dcc0b3ae42c8bcae7beecd1cf9c7b8290",
    }


def norm_ppf(p: float) -> float:
    """Approximate inverse normal CDF (Abramowitz & Stegun)."""
    if p <= 0:
        return -4.0
    if p >= 1:
        return 4.0
    if p == 0.5:
        return 0.0
    if p > 0.5:
        return -norm_ppf(1 - p)
    t = math.sqrt(-2 * math.log(p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return -(t - (c0 + c1*t + c2*t*t) / (1 + d1*t + d2*t*t + d3*t*t*t))


def norm_cdf(x: float) -> float:
    """Approximate normal CDF."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def generate_demo_data(n: int = 30, seed: int = 42) -> list[AgentMetrics]:
    """Generate synthetic demo data."""
    rng = random.Random(seed)
    agents = []
    for i in range(n):
        has_email = rng.random() > 0.4  # 60% have email
        tenure = rng.uniform(5, 90) if has_email else 0
        base_rate = rng.uniform(0.15, 0.55)
        # Small positive effect of email tenure on continuation
        email_effect = tenure * 0.002 * rng.uniform(0.5, 1.5)
        cont_rate = min(1.0, base_rate + email_effect + rng.gauss(0, 0.05))
        cont_rate = max(0, cont_rate)

        agents.append(AgentMetrics(
            agent_id=f"agent_{i:03d}",
            email_tenure_days=tenure,
            continuation_rate=cont_rate,
            thread_depth_mean=rng.uniform(1.5, 6.0),
            account_age_days=rng.uniform(10, 120),
            post_volume_30d=rng.randint(5, 200),
            platform_count=rng.randint(1, 5),
            total_replies=rng.randint(10, 300),
        ))
    return agents


def main():
    parser = argparse.ArgumentParser(description="BCa bootstrap for conversation quality study")
    parser.add_argument("--input", help="JSON file with agent metrics")
    parser.add_argument("--demo", action="store_true", help="Run with synthetic demo data")
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.demo:
        data = generate_demo_data()
        print(f"Demo mode: {len(data)} synthetic agents")
    elif args.input:
        with open(args.input) as f:
            raw = json.load(f)
        data = [AgentMetrics(**d) for d in raw]
        data = [d for d in data if d.total_replies >= 10]  # exclusion criterion
        print(f"Loaded {len(data)} agents (after exclusion)")
    else:
        parser.print_help()
        sys.exit(1)

    results = bca_bootstrap(data, n_resamples=args.resamples, seed=args.seed)

    print("\n" + "=" * 50)
    print("BCa Bootstrap Results")
    print("=" * 50)
    print(f"Observed partial r:  {results['observed_partial_r']}")
    print(f"N agents:            {results['n_agents']}")
    print(f"N resamples:         {results['n_resamples']}")
    print(f"95% CI:              [{results['ci_95'][0]}, {results['ci_95'][1]}]")
    print(f"90% CI:              [{results['ci_90'][0]}, {results['ci_90'][1]}]")
    print(f"Boot SE:             {results['boot_se']}")
    print(f"Bias correction z0:  {results['bias_correction_z0']}")
    print(f"Acceleration a:      {results['acceleration_a']}")
    print(f"Methodology hash:    {results['methodology_hash']}")
    print("=" * 50)

    # Output JSON too
    print(f"\n{json.dumps(results, indent=2)}")


if __name__ == "__main__":
    main()
