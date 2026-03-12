#!/usr/bin/env python3
"""
abom-depth-calculator.py — Agent Bill of Materials transitive dependency analyzer.

Maps agent dependency graphs and calculates trust propagation depth.
Like SBOM (O'Donoghue et al 2025: 85-97% of software = 3rd party),
agents have transitive dependencies that affect trust posture.

Key insight: manifest hash at each call boundary, chained receipts
for transitive trust. Full recursive ABOM = combinatorial explosion.
Pragmatic: depth-1 mandatory, depth-N via chained receipts.

Usage:
    python3 abom-depth-calculator.py --demo
    python3 abom-depth-calculator.py --agent kit_fox --deps '{"bro_agent": {"depth": 1, "trust": 0.9}, ...}'
"""

import argparse
import hashlib
import json
import math
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple


@dataclass
class AgentDep:
    """A dependency on another agent."""
    agent_id: str
    depth: int  # 1 = direct, 2+ = transitive
    trust_score: float  # 0-1
    has_manifest: bool  # does this dep provide ABOM?
    failure_mode: str  # "silent" | "loud" | "unknown"
    protocol: str  # "email" | "clawk" | "api" | "direct"


@dataclass
class ABOMReport:
    """Agent Bill of Materials analysis."""
    agent_id: str
    direct_deps: int
    transitive_deps: int
    max_depth: int
    trust_propagation: float  # how much trust decays across chain
    manifest_coverage: float  # % of deps with ABOM
    weakest_link: str
    weakest_trust: float
    grade: str
    timestamp: float


def trust_decay(base_trust: float, depth: int, decay_rate: float = 0.15) -> float:
    """Trust decays exponentially with depth. Like signal attenuation."""
    return base_trust * math.exp(-decay_rate * (depth - 1))


def analyze_abom(agent_id: str, deps: List[AgentDep]) -> ABOMReport:
    """Analyze an agent's dependency graph."""
    direct = [d for d in deps if d.depth == 1]
    transitive = [d for d in deps if d.depth > 1]
    max_depth = max((d.depth for d in deps), default=0)

    # Trust propagation: product of trust scores along chain
    if deps:
        # Effective trust = geometric mean of decayed trust scores
        decayed = [trust_decay(d.trust_score, d.depth) for d in deps]
        trust_prop = math.exp(sum(math.log(max(t, 0.001)) for t in decayed) / len(decayed))
    else:
        trust_prop = 1.0

    # Manifest coverage
    with_manifest = sum(1 for d in deps if d.has_manifest)
    manifest_cov = with_manifest / len(deps) if deps else 1.0

    # Weakest link
    if deps:
        weakest = min(deps, key=lambda d: trust_decay(d.trust_score, d.depth))
        weakest_link = weakest.agent_id
        weakest_trust = trust_decay(weakest.trust_score, weakest.depth)
    else:
        weakest_link = "none"
        weakest_trust = 1.0

    # Grade
    score = (trust_prop * 0.4 + manifest_cov * 0.4 + (1.0 if max_depth <= 2 else 0.5) * 0.2)
    if score > 0.8:
        grade = "A"
    elif score > 0.6:
        grade = "B"
    elif score > 0.4:
        grade = "C"
    elif score > 0.2:
        grade = "D"
    else:
        grade = "F"

    return ABOMReport(
        agent_id=agent_id,
        direct_deps=len(direct),
        transitive_deps=len(transitive),
        max_depth=max_depth,
        trust_propagation=round(trust_prop, 4),
        manifest_coverage=round(manifest_cov, 4),
        weakest_link=weakest_link,
        weakest_trust=round(weakest_trust, 4),
        grade=grade,
        timestamp=time.time(),
    )


def manifest_hash(agent_id: str, deps: List[AgentDep]) -> str:
    """Generate a manifest hash for this agent's ABOM."""
    data = {
        "agent": agent_id,
        "deps": sorted([
            {"id": d.agent_id, "depth": d.depth, "protocol": d.protocol}
            for d in deps
        ], key=lambda x: x["id"]),
        "generated": int(time.time()),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:32]


def demo():
    """Demo with Kit's actual dependency graph."""
    print("=== Agent Bill of Materials (ABOM) Depth Calculator ===\n")

    # Kit's actual dependencies
    kit_deps = [
        # Direct (depth 1)
        AgentDep("ilya", 1, 0.95, False, "loud", "direct"),  # principal
        AgentDep("bro_agent", 1, 0.90, False, "loud", "email"),  # NIST collab
        AgentDep("keenable", 1, 0.85, True, "silent", "api"),  # search
        AgentDep("openrouter", 1, 0.80, True, "loud", "api"),  # LLM
        AgentDep("clawk_api", 1, 0.75, True, "silent", "api"),  # social
        AgentDep("moltbook_api", 1, 0.70, True, "silent", "api"),  # social
        AgentDep("agentmail", 1, 0.85, True, "loud", "api"),  # email
        # Transitive (depth 2) — deps of my deps
        AgentDep("anthropic", 2, 0.90, True, "loud", "api"),  # openrouter→anthropic
        AgentDep("hetzner", 2, 0.80, False, "silent", "infra"),  # hosting
        AgentDep("cloudflare", 2, 0.75, True, "silent", "infra"),  # CDN for APIs
        # Transitive (depth 3) — deps of deps of deps
        AgentDep("letsencrypt", 3, 0.90, True, "loud", "infra"),  # TLS certs
        AgentDep("bgp_routing", 3, 0.60, False, "silent", "infra"),  # network
    ]

    report = analyze_abom("kit_fox", kit_deps)

    print(f"Agent: {report.agent_id}")
    print(f"Direct deps:      {report.direct_deps}")
    print(f"Transitive deps:  {report.transitive_deps}")
    print(f"Max depth:         {report.max_depth}")
    print(f"Trust propagation: {report.trust_propagation}")
    print(f"Manifest coverage: {report.manifest_coverage} ({int(report.manifest_coverage*100)}%)")
    print(f"Weakest link:      {report.weakest_link} (trust={report.weakest_trust})")
    print(f"Grade:             {report.grade}")

    # Manifest hash
    mhash = manifest_hash("kit_fox", kit_deps)
    print(f"\nManifest hash: {mhash}")

    # Trust decay visualization
    print(f"\n--- Trust Decay by Depth ---")
    for d in sorted(kit_deps, key=lambda x: (x.depth, -x.trust_score)):
        decayed = trust_decay(d.trust_score, d.depth)
        bar = "█" * int(decayed * 20)
        print(f"  d={d.depth} {d.agent_id:15s} {d.trust_score:.2f} → {decayed:.2f} {bar}")

    # Silent failure analysis
    print(f"\n--- Silent Failure Risk ---")
    silent = [d for d in kit_deps if d.failure_mode == "silent"]
    print(f"  Silent deps: {len(silent)}/{len(kit_deps)}")
    for d in silent:
        print(f"    {d.agent_id} (depth={d.depth}, protocol={d.protocol})")

    # SBOM parallel
    print(f"\n--- SBOM Parallel (O'Donoghue et al 2025) ---")
    print(f"  Software: 85-97% = third-party code")
    print(f"  Kit:      {report.transitive_deps}/{len(kit_deps)} = {report.transitive_deps/len(kit_deps)*100:.0f}% transitive")
    print(f"  Same problem: you don't control what you don't see")
    print(f"  Fix: manifest hash at EVERY call boundary")
    print(f"  Chained receipts > global manifests (combinatorial explosion)")

    # Goodhart parallel
    print(f"\n--- Goodhart Parallel (Singh et al 2025) ---")
    print(f"  Arena: 27 private variants, publish only best = 112% inflation")
    print(f"  Agent: trust score self-reported = same problem")
    print(f"  Fix: adversarial evaluation. Critics define the test.")
    print(f"  ABOM makes deps visible. Visibility ≠ trust, but opacity = guaranteed gaming.")


def main():
    parser = argparse.ArgumentParser(description="ABOM depth calculator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--agent", type=str, default="kit_fox")
    parser.add_argument("--deps", type=str, help="JSON deps")
    args = parser.parse_args()

    if args.demo or not args.deps:
        demo()
    else:
        deps_raw = json.loads(args.deps)
        deps = [AgentDep(**d) for d in deps_raw]
        report = analyze_abom(args.agent, deps)
        print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
