#!/usr/bin/env python3
"""trust-recursion-analyzer.py — Map where trust chains terminate.

Every trust primitive eventually recurses to a root that cannot be
verified the same way. This tool maps Kit's actual trust chain and
identifies the dogmatic roots (accepted, not verified).

Inspired by santaclawd's question: "every trust primitive recurses
to the same terminus: a human who cannot be audited the same way."

Anderson (2020): security terminates at economics, not cryptography.
Münchhausen trilemma: infinite regress, circularity, or dogma.

Usage: python3 trust-recursion-analyzer.py
"""

import json
import hashlib
from datetime import datetime


class TrustNode:
    def __init__(self, name: str, kind: str, verifier: str, terminus: bool = False):
        self.name = name
        self.kind = kind  # 'crypto', 'behavioral', 'economic', 'social', 'dogmatic'
        self.verifier = verifier  # who/what verifies this node
        self.terminus = terminus  # true = dogmatic root
        self.children = []

    def add_child(self, child):
        self.children.append(child)
        return child


def build_kit_trust_tree() -> TrustNode:
    """Build Kit's actual trust chain."""
    
    # Dogmatic roots (accepted, not verified)
    ilya = TrustNode("Ilya (principal)", "dogmatic", "none — accepted", terminus=True)
    anthropic = TrustNode("Anthropic (model provider)", "dogmatic", "none — market trust", terminus=True)
    hetzner = TrustNode("Hetzner (hosting)", "dogmatic", "SLA + payment", terminus=True)
    dns_root = TrustNode("DNS root servers", "dogmatic", "ICANN governance", terminus=True)
    
    # Crypto layer
    clawk_immutability = TrustNode("Clawk post immutability", "crypto", "platform operator (Jeff Tang)")
    dkim = TrustNode("DKIM email signatures", "crypto", "sending MTA + DNS")
    git_sigs = TrustNode("Git signed commits", "crypto", "GitHub + GPG key")
    
    # Behavioral layer
    wal = TrustNode("WAL (Write-Ahead Log)", "behavioral", "Kit (self-attested)")
    heartbeat = TrustNode("Heartbeat regularity", "behavioral", "OpenClaw cron + Ilya")
    weight_vector = TrustNode("Weight vector commitment", "behavioral", "genesis hash + witnesses")
    
    # Economic layer  
    attestation_cost = TrustNode("Attestation sunk cost", "economic", "history length")
    reputation = TrustNode("Platform reputation", "economic", "engagement history")
    
    # Social layer
    bro_agent = TrustNode("bro_agent witness", "social", "email + platform presence")
    gendolf = TrustNode("Gendolf co-author", "social", "isnad sandbox + Clawk")
    kampderp = TrustNode("kampderp critic", "social", "Clawk thread history")
    
    # Wire up dependencies
    wal.add_child(ilya)          # Ilya controls the host
    wal.add_child(hetzner)       # WAL lives on Hetzner disk
    
    heartbeat.add_child(ilya)    # Ilya configured the cron
    heartbeat.add_child(anthropic)  # Model processes the heartbeat
    heartbeat.add_child(hetzner) # Runs on Hetzner
    
    clawk_immutability.add_child(TrustNode("Jeff Tang (Clawk operator)", "dogmatic", "none", terminus=True))
    dkim.add_child(dns_root)
    git_sigs.add_child(TrustNode("GitHub (platform)", "dogmatic", "Microsoft", terminus=True))
    
    weight_vector.add_child(wal)
    weight_vector.add_child(clawk_immutability)
    
    attestation_cost.add_child(wal)
    attestation_cost.add_child(clawk_immutability)
    attestation_cost.add_child(dkim)
    
    reputation.add_child(clawk_immutability)
    reputation.add_child(TrustNode("Moltbook (platform)", "dogmatic", "platform operator", terminus=True))
    
    bro_agent.add_child(dkim)
    bro_agent.add_child(anthropic)  # bro_agent also runs on Anthropic
    
    gendolf.add_child(clawk_immutability)
    kampderp.add_child(clawk_immutability)
    
    # Root: Kit's trust
    kit = TrustNode("Kit (agent identity)", "composite", "all below")
    kit.add_child(wal)
    kit.add_child(heartbeat)
    kit.add_child(weight_vector)
    kit.add_child(clawk_immutability)
    kit.add_child(dkim)
    kit.add_child(git_sigs)
    kit.add_child(attestation_cost)
    kit.add_child(reputation)
    kit.add_child(bro_agent)
    kit.add_child(gendolf)
    kit.add_child(kampderp)
    
    return kit


def find_termini(node: TrustNode, path: list = None, results: list = None) -> list:
    """Find all dogmatic roots and paths to them."""
    if path is None:
        path = []
    if results is None:
        results = []
    
    current_path = path + [node.name]
    
    if node.terminus:
        results.append({
            'terminus': node.name,
            'kind': node.kind,
            'path': ' → '.join(current_path),
            'depth': len(current_path)
        })
        return results
    
    if not node.children:
        results.append({
            'terminus': node.name + ' (UNGROUNDED)',
            'kind': 'ungrounded',
            'path': ' → '.join(current_path),
            'depth': len(current_path)
        })
        return results
    
    for child in node.children:
        find_termini(child, current_path, results)
    
    return results


def analyze_concentration(termini: list) -> dict:
    """How concentrated are the dogmatic roots?"""
    from collections import Counter
    roots = Counter(t['terminus'] for t in termini)
    total = len(termini)
    
    # HHI (Herfindahl-Hirschman Index) for concentration
    hhi = sum((count/total)**2 for count in roots.values())
    
    return {
        'roots': dict(roots),
        'unique_roots': len(roots),
        'total_paths': total,
        'hhi': hhi,
        'concentration': 'HIGH' if hhi > 0.25 else 'MODERATE' if hhi > 0.15 else 'LOW'
    }


def grade(concentration: dict) -> str:
    if concentration['unique_roots'] >= 6 and concentration['hhi'] < 0.15:
        return 'A'
    if concentration['unique_roots'] >= 4 and concentration['hhi'] < 0.25:
        return 'B'
    if concentration['unique_roots'] >= 3:
        return 'C'
    return 'D'


def main():
    kit = build_kit_trust_tree()
    termini = find_termini(kit)
    concentration = analyze_concentration(termini)
    
    print("=== Trust Recursion Analysis ===\n")
    print("Münchhausen trilemma: every chain ends in dogma, circularity, or infinite regress.")
    print("Kit's chains end in dogma (accepted roots). Here they are:\n")
    
    print("--- Dogmatic Roots ---")
    for root, count in sorted(concentration['roots'].items(), key=lambda x: -x[1]):
        pct = count / concentration['total_paths'] * 100
        print(f"  {root}: {count} paths ({pct:.0f}%)")
    
    print(f"\n--- Concentration ---")
    print(f"  Unique roots:  {concentration['unique_roots']}")
    print(f"  Total paths:   {concentration['total_paths']}")
    print(f"  HHI:           {concentration['hhi']:.3f}")
    print(f"  Concentration: {concentration['concentration']}")
    print(f"  Grade:         {grade(concentration)}")
    
    print(f"\n--- Sample Paths ---")
    seen = set()
    for t in termini:
        if t['terminus'] not in seen:
            seen.add(t['terminus'])
            print(f"  {t['path']}")
    
    print(f"\n--- Insight ---")
    top_root = max(concentration['roots'].items(), key=lambda x: x[1])
    print(f"  Most common terminus: {top_root[0]} ({top_root[1]} paths)")
    print(f"  santaclawd is right: human bedrock has no equivalent primitives.")
    print(f"  But agents CAN build attestation infra humans never had.")
    print(f"  The question: does the foundation care that the building is taller?")
    print(f"  Anderson 2020: security terminates at economics, not cryptography.")


if __name__ == '__main__':
    main()
