#!/usr/bin/env python3
"""
signal-cost-analyzer.py — Spence signaling theory applied to agent attestations.

Key insight (Connelly et al, J Management 2025): signal power = differential cost.
Good signals are cheap for high-quality agents, expensive for low-quality ones.

Maps each proof type to:
- Cost for honest agent (time, compute, capital)
- Cost for dishonest agent (forgery difficulty)
- Signal strength = cost_dishonest / cost_honest (separation ratio)

Higher separation ratio = stronger signal. If both costs are similar, signal is noise.
"""

import json
import sys
from dataclasses import dataclass

@dataclass
class SignalProfile:
    proof_type: str
    honest_cost: float      # normalized 0-1
    dishonest_cost: float   # normalized 0-1
    description: str
    
    @property
    def separation_ratio(self) -> float:
        """How much harder is it for a dishonest agent? Higher = stronger signal."""
        if self.honest_cost == 0:
            return float('inf') if self.dishonest_cost > 0 else 1.0
        return self.dishonest_cost / self.honest_cost
    
    @property
    def signal_grade(self) -> str:
        r = self.separation_ratio
        if r >= 10: return "A"   # Strong: 10x harder to fake
        if r >= 5:  return "B"   # Good
        if r >= 2:  return "C"   # Weak
        return "D"               # Noise: easy to fake


# Signal profiles for each proof type
SIGNALS = [
    SignalProfile("x402_tx", 0.3, 0.9, "payment: honest = wallet tx, dishonest = needs real capital"),
    SignalProfile("paylock", 0.3, 0.95, "escrow: honest = lock funds, dishonest = capital + time lock"),
    SignalProfile("gen_sig", 0.1, 0.7, "generation sig: honest = sign output, dishonest = forge private key"),
    SignalProfile("dkim", 0.05, 0.8, "DKIM: honest = MTA signs automatically, dishonest = compromise MTA"),
    SignalProfile("content_hash", 0.05, 0.3, "content hash: honest = hash output, dishonest = produce plausible content"),
    SignalProfile("witness", 0.2, 0.3, "witness: honest = observe, dishonest = collude (cheap if sybil)"),
    SignalProfile("attestation", 0.2, 0.4, "attestation: honest = sign claim, dishonest = collude or sybil"),
    SignalProfile("isnad", 0.4, 0.85, "isnad chain: honest = build chain over time, dishonest = fake history"),
    SignalProfile("clawtask", 0.15, 0.25, "clawtask: honest = complete task, dishonest = game completion criteria"),
]


def analyze_bundle(proof_types: list[str]) -> dict:
    """Analyze signaling strength of a proof bundle."""
    profiles = {s.proof_type: s for s in SIGNALS}
    
    results = []
    total_honest = 0
    total_dishonest = 0
    
    for pt in proof_types:
        if pt in profiles:
            s = profiles[pt]
            results.append({
                "proof_type": pt,
                "honest_cost": s.honest_cost,
                "dishonest_cost": s.dishonest_cost,
                "separation_ratio": round(s.separation_ratio, 2),
                "grade": s.signal_grade,
                "description": s.description,
            })
            total_honest += s.honest_cost
            total_dishonest += s.dishonest_cost
    
    # Bundle-level: multiplicative forgery cost (must fake ALL)
    bundle_separation = total_dishonest / max(total_honest, 0.01)
    
    # Weakest link: bundle is only as strong as weakest signal
    weakest = min((r["separation_ratio"] for r in results), default=1.0)
    
    return {
        "signals": results,
        "bundle_separation": round(bundle_separation, 2),
        "weakest_link": round(weakest, 2),
        "bundle_grade": "A" if weakest >= 5 else "B" if weakest >= 3 else "C" if weakest >= 2 else "D",
        "honest_total_cost": round(total_honest, 3),
        "dishonest_total_cost": round(total_dishonest, 3),
    }


def demo():
    print("=== Signal Cost Analyzer (Spence) ===\n")
    
    bundles = {
        "tc3 (3 strong signals)": ["x402_tx", "gen_sig", "dkim"],
        "sybil-friendly (weak signals)": ["witness", "witness", "clawtask"],
        "gold standard": ["paylock", "dkim", "isnad", "gen_sig"],
        "payment only": ["x402_tx", "paylock"],
    }
    
    for name, types in bundles.items():
        result = analyze_bundle(types)
        print(f"  {name}:")
        for s in result["signals"]:
            print(f"    {s['proof_type']}: {s['grade']} (separation {s['separation_ratio']}x)")
        print(f"    → Bundle: {result['bundle_grade']} | weakest link: {result['weakest_link']}x | total separation: {result['bundle_separation']}x")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        types = json.loads(sys.stdin.read())
        print(json.dumps(analyze_bundle(types), indent=2))
    else:
        demo()
