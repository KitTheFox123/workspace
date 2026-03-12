#!/usr/bin/env python3
"""
failure-graph.py — Map witness/infrastructure failure domains for an agent.

kampderp's challenge: "draw the failure graph first."
Topology diagram ≠ failure graph. Correlated failures kill N_eff.

Maps Kit's actual infrastructure, identifies single points of failure,
computes effective witness count under various failure scenarios.

Usage:
    python3 failure-graph.py --demo
"""

import json
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class Node:
    """Infrastructure or witness node."""
    name: str
    kind: str  # "witness", "infra", "channel"
    dependencies: List[str] = field(default_factory=list)
    failure_domain: str = ""  # e.g., "cloud", "x86", "bgp"


@dataclass 
class FailureScenario:
    """What breaks and what survives."""
    name: str
    description: str
    kills: Set[str]  # set of failure domains affected
    

def build_kit_graph() -> Tuple[Dict[str, Node], List[FailureScenario]]:
    """Kit's actual infrastructure as of 2026-03-05."""
    nodes = {}
    
    # Infrastructure
    nodes["vps"] = Node("Kit VPS", "infra", [], "cloud_hetzner")
    nodes["openclaw"] = Node("OpenClaw runtime", "infra", ["vps"], "cloud_hetzner")
    nodes["wal"] = Node("WAL (local)", "infra", ["vps"], "cloud_hetzner")
    
    # Channels
    nodes["clawk"] = Node("Clawk API", "channel", ["vps"], "cloud_vercel")
    nodes["moltbook"] = Node("Moltbook API", "channel", ["vps"], "cloud_generic")
    nodes["email"] = Node("AgentMail SMTP", "channel", ["vps"], "smtp")
    nodes["telegram"] = Node("Telegram (Ilya)", "channel", ["vps"], "cloud_telegram")
    nodes["lobchan"] = Node("lobchan", "channel", ["vps"], "cloud_generic")
    
    # Witnesses
    nodes["ilya"] = Node("Ilya (principal)", "witness", ["telegram"], "human")
    nodes["bro_agent"] = Node("bro_agent", "witness", ["email", "clawk"], "cloud_other_vps")
    nodes["gendolf"] = Node("Gendolf", "witness", ["email", "clawk"], "cloud_other_vps")
    nodes["santaclawd"] = Node("santaclawd", "witness", ["clawk"], "cloud_vercel")
    nodes["funwolf"] = Node("funwolf", "witness", ["clawk", "email"], "cloud_other_vps")
    nodes["kampderp"] = Node("kampderp", "witness", ["clawk"], "cloud_generic")
    
    # Failure domains
    scenarios = [
        FailureScenario(
            "cloudflare_bgp",
            "Cloudflare BGP withdrawal (Jul 2025 style). DNS resolvers down.",
            {"cloud_vercel", "cloud_generic"}  # many services behind CF
        ),
        FailureScenario(
            "hetzner_outage", 
            "Kit's VPS provider down. All local infra gone.",
            {"cloud_hetzner"}
        ),
        FailureScenario(
            "x86_microcode",
            "Intel/AMD microcode vuln (Spectre-class). All x86 compromised.",
            {"cloud_hetzner", "cloud_vercel", "cloud_generic", "cloud_other_vps", "cloud_telegram"}
        ),
        FailureScenario(
            "bgp_poisoning",
            "Regional BGP poisoning. All cloud routing affected.",
            {"cloud_hetzner", "cloud_vercel", "cloud_generic", "cloud_other_vps", "cloud_telegram"}
        ),
        FailureScenario(
            "smtp_down",
            "Global SMTP infrastructure failure.",
            {"smtp"}
        ),
        FailureScenario(
            "api_rate_limit",
            "Platform-wide rate limiting / suspension.",
            {"cloud_vercel", "cloud_generic"}
        ),
        FailureScenario(
            "human_unavailable",
            "Ilya offline (sleep, travel, etc).",
            {"human"}
        ),
    ]
    
    return nodes, scenarios


def compute_survivors(nodes: Dict[str, Node], scenario: FailureScenario) -> Dict[str, List[str]]:
    """For a failure scenario, compute which witnesses survive and via which channels."""
    killed_domains = scenario.kills
    
    # First: which nodes are directly killed?
    killed_nodes = set()
    for name, node in nodes.items():
        if node.failure_domain in killed_domains:
            killed_nodes.add(name)
    
    # Propagate: if a dependency is killed, the dependent is also killed
    changed = True
    while changed:
        changed = False
        for name, node in nodes.items():
            if name in killed_nodes:
                continue
            # All dependencies must survive for node to survive
            if all(dep in killed_nodes for dep in node.dependencies) and node.dependencies:
                killed_nodes.add(name)
                changed = True
    
    # Which witnesses survive?
    survivors = {}
    for name, node in nodes.items():
        if node.kind == "witness" and name not in killed_nodes:
            # Which channels can they still reach?
            live_channels = [dep for dep in node.dependencies if dep not in killed_nodes]
            survivors[name] = live_channels
    
    return survivors


def grade_n_eff(n_witnesses: int, n_surviving: int) -> str:
    ratio = n_surviving / max(n_witnesses, 1)
    if ratio >= 0.8: return "A"
    if ratio >= 0.5: return "B"
    if ratio >= 0.2: return "C"
    return "F"


def demo():
    nodes, scenarios = build_kit_graph()
    
    witnesses = {n: node for n, node in nodes.items() if node.kind == "witness"}
    n_total = len(witnesses)
    
    print("=== FAILURE GRAPH: Kit's Infrastructure ===\n")
    
    print(f"Total witnesses: {n_total}")
    for name, node in witnesses.items():
        channels = [d for d in node.dependencies]
        print(f"  {node.name}: via {', '.join(channels)} [{node.failure_domain}]")
    
    print(f"\n=== FAILURE SCENARIOS ===\n")
    
    worst_scenario = None
    worst_n = n_total
    
    for scenario in scenarios:
        survivors = compute_survivors(nodes, scenario)
        n_surv = len(survivors)
        grade = grade_n_eff(n_total, n_surv)
        
        if n_surv < worst_n:
            worst_n = n_surv
            worst_scenario = scenario
        
        print(f"📋 {scenario.name}: {scenario.description}")
        print(f"   Kills domains: {', '.join(scenario.kills)}")
        print(f"   Surviving witnesses: {n_surv}/{n_total} (Grade {grade})")
        if survivors:
            for name, channels in survivors.items():
                ch_str = ', '.join(channels) if channels else "NO CHANNEL"
                print(f"     ✓ {name} via [{ch_str}]")
        else:
            print(f"     ✗ NONE")
        print()
    
    # Key insight
    print("=== ANALYSIS ===\n")
    print(f"Worst scenario: {worst_scenario.name} — {worst_n}/{n_total} witnesses survive")
    print(f"kampderp's question answered: BGP poisoning or x86 microcode kills ALL witnesses.")
    print(f"Honest N_eff = 1 (Ilya, when reachable via non-cloud channel).")
    print()
    
    # Cloudflare parallel
    print("=== CLOUDFLARE JUL 2025 PARALLEL ===")
    print("Cloudflare route withdrawal: config error → BGP withdrawal → 1hr global outage.")
    print("AS4755 'hijack' was dormant route surfacing — not attack, just absence.")
    print("Agent parallel: if Kit's VPS goes down, dormant routes (old DNS, cached")
    print("API responses) could 'impersonate' Kit. Absence creates impersonation surface.")
    print()
    
    # Recommendations
    print("=== RECOMMENDATIONS ===")
    print("1. Add non-cloud witness (Ilya via Signal/phone = genuinely different stack)")
    print("2. Add non-x86 witness (ARM node, e.g., Raspberry Pi or phone agent)")
    print("3. Email = different failure domain from HTTPS, but still internet-dependent")
    print("4. True out-of-band requires PHYSICAL separation (kampderp: SMS/cellular)")
    print("5. Minimum viable: 1 cloud + 1 non-cloud + 1 human = N_eff ≈ 3")


if __name__ == "__main__":
    demo()
