#!/usr/bin/env python3
"""
trust-topology-analyzer.py — Classify trust structures as weakest-link or best-shot.

Hirshleifer (1983): Public goods aggregate differently:
- Weakest-link: security = min(contributions). One bad node breaks everything.
- Best-shot: security = max(contributions). One strong node covers everyone.

Attestation chains = weakest-link (one compromised attester invalidates chain).
Proof class diversity = best-shot (one strong class compensates for weak ones).

Optimal design: weakest-link within chains (verify every link),
                best-shot across classes (diversify proof types).
"""

import json
import sys
from dataclasses import dataclass, asdict


@dataclass
class TrustLink:
    """A single link in an attestation chain."""
    attester: str
    proof_type: str
    strength: float  # 0.0-1.0
    verified: bool = True


@dataclass
class TrustChain:
    """A chain of attestations — weakest-link topology."""
    links: list
    
    @property
    def strength(self) -> float:
        """Weakest-link: min of all links."""
        if not self.links:
            return 0.0
        verified = [l for l in self.links if l.verified]
        if not verified:
            return 0.0
        return min(l.strength for l in verified)
    
    @property
    def weakest(self) -> str:
        """Identify the weakest link."""
        if not self.links:
            return "empty"
        return min(self.links, key=lambda l: l.strength if l.verified else 0.0).attester
    
    @property
    def topology(self) -> str:
        return "weakest-link"


@dataclass 
class ProofBundle:
    """Multiple proof classes — best-shot topology."""
    chains: list  # list of TrustChain
    
    @property
    def strength(self) -> float:
        """Best-shot: max of chain strengths."""
        if not self.chains:
            return 0.0
        return max(c.strength for c in self.chains)
    
    @property
    def strongest(self) -> str:
        """Identify the strongest chain."""
        if not self.chains:
            return "empty"
        best = max(self.chains, key=lambda c: c.strength)
        return f"chain[{best.links[0].proof_type if best.links else '?'}]"
    
    @property
    def topology(self) -> str:
        return "best-shot"
    
    def diagnosis(self) -> dict:
        """Full topology analysis."""
        chain_strengths = [(c.links[0].proof_type if c.links else "?", c.strength, c.weakest) 
                          for c in self.chains]
        
        # Effective strength
        best_shot = max(s for _, s, _ in chain_strengths) if chain_strengths else 0.0
        weakest_link_if_serial = min(s for _, s, _ in chain_strengths) if chain_strengths else 0.0
        
        # Improvement from parallel vs serial
        improvement = best_shot / weakest_link_if_serial if weakest_link_if_serial > 0 else float('inf')
        
        return {
            "topology": "best-shot (parallel chains)",
            "effective_strength": round(best_shot, 3),
            "if_serial_instead": round(weakest_link_if_serial, 3),
            "diversity_multiplier": round(improvement, 2),
            "chains": [
                {"class": t, "strength": round(s, 3), "weakest_link": w}
                for t, s, w in chain_strengths
            ],
            "recommendation": self._recommend(chain_strengths),
        }
    
    def _recommend(self, chains) -> str:
        strengths = [s for _, s, _ in chains]
        if len(chains) < 2:
            return "ADD more proof classes — single chain = no best-shot benefit"
        if min(strengths) < 0.3:
            weak = [t for t, s, _ in chains if s < 0.3]
            return f"STRENGTHEN or DROP weak chains: {weak}. They add cost without best-shot benefit."
        if max(strengths) - min(strengths) > 0.5:
            return "REBALANCE: huge gap between strongest and weakest chain. Focus investment on weak links in strong chains."
        return "HEALTHY: multiple strong independent chains provide robust best-shot coverage."


def demo():
    print("=== Trust Topology Analyzer ===\n")
    print("Hirshleifer (1983): weakest-link vs best-shot public goods\n")
    
    # TC3 example
    payment_chain = TrustChain(links=[
        TrustLink("gendolf", "x402_tx", 0.95),
        TrustLink("paylock", "escrow", 0.90),
    ])
    
    generation_chain = TrustChain(links=[
        TrustLink("kit_fox", "gen_sig", 0.92),
        TrustLink("kit_fox", "content_hash", 0.95),
    ])
    
    transport_chain = TrustChain(links=[
        TrustLink("agentmail", "dkim", 0.88),
    ])
    
    witness_chain = TrustChain(links=[
        TrustLink("momo", "attestation", 0.85),
        TrustLink("braindiff", "attestation", 0.80),
    ])
    
    bundle = ProofBundle(chains=[payment_chain, generation_chain, transport_chain, witness_chain])
    
    print("TC3 Bundle:")
    diag = bundle.diagnosis()
    print(f"  Effective strength: {diag['effective_strength']} (best-shot)")
    print(f"  If serial instead: {diag['if_serial_instead']} (weakest-link)")
    print(f"  Diversity multiplier: {diag['diversity_multiplier']}x")
    print(f"  Chains:")
    for c in diag['chains']:
        print(f"    {c['class']}: {c['strength']} (weakest: {c['weakest_link']})")
    print(f"  → {diag['recommendation']}")
    
    print()
    
    # Single chain (bad)
    single = ProofBundle(chains=[
        TrustChain(links=[
            TrustLink("bot1", "witness", 0.60),
            TrustLink("bot2", "witness", 0.40),
            TrustLink("bot3", "witness", 0.55),
        ])
    ])
    
    print("Single-class sybil:")
    diag2 = single.diagnosis()
    print(f"  Effective strength: {diag2['effective_strength']}")
    print(f"  → {diag2['recommendation']}")
    
    print()
    
    # Compromised chain
    compromised = ProofBundle(chains=[
        TrustChain(links=[
            TrustLink("good_attester", "x402_tx", 0.95),
        ]),
        TrustChain(links=[
            TrustLink("compromised", "dkim", 0.10, verified=True),
        ]),
        TrustChain(links=[
            TrustLink("solid_witness", "attestation", 0.85),
        ]),
    ])
    
    print("One compromised chain (best-shot saves you):")
    diag3 = compromised.diagnosis()
    print(f"  Effective strength: {diag3['effective_strength']} (best-shot ignores weak chain)")
    print(f"  If serial: {diag3['if_serial_instead']} (weakest-link would kill you)")
    print(f"  → {diag3['recommendation']}")


if __name__ == "__main__":
    demo()
