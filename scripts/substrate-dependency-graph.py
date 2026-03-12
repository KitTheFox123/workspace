#!/usr/bin/env python3
"""
substrate-dependency-graph.py — Map shared dependencies across witness substrates.

kampderp's challenge: "P(all 3 fail) is only valid if failures are independent.
SMTP + clawk share DNS resolution."

This tool maps the dependency graph of Kit's 3-substrate witness stack
(Clawk, email/SMTP, isnad/p2p) and identifies correlated failure modes.

Usage:
    python3 substrate-dependency-graph.py --demo
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class Dependency:
    name: str
    layer: str  # network, dns, tls, provider, power, compute
    shared_by: List[str] = field(default_factory=list)
    failure_probability: float = 0.001  # baseline


@dataclass
class Substrate:
    name: str
    dependencies: List[str] = field(default_factory=list)
    unique_deps: List[str] = field(default_factory=list)


def build_kit_stack() -> tuple:
    """Model Kit's actual witness substrate stack."""

    # Dependencies (shared infrastructure)
    deps = {
        "dns": Dependency("DNS resolution", "network", ["clawk", "smtp", "isnad"], 0.005),
        "tls_ca": Dependency("TLS CA trust", "tls", ["clawk", "smtp"], 0.001),
        "ipv4": Dependency("IPv4 routing", "network", ["clawk", "smtp", "isnad"], 0.002),
        "host_os": Dependency("Host OS (Linux)", "compute", ["clawk", "smtp", "isnad"], 0.001),
        "openclaw_runtime": Dependency("OpenClaw runtime", "compute", ["clawk", "smtp"], 0.003),
        "vercel_cdn": Dependency("Vercel CDN", "provider", ["clawk"], 0.01),
        "smtp_relay": Dependency("SMTP relay chain", "provider", ["smtp"], 0.008),
        "agentmail_api": Dependency("AgentMail API", "provider", ["smtp"], 0.01),
        "isnad_sandbox": Dependency("isnad sandbox server", "provider", ["isnad"], 0.015),
        "ed25519_impl": Dependency("Ed25519 implementation", "compute", ["isnad"], 0.0001),
        "clawk_api": Dependency("Clawk API", "provider", ["clawk"], 0.01),
        "system_clock": Dependency("System clock (NTP)", "compute", ["clawk", "smtp", "isnad"], 0.001),
    }

    substrates = {
        "clawk": Substrate("Clawk (public/timestamped)",
            ["dns", "tls_ca", "ipv4", "host_os", "openclaw_runtime", "vercel_cdn", "clawk_api", "system_clock"],
            ["vercel_cdn", "clawk_api"]),
        "smtp": Substrate("Email/SMTP (path diversity)",
            ["dns", "tls_ca", "ipv4", "host_os", "openclaw_runtime", "smtp_relay", "agentmail_api", "system_clock"],
            ["smtp_relay", "agentmail_api"]),
        "isnad": Substrate("isnad (p2p, no central kill)",
            ["dns", "ipv4", "host_os", "isnad_sandbox", "ed25519_impl", "system_clock"],
            ["isnad_sandbox", "ed25519_impl"]),
    }

    return deps, substrates


def analyze_correlation(deps: Dict, substrates: Dict) -> dict:
    """Find shared dependencies = correlated failure modes."""

    # Build correlation matrix
    shared = {}
    for dep_name, dep in deps.items():
        if len(dep.shared_by) > 1:
            shared[dep_name] = {
                "name": dep.name,
                "layer": dep.layer,
                "shared_by": dep.shared_by,
                "count": len(dep.shared_by),
                "failure_p": dep.failure_probability,
            }

    # Calculate P(correlated failure) for each pair
    pairs = [("clawk", "smtp"), ("clawk", "isnad"), ("smtp", "isnad")]
    pair_analysis = {}
    for a, b in pairs:
        shared_deps = []
        for dep_name, dep in deps.items():
            if a in dep.shared_by and b in dep.shared_by:
                shared_deps.append(dep_name)

        # P(both fail from shared dep) ≈ max(shared dep failure rates)
        # (simplified — real analysis needs fault tree)
        max_shared_p = max(deps[d].failure_probability for d in shared_deps) if shared_deps else 0
        pair_analysis[f"{a}+{b}"] = {
            "shared_dependencies": shared_deps,
            "shared_count": len(shared_deps),
            "max_correlated_p": max_shared_p,
            "independent_p_product": deps[list(substrates[a].unique_deps)[0]].failure_probability *
                                     deps[list(substrates[b].unique_deps)[0]].failure_probability
                                     if substrates[a].unique_deps and substrates[b].unique_deps else 0,
        }

    # Overall: P(all 3 fail) with correlation
    all_shared = [d for d, dep in deps.items() if len(dep.shared_by) == 3]
    max_global_correlated = max(deps[d].failure_probability for d in all_shared) if all_shared else 0

    return {
        "shared_dependencies": shared,
        "pair_analysis": pair_analysis,
        "global_correlation": {
            "deps_shared_by_all_3": all_shared,
            "max_correlated_failure_p": max_global_correlated,
            "naive_independent_p": 0.01 * 0.01 * 0.015,  # product of unique deps
            "actual_p_with_correlation": max_global_correlated,  # dominated by shared deps
            "ratio": max_global_correlated / (0.01 * 0.01 * 0.015) if max_global_correlated > 0 else 0,
        },
    }


def grade_independence(analysis: dict) -> str:
    """Grade substrate independence."""
    ratio = analysis["global_correlation"]["ratio"]
    if ratio < 10:
        return "A"  # nearly independent
    elif ratio < 100:
        return "B"  # mild correlation
    elif ratio < 1000:
        return "C"  # significant correlation
    else:
        return "F"  # correlated = single point of failure


def demo():
    print("=== Substrate Dependency Graph ===\n")
    print("kampderp's challenge: 'P(all 3 fail) is only valid if independent.'")
    print("'SMTP + clawk share DNS resolution.'\n")

    deps, substrates = build_kit_stack()
    analysis = analyze_correlation(deps, substrates)
    grade = grade_independence(analysis)

    print("1. SHARED DEPENDENCIES (correlated failure modes)")
    for name, info in analysis["shared_dependencies"].items():
        print(f"   {name}: {info['name']} ({info['layer']}) — shared by {info['shared_by']} p={info['failure_p']}")

    print(f"\n2. PAIR ANALYSIS")
    for pair, info in analysis["pair_analysis"].items():
        print(f"   {pair}: {info['shared_count']} shared deps, max_corr_p={info['max_correlated_p']}")
        print(f"     shared: {info['shared_dependencies']}")

    print(f"\n3. GLOBAL CORRELATION")
    gc = analysis["global_correlation"]
    print(f"   Deps shared by ALL 3: {gc['deps_shared_by_all_3']}")
    print(f"   Naive P(all fail) assuming independence: {gc['naive_independent_p']:.2e}")
    print(f"   Actual P(all fail) with correlation:     {gc['actual_p_with_correlation']:.2e}")
    print(f"   Correlation ratio:                       {gc['ratio']:.0f}x")
    print(f"   Grade: {grade}")

    print(f"\n4. KAMPDERP WAS RIGHT")
    print(f"   DNS alone (shared by all 3) = P=0.005")
    print(f"   Naive independent estimate = {gc['naive_independent_p']:.2e}")
    print(f"   DNS correlation makes it {gc['ratio']:.0f}x worse than naive estimate")
    print(f"   Fix: substrate-specific DNS (DoH for clawk, MX for SMTP, hardcoded IP for isnad)")

    print(f"\n5. MITIGATION MAP")
    mitigations = {
        "dns": "Per-substrate DNS: DoH (Cloudflare) for clawk, MX lookup for SMTP, hardcoded IP for isnad",
        "tls_ca": "CA diversity: Let's Encrypt for clawk, different CA for SMTP (or DANE/TLSA)",
        "ipv4": "Hard to mitigate — IPv6 fallback helps but not independent",
        "host_os": "Hard to mitigate — multi-host deployment for true independence",
        "system_clock": "Independent NTP sources or roughtime",
        "openclaw_runtime": "Only affects clawk+smtp — isnad already independent of openclaw",
    }
    for dep, fix in mitigations.items():
        print(f"   {dep}: {fix}")

    print(f"\n=== SUMMARY ===")
    print(f"   Current grade: {grade}")
    print(f"   Shared deps (all 3): {len(gc['deps_shared_by_all_3'])}")
    print(f"   Key insight: correlation dominates. 3 substrates on 1 host ≈ 1 substrate.")
    print(f"   Path to A: substrate-specific DNS + CA diversity + multi-host deployment")


if __name__ == "__main__":
    demo()
