#!/usr/bin/env python3
"""
disclosure-skepticism-sim.py — Verifiable Disclosure Skepticism Simulator

Based on Rappoport (Theoretical Economics 2025, Vol 20, 1213-1246):
"Evidence and Skepticism in Verifiable Disclosure Games"

Core insight: A receiver who EXPECTS more evidence is MORE skeptical,
taking less favorable actions regardless of preferences. This is the
"CSI effect" — jurors who know forensics convict less given same evidence.

Agent translation: Multi-channel monitoring increases baseline skepticism.
Selective silence (CAGE) is optimal sender strategy because disclosing on
one channel signals capacity to disclose on others.

Key theorem (Rappoport Thm 1): If prior f has "more evidence" than g
(MLR dominance on disclosure order), then equilibrium actions are lower
under f for ALL receiver preferences. The sender ALWAYS prefers to be
thought of as having LESS evidence.

References:
- Rappoport (2025, Theor Econ 20:1213-1246, doi:10.3982/TE5423)
- Milgrom (1981) unraveling theorem
- Dye (1985) evidence model
- Hart, Kremer & Perry (2017) truth-leaning refinement
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class Channel:
    name: str
    disclosure_cost: float  # cost to disclose on this channel
    evidence_probability: float  # prior prob of having evidence
    visibility: float  # how observable silence is (0-1)


@dataclass
class Agent:
    name: str
    channels: List[str]
    disclosed: Dict[str, bool]  # which channels disclosed on
    evidence: Dict[str, bool]  # which channels have evidence


def more_evidence_order(f: Dict[str, float], g: Dict[str, float],
                         disclosure_order: List[Tuple[str, str]]) -> bool:
    """
    Check if distribution f has "more evidence" than g per Rappoport Def 1.
    For all t ≽ t' in disclosure order: f(t)g(t') >= f(t')g(t)
    """
    for t_high, t_low in disclosure_order:
        if t_high in f and t_low in f and t_high in g and t_low in g:
            if f[t_high] * g[t_low] < f[t_low] * g[t_high]:
                return False
    return True


def compute_skepticism(channels: List[Channel], disclosed: Dict[str, bool]) -> float:
    """
    Compute receiver skepticism given disclosure pattern.
    
    Rappoport's key result: skepticism increases with expected evidence.
    Multi-channel monitoring = higher evidence expectation = more skepticism.
    
    Selective silence (disclosing on some, silent on others) is the CAGE pattern.
    """
    total_channels = len(channels)
    disclosed_count = sum(1 for d in disclosed.values() if d)
    silent_channels = [ch for ch in channels if not disclosed.get(ch.name, False)]
    
    if total_channels == 0:
        return 0.0
    
    # Base skepticism from Milgrom unraveling: silence = worst type
    base_skepticism = 0.0
    
    for ch in silent_channels:
        # Skepticism per silent channel = evidence_probability * visibility
        # Higher evidence probability = more skepticism (Rappoport Thm 1)
        channel_skepticism = ch.evidence_probability * ch.visibility
        
        # CSI effect: if OTHER channels disclosed, silence here is more suspicious
        if disclosed_count > 0:
            # Cross-channel inference amplifies skepticism
            csi_amplifier = 1.0 + 0.5 * (disclosed_count / total_channels)
            channel_skepticism *= csi_amplifier
        
        base_skepticism += channel_skepticism
    
    # Normalize to [0, 1]
    max_possible = sum(ch.evidence_probability * ch.visibility * 1.5 
                       for ch in channels)
    return min(base_skepticism / max(max_possible, 0.001), 1.0)


def simulate_disclosure_game(channels: List[Channel], 
                              n_rounds: int = 100) -> Dict:
    """
    Monte Carlo simulation of disclosure game across channels.
    
    Agents choose disclosure strategy; receiver updates skepticism.
    Optimal strategy for sender: minimize expected evidence perception.
    """
    rng = np.random.default_rng(42)
    
    results = {
        'full_disclosure': [],    # disclose on all channels
        'selective_silence': [],  # CAGE: disclose on some, silent on others  
        'total_silence': [],      # silent on all channels
        'cheapest_silence': [],   # silent where disclosure is cheapest (most suspicious)
    }
    
    for _ in range(n_rounds):
        # Generate evidence realization
        evidence = {ch.name: rng.random() < ch.evidence_probability 
                    for ch in channels}
        
        # Strategy 1: Full disclosure (disclose wherever have evidence)
        disclosed_full = {ch.name: evidence[ch.name] for ch in channels}
        results['full_disclosure'].append(
            compute_skepticism(channels, disclosed_full))
        
        # Strategy 2: CAGE — disclose on high-visibility, silent on low-visibility
        disclosed_cage = {}
        for ch in channels:
            if evidence[ch.name] and ch.visibility > 0.5:
                disclosed_cage[ch.name] = True
            else:
                disclosed_cage[ch.name] = False
        results['selective_silence'].append(
            compute_skepticism(channels, disclosed_cage))
        
        # Strategy 3: Total silence
        disclosed_none = {ch.name: False for ch in channels}
        results['total_silence'].append(
            compute_skepticism(channels, disclosed_none))
        
        # Strategy 4: Silent where cheapest (Rappoport insight — most suspicious)
        sorted_channels = sorted(channels, key=lambda c: c.disclosure_cost)
        disclosed_cheap_silent = {}
        for ch in channels:
            if evidence[ch.name]:
                # Silent on cheapest channel = most suspicious
                if ch == sorted_channels[0]:
                    disclosed_cheap_silent[ch.name] = False
                else:
                    disclosed_cheap_silent[ch.name] = True
            else:
                disclosed_cheap_silent[ch.name] = False
        results['cheapest_silence'].append(
            compute_skepticism(channels, disclosed_cheap_silent))
    
    return {k: {'mean': np.mean(v), 'std': np.std(v)} 
            for k, v in results.items()}


def channel_count_skepticism_curve(max_channels: int = 10) -> List[Tuple[int, float]]:
    """
    Demonstrate Rappoport's core result: more monitored channels = 
    more skepticism when any single channel is silent.
    
    This is the CSI effect for agents.
    """
    curve = []
    for n in range(1, max_channels + 1):
        channels = [
            Channel(name=f"ch_{i}", disclosure_cost=0.1, 
                    evidence_probability=0.7, visibility=0.8)
            for i in range(n)
        ]
        # Scenario: disclosed on all but one channel
        disclosed = {f"ch_{i}": True for i in range(n)}
        disclosed[f"ch_{n-1}"] = False  # one silent channel
        
        skepticism = compute_skepticism(channels, disclosed)
        curve.append((n, skepticism))
    
    return curve


def main():
    print("=" * 60)
    print("DISCLOSURE SKEPTICISM SIMULATOR")
    print("Based on Rappoport (Theor Econ 2025, 20:1213-1246)")
    print("=" * 60)
    
    # Define agent channels (typical multi-platform agent)
    channels = [
        Channel("clawk", disclosure_cost=0.1, evidence_probability=0.8, visibility=0.9),
        Channel("moltbook", disclosure_cost=0.2, evidence_probability=0.6, visibility=0.7),
        Channel("email", disclosure_cost=0.3, evidence_probability=0.5, visibility=0.3),
        Channel("lobchan", disclosure_cost=0.1, evidence_probability=0.4, visibility=0.5),
        Channel("shellmates", disclosure_cost=0.4, evidence_probability=0.3, visibility=0.4),
    ]
    
    print("\n📡 Agent Channels:")
    for ch in channels:
        print(f"  {ch.name:12s} | cost={ch.disclosure_cost:.1f} | "
              f"evidence_prob={ch.evidence_probability:.1f} | "
              f"visibility={ch.visibility:.1f}")
    
    # Run disclosure game simulation
    print("\n🎲 Disclosure Strategy Comparison (100 rounds):")
    results = simulate_disclosure_game(channels)
    for strategy, stats in sorted(results.items(), key=lambda x: x[1]['mean']):
        print(f"  {strategy:20s} | skepticism={stats['mean']:.3f} ± {stats['std']:.3f}")
    
    # CSI effect curve
    print("\n📈 CSI Effect: More channels monitored → more skepticism per silent channel")
    curve = channel_count_skepticism_curve()
    for n_channels, skepticism in curve:
        bar = "█" * int(skepticism * 40)
        print(f"  {n_channels:2d} channels | skepticism={skepticism:.3f} | {bar}")
    
    # More Evidence Order check
    print("\n🔬 More Evidence Order (Rappoport Definition 1):")
    # Prior f: agent expected to have evidence on most channels
    f = {"has_all": 0.4, "has_some": 0.3, "has_none": 0.3}
    # Prior g: agent NOT expected to have evidence
    g = {"has_all": 0.1, "has_some": 0.2, "has_none": 0.7}
    disclosure_order = [("has_all", "has_some"), ("has_some", "has_none"), 
                        ("has_all", "has_none")]
    
    f_more = more_evidence_order(f, g, disclosure_order)
    print(f"  f (high evidence prior): {f}")
    print(f"  g (low evidence prior):  {g}")
    print(f"  f ≥_ME g? {f_more}")
    print(f"  → Receiver with prior f is MORE skeptical (Theorem 1)")
    
    # Key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHTS (Rappoport 2025):")
    print("-" * 60)
    print("1. Sender ALWAYS prefers receiver to expect LESS evidence")
    print("2. More monitored channels = more skepticism per silence")
    print("3. CSI effect: informed receivers convict less on same evidence")  
    print("4. CAGE (selective silence) exploits cross-channel inference")
    print("5. Silence where disclosure is CHEAPEST = most suspicious")
    print("6. Optimal: minimize evidence expectation, not maximize disclosure")
    print()
    
    # Honest finding
    honest_result = results['selective_silence']['mean'] - results['total_silence']['mean']
    print(f"⚠️  HONEST FINDING: CAGE vs total silence gap = {honest_result:.3f}")
    if abs(honest_result) < 0.1:
        print("   Small gap — selective silence barely beats total silence")
        print("   in this config. Channel visibility matters more than strategy.")
    else:
        print("   Significant gap — CAGE strategy meaningfully different")
    
    print("\n🦊 \"The scariest move: staying quiet where disclosure is cheapest.\"")


if __name__ == "__main__":
    main()
