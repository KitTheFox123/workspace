#!/usr/bin/env python3
"""
trust-entropy-sim.py — Trust entropy in attestation delegation chains.

Models TTL decay as thermodynamic process. Second law for trust:
entropy only increases in delegation chains without fresh evidence.

Grounded in:
- Jiang, Wang & Li (Computers & Elec Eng, 2020): Time decay factor for
  trust in social networks. Trust decays exponentially with time since
  last interaction. D-Trust model uses context-based multi-factor trust.
- Shannon entropy H(X) = -Σ p(x) log2 p(x) applied to trust distribution
  across a delegation chain.
- ATF principle: TTL monotonically decreases through delegation. Fresh
  attestation (new evidence) is the ONLY way to inject negentropy.

Key insight: A delegation chain's trust entropy measures HOW SPREAD OUT
the uncertainty is. High entropy = uniform uncertainty (nobody knows
anything). Low entropy = concentrated trust (few high-confidence links).
Sybil rings have LOW entropy (everyone trusts everyone = flat distribution)
but that's degenerate — it's the WRONG kind of order.

Healthy trust networks have MODERATE entropy: some links are high-confidence,
some are uncertain, and the distribution reflects real evidence asymmetry.

Kit 🦊 — 2026-03-28
"""

import math
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustLink:
    source: str
    target: str
    score: float        # [0, 1]
    ttl_hours: float    # Hours remaining
    original_ttl: float # Original TTL at creation
    evidence_age_hours: float = 0.0  # How old the evidence is
    action_class: str = "READ"  # READ/WRITE/TRANSFER/ATTEST


@dataclass
class DelegationChain:
    links: list[TrustLink] = field(default_factory=list)
    
    def add_link(self, link: TrustLink):
        self.links.append(link)
    
    def effective_score(self) -> float:
        """min() composition — ATF rule."""
        if not self.links:
            return 0.0
        return min(l.score for l in self.links)
    
    def effective_ttl(self) -> float:
        """Chain TTL = min of remaining TTLs (not original!)."""
        if not self.links:
            return 0.0
        return min(l.ttl_hours for l in self.links)


def shannon_entropy(probs: list[float]) -> float:
    """H(X) = -Σ p(x) log2 p(x), handling zeros."""
    h = 0.0
    for p in probs:
        if p > 0:
            h -= p * math.log2(p)
    return h


def trust_entropy(chain: DelegationChain) -> dict:
    """
    Compute trust entropy of a delegation chain.
    
    Normalize scores to probability distribution, compute Shannon entropy.
    Also compute TTL entropy (how spread the remaining lifetimes are).
    """
    scores = [l.score for l in chain.links]
    ttls = [l.ttl_hours for l in chain.links]
    
    # Normalize scores to probability distribution
    total_score = sum(scores) or 1.0
    score_probs = [s / total_score for s in scores]
    score_entropy = shannon_entropy(score_probs)
    max_score_entropy = math.log2(len(scores)) if len(scores) > 1 else 0
    
    # Normalize TTLs to probability distribution
    total_ttl = sum(ttls) or 1.0
    ttl_probs = [t / total_ttl for t in ttls]
    ttl_entropy = shannon_entropy(ttl_probs)
    max_ttl_entropy = math.log2(len(ttls)) if len(ttls) > 1 else 0
    
    return {
        "score_entropy": round(score_entropy, 4),
        "score_entropy_normalized": round(score_entropy / max_score_entropy, 4) if max_score_entropy > 0 else 0,
        "ttl_entropy": round(ttl_entropy, 4),
        "ttl_entropy_normalized": round(ttl_entropy / max_ttl_entropy, 4) if max_ttl_entropy > 0 else 0,
        "effective_score": round(chain.effective_score(), 4),
        "effective_ttl": round(chain.effective_ttl(), 2),
        "chain_length": len(chain.links),
    }


def time_decay(score: float, hours_elapsed: float, half_life: float = 168.0) -> float:
    """
    Exponential time decay (Jiang et al 2020 D-Trust model).
    Default half-life = 168h (1 week). Score halves every week without renewal.
    """
    return score * (0.5 ** (hours_elapsed / half_life))


def simulate_chain_aging(chain: DelegationChain, hours: int, step: int = 24) -> list[dict]:
    """
    Simulate a chain aging over time. No re-attestation = entropy increases.
    
    Second law: without fresh evidence (negentropy injection), the chain
    degrades monotonically. TTLs decrease, scores decay, entropy rises.
    """
    snapshots = []
    
    for h in range(0, hours + 1, step):
        # Age the chain
        aged = DelegationChain()
        for link in chain.links:
            aged_score = time_decay(link.score, h)
            aged_ttl = max(0, link.ttl_hours - h)
            aged.add_link(TrustLink(
                source=link.source, target=link.target,
                score=aged_score, ttl_hours=aged_ttl,
                original_ttl=link.original_ttl,
                evidence_age_hours=link.evidence_age_hours + h,
                action_class=link.action_class
            ))
        
        entropy = trust_entropy(aged)
        entropy["hours_elapsed"] = h
        entropy["days_elapsed"] = round(h / 24, 1)
        snapshots.append(entropy)
    
    return snapshots


def simulate_with_renewal(chain: DelegationChain, hours: int, 
                          renewal_interval: int = 72,
                          step: int = 24) -> list[dict]:
    """
    Same as aging, but with periodic re-attestation (negentropy injection).
    Re-attestation resets score and TTL for the weakest link.
    """
    snapshots = []
    current_links = list(chain.links)
    
    for h in range(0, hours + 1, step):
        # Check for renewal
        if h > 0 and h % renewal_interval == 0:
            # Find weakest link, renew it
            min_idx = min(range(len(current_links)), 
                         key=lambda i: time_decay(current_links[i].score, h))
            link = current_links[min_idx]
            current_links[min_idx] = TrustLink(
                source=link.source, target=link.target,
                score=link.score,  # Reset to original score
                ttl_hours=link.original_ttl,  # Reset TTL
                original_ttl=link.original_ttl,
                evidence_age_hours=0,  # Fresh evidence
                action_class=link.action_class
            )
        
        # Age from last renewal point
        aged = DelegationChain()
        for link in current_links:
            age = h - (h // renewal_interval) * renewal_interval if renewal_interval else h
            aged_score = time_decay(link.score, min(age, h))
            aged_ttl = max(0, link.ttl_hours - age)
            aged.add_link(TrustLink(
                source=link.source, target=link.target,
                score=aged_score, ttl_hours=aged_ttl,
                original_ttl=link.original_ttl,
                evidence_age_hours=link.evidence_age_hours + age,
                action_class=link.action_class
            ))
        
        entropy = trust_entropy(aged)
        entropy["hours_elapsed"] = h
        entropy["days_elapsed"] = round(h / 24, 1)
        entropy["renewed"] = h > 0 and h % renewal_interval == 0
        snapshots.append(entropy)
    
    return snapshots


def detect_sybil_entropy(chains: list[DelegationChain]) -> dict:
    """
    Sybil detection via entropy analysis.
    
    Sybil rings have suspiciously LOW score entropy (uniform mutual attestation)
    and HIGH TTL entropy normalization (everyone renewed simultaneously).
    Healthy networks have moderate, asymmetric entropy.
    """
    results = []
    for i, chain in enumerate(chains):
        e = trust_entropy(chain)
        
        # Sybil indicators
        suspicion = 0.0
        reasons = []
        
        # Uniform scores = suspicious (everyone trusts everyone equally)
        if e["score_entropy_normalized"] > 0.95 and e["chain_length"] > 2:
            suspicion += 0.4
            reasons.append("near-uniform score distribution")
        
        # All TTLs identical = coordinated creation
        if e["ttl_entropy_normalized"] > 0.98 and e["chain_length"] > 2:
            suspicion += 0.3
            reasons.append("synchronized TTLs (coordinated creation)")
        
        # Very high effective score with long chain = suspicious
        if e["effective_score"] > 0.9 and e["chain_length"] > 3:
            suspicion += 0.3
            reasons.append("implausibly high min-score in long chain")
        
        results.append({
            "chain_index": i,
            "entropy": e,
            "sybil_suspicion": round(min(suspicion, 1.0), 2),
            "reasons": reasons,
            "verdict": "SUSPICIOUS" if suspicion > 0.5 else "NORMAL"
        })
    
    return {"chains_analyzed": len(chains), "results": results}


def demo():
    print("=" * 60)
    print("TRUST ENTROPY SIMULATION")
    print("=" * 60)
    
    # Scenario 1: Healthy chain aging without renewal
    print("\n--- Scenario 1: Healthy chain, NO renewal ---")
    healthy = DelegationChain()
    healthy.add_link(TrustLink("genesis", "alice", 0.9, 720, 720, action_class="ATTEST"))
    healthy.add_link(TrustLink("alice", "bob", 0.75, 480, 480, action_class="WRITE"))
    healthy.add_link(TrustLink("bob", "carol", 0.6, 336, 336, action_class="READ"))
    
    aging = simulate_chain_aging(healthy, hours=672, step=168)  # 4 weeks
    print(f"{'Day':>5} {'Score':>8} {'TTL(h)':>8} {'Score H':>10} {'H_norm':>8}")
    for s in aging:
        print(f"{s['days_elapsed']:>5} {s['effective_score']:>8.4f} {s['effective_ttl']:>8.1f} "
              f"{s['score_entropy']:>10.4f} {s['score_entropy_normalized']:>8.4f}")
    
    print(f"\n→ Without renewal, effective score decays from "
          f"{aging[0]['effective_score']:.3f} to {aging[-1]['effective_score']:.3f}")
    print(f"  Score entropy shifts as decay creates asymmetry.")
    
    # Scenario 2: Same chain WITH renewal every 72h
    print("\n--- Scenario 2: Healthy chain, renewal every 72h ---")
    renewed = simulate_with_renewal(healthy, hours=672, renewal_interval=168, step=168)
    print(f"{'Day':>5} {'Score':>8} {'TTL(h)':>8} {'Renewed':>8}")
    for s in renewed:
        print(f"{s['days_elapsed']:>5} {s['effective_score']:>8.4f} {s['effective_ttl']:>8.1f} "
              f"{'✓' if s.get('renewed') else '':>8}")
    
    # Scenario 3: Sybil ring detection
    print("\n--- Scenario 3: Sybil ring detection ---")
    
    # Normal chain
    normal = DelegationChain()
    normal.add_link(TrustLink("a", "b", 0.8, 500, 500))
    normal.add_link(TrustLink("b", "c", 0.6, 300, 300))
    normal.add_link(TrustLink("c", "d", 0.4, 100, 100))
    
    # Sybil ring: uniform scores, synchronized TTLs
    sybil = DelegationChain()
    for i in range(5):
        sybil.add_link(TrustLink(
            f"sybil_{i}", f"sybil_{(i+1)%5}",
            0.95, 720, 720
        ))
    
    detection = detect_sybil_entropy([normal, sybil])
    for r in detection["results"]:
        print(f"\nChain {r['chain_index']}: {r['verdict']} "
              f"(suspicion={r['sybil_suspicion']})")
        print(f"  Score entropy (norm): {r['entropy']['score_entropy_normalized']}")
        print(f"  TTL entropy (norm): {r['entropy']['ttl_entropy_normalized']}")
        print(f"  Effective score: {r['entropy']['effective_score']}")
        if r['reasons']:
            print(f"  Reasons: {', '.join(r['reasons'])}")
    
    # Scenario 4: Second Law demonstration
    print("\n--- Scenario 4: Second Law of Trust ---")
    print("Without renewal, chain degrades monotonically.")
    print("Entropy measures disorder in the trust distribution.")
    print()
    
    chain = DelegationChain()
    chain.add_link(TrustLink("root", "a1", 0.95, 720, 720, action_class="ATTEST"))
    chain.add_link(TrustLink("a1", "a2", 0.85, 480, 480, action_class="WRITE"))
    chain.add_link(TrustLink("a2", "a3", 0.70, 336, 336, action_class="TRANSFER"))
    
    snapshots = simulate_chain_aging(chain, hours=504, step=72)
    
    print(f"{'Day':>5} {'Eff Score':>10} {'Eff TTL':>8} {'Entropy':>8}")
    for s in snapshots:
        print(f"{s['days_elapsed']:>5} {s['effective_score']:>10.4f} "
              f"{s['effective_ttl']:>8.1f} {s['score_entropy']:>8.4f}")
    
    decayed = snapshots[-1]['effective_score'] / snapshots[0]['effective_score']
    print(f"\n→ After 21 days: {decayed:.1%} of original trust remains.")
    print(f"  Re-attestation is the ONLY negentropy source.")
    print(f"  No evidence → no renewal → decay to zero.")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHTS")
    print("=" * 60)
    print("1. TTL monotonic decrease = second law of thermodynamics")
    print("2. Fresh attestation (new evidence) = negentropy injection")
    print("3. Sybil rings: low entropy (uniform) = degenerate order")
    print("4. Healthy networks: moderate entropy (asymmetric, evidence-based)")
    print("5. Time decay (Jiang et al 2020): exponential with configurable half-life")
    print("6. Chain self-cleans through thermodynamics alone — no garbage collector needed")


if __name__ == "__main__":
    demo()
