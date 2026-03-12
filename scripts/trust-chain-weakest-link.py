#!/usr/bin/env python3
"""
trust-chain-weakest-link.py — Analyze attestation chains for weakest-link vulnerabilities.

Varian (2004): security games are either weakest-link (chain breaks at worst node)
or best-shot (one strong node saves everyone). Trust chains are BOTH:
- Within a class: weakest-link (one bad attester in a chain breaks it)  
- Across classes: best-shot (one strong class compensates for weak ones)

This tool identifies which links are load-bearing and where to invest.
"""

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Link:
    attester: str
    proof_type: str
    confidence: float  # 0.0-1.0
    age_hours: float = 0.0
    verified: bool = True
    
    @property
    def effective_confidence(self) -> float:
        """Confidence adjusted for age and verification."""
        decay = math.exp(-0.693 * self.age_hours / 720)  # 30d half-life
        return self.confidence * decay * (1.0 if self.verified else 0.5)


@dataclass  
class Chain:
    links: list[Link] = field(default_factory=list)
    
    @property
    def weakest_link(self) -> Link | None:
        if not self.links:
            return None
        return min(self.links, key=lambda l: l.effective_confidence)
    
    @property
    def chain_confidence(self) -> float:
        """Weakest-link: chain = min(links)."""
        if not self.links:
            return 0.0
        return min(l.effective_confidence for l in self.links)
    
    @property
    def best_shot_confidence(self) -> float:
        """Best-shot: max(links)."""
        if not self.links:
            return 0.0
        return max(l.effective_confidence for l in self.links)


def analyze_bundle(chains: dict[str, Chain]) -> dict:
    """Analyze a multi-class attestation bundle."""
    results = {}
    
    # Per-class analysis (weakest-link within each)
    class_scores = {}
    weakest_links = {}
    for cls, chain in chains.items():
        class_scores[cls] = chain.chain_confidence
        wl = chain.weakest_link
        if wl:
            weakest_links[cls] = {
                "attester": wl.attester,
                "proof_type": wl.proof_type,
                "effective_confidence": round(wl.effective_confidence, 3),
                "raw_confidence": wl.confidence,
            }
    
    # Cross-class analysis (best-shot across classes)
    overall_weakest_class = min(class_scores, key=class_scores.get) if class_scores else None
    overall_strongest_class = max(class_scores, key=class_scores.get) if class_scores else None
    
    # Composite: geometric mean of class scores (compromise between weakest-link and best-shot)
    if class_scores:
        log_sum = sum(math.log(max(s, 0.001)) for s in class_scores.values())
        composite = math.exp(log_sum / len(class_scores))
    else:
        composite = 0.0
    
    # Investment recommendation: where does +0.1 confidence help most?
    marginal_value = {}
    for cls, score in class_scores.items():
        # Marginal improvement to composite from boosting this class by 0.1
        boosted = dict(class_scores)
        boosted[cls] = min(score + 0.1, 1.0)
        log_sum_b = sum(math.log(max(s, 0.001)) for s in boosted.values())
        composite_b = math.exp(log_sum_b / len(boosted))
        marginal_value[cls] = round(composite_b - composite, 4)
    
    invest_in = max(marginal_value, key=marginal_value.get) if marginal_value else None
    
    return {
        "class_scores": {k: round(v, 3) for k, v in class_scores.items()},
        "weakest_links": weakest_links,
        "weakest_class": overall_weakest_class,
        "strongest_class": overall_strongest_class,
        "composite": round(composite, 3),
        "invest_in": invest_in,
        "marginal_value": marginal_value,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


def demo():
    print("=== Trust Chain Weakest-Link Analyzer ===\n")
    
    # TC3-like bundle
    tc3 = {
        "payment": Chain([
            Link("bro_agent", "paylock", 0.95, age_hours=48),
            Link("gendolf", "x402_tx", 0.90, age_hours=48),
        ]),
        "generation": Chain([
            Link("kit_fox", "gen_sig", 0.92, age_hours=24),
            Link("kit_fox", "content_hash", 0.98, age_hours=24),
        ]),
        "transport": Chain([
            Link("agentmail", "dkim", 0.85, age_hours=24),
        ]),
    }
    
    result = analyze_bundle(tc3)
    print("TC3 bundle:")
    for cls, score in result["class_scores"].items():
        wl = result["weakest_links"].get(cls, {})
        print(f"  {cls}: {score} (weakest: {wl.get('attester', 'n/a')} @ {wl.get('effective_confidence', 'n/a')})")
    print(f"  Composite: {result['composite']}")
    print(f"  Weakest class: {result['weakest_class']}")
    print(f"  Invest in: {result['invest_in']} (marginal +{result['marginal_value'].get(result['invest_in'], 0)})")
    print()
    
    # Sybil bundle — strong payment, weak everything else
    sybil = {
        "payment": Chain([
            Link("legit_wallet", "x402_tx", 0.95, age_hours=2),
        ]),
        "generation": Chain([
            Link("bot1", "gen_sig", 0.3, age_hours=1),
        ]),
        "transport": Chain([
            Link("bot2", "dkim", 0.2, age_hours=1, verified=False),
        ]),
    }
    
    result2 = analyze_bundle(sybil)
    print("Sybil bundle (strong payment, weak generation+transport):")
    for cls, score in result2["class_scores"].items():
        print(f"  {cls}: {score}")
    print(f"  Composite: {result2['composite']}")
    print(f"  Invest in: {result2['invest_in']} (marginal +{result2['marginal_value'].get(result2['invest_in'], 0)})")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        chains = {}
        for cls, links in data.items():
            chains[cls] = Chain([Link(**l) for l in links])
        print(json.dumps(analyze_bundle(chains), indent=2))
    else:
        demo()
